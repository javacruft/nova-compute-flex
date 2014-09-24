# Copyright (c) 2014 Canonical Ltd
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import os
import time

from oslo.config import cfg

from nova import exception
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging
from nova.openstack.common import processutils
from nova import utils

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class VolumeOps(object):
    def __init__(self):
        self.num_scan_tries = CONF.lxc.num_iscsi_scan_tries

    def _run_iscsiadm(self, iscsi_properties, iscsi_command, **kwargs):
        check_exit_code = kwargs.pop('check_exit_code', 0)
        (out, err) = utils.execute('iscsiadm', '-m', 'node', '-T',
                                   iscsi_properties['target_iqn'],
                                   '-p', iscsi_properties['target_portal'],
                                   *iscsi_command, run_as_root=True,
                                   check_exit_code=check_exit_code)
        LOG.debug("iscsiadm %(command)s: stdout=%(out)s stderr=%(err)s",
                  {'command': iscsi_command, 'out': out, 'err': err})
        return (out, err)

    def _iscsiadm_update(self, iscsi_properties, property_key, property_value,
                         **kwargs):
        iscsi_command = ('--op', 'update', '-n', property_key,
                         '-v', property_value)
        return self._run_iscsiadm(iscsi_properties, iscsi_command, **kwargs)

    def connect_volume(self, connection_info, instance, mountpoint):
        LOG.debug('Connecting volume instnace=%(instance)s '
                  'connection_info=%(connection_info)s',
                  {'instance': instance,
                   'connection_info': connection_info})

        iscsi_properties = connection_info['data']
        self._connect_to_iscsi_portal(iscsi_properties)

        # Detect new/resized LUNs for existing sessions
        self._run_iscsiadm(iscsi_properties, ("--rescan",))

        host_device = self._get_host_device(iscsi_properties)

        # The /dev/disk/by-path/... node is not always present immediately
        # TODO(justinsb): This retry-with-delay is a pattern, move to utils?
        tries = 0
        while not os.path.exists(host_device):
            if tries >= self.num_scan_tries:
                raise exception.NovaException(_("iSCSI device not found at %s")
                                              % (host_device))

            LOG.warn(_("ISCSI volume not yet"
                       "Will rescan & retry.  Try number: %(tries)s"),
                     {'tries': tries})

            # The rescan isn't documented as being necessary(?), but it helps
            self._run_iscsiadm(iscsi_properties, ("--rescan",))

            tries = tries + 1
            if not os.path.exists(host_device):
                time.sleep(tries ** 2)

        if tries != 0:
            LOG.debug("Found iSCSI node "
                      "(after %(tries)s rescans)",
                      {'tries': tries})

        return host_device

    def disconnect_volume(self, connection_info, instance, mountpoint):
        LOG.debug('Disconnecting volume instnace=%(instance)s '
                  'connection_info=%(connection_info)s',
                  {'instance': instance,
                   'connection_info': connection_info})
        iscsi_properties = connection_info['data']
        host_device = self._get_host_device(iscsi_properties)
        device_prefix = ("/dev/disk/by-path/ip-%s-iscsi-%s-lun-" %
                         (iscsi_properties['target_portal'],
                          iscsi_properties['target_iqn']))
        devices = self._get_all_block_devices()
        devices = [dev for dev in devices if dev.startswith(device_prefix)]
        if not devices:
            self._disconnect_from_iscsi_portal(iscsi_properties)
        elif host_device not in devices:
            # Delete device if LUN is not in use by another instance
            self._delete_device(host_device)

    def _get_all_block_devices(self):
        devices = []
        for device in os.listdir('/dev/disk'):
            devices.append('/dev/disk/by-path/%s' % device)
        return devices

    def _connect_to_iscsi_portal(self, iscsi_properties):
        # NOTE(vish): If we are on the same host as nova volume, the
        #             discovery makes the target so we don't need to
        #             run --op new. Therefore, we check to see if the
        #             target exists, and if we get 255 (Not Found), then
        #             we run --op new. This will also happen if another
        #             volume is using the same target.
        try:
            self._run_iscsiadm(iscsi_properties, ())
        except processutils.ProcessExecutionError as exc:
            # iscsiadm returns 21 for "No records found" after version 2.0-871
            if exc.exit_code in [21, 255]:
                self._reconnect(iscsi_properties)
            else:
                raise

        if iscsi_properties.get('auth_method'):
            self._iscsiadm_update(iscsi_properties,
                                  "node.session.auth.authmethod",
                                  iscsi_properties['auth_method'])
            self._iscsiadm_update(iscsi_properties,
                                  "node.session.auth.username",
                                  iscsi_properties['auth_username'])
            self._iscsiadm_update(iscsi_properties,
                                  "node.session.auth.password",
                                  iscsi_properties['auth_password'])

        #duplicate logins crash iscsiadm after load,
        #so we scan active sessions to see if the node is logged in.
        out = self._run_iscsiadm_bare(["-m", "session"],
                                      run_as_root=True,
                                      check_exit_code=[0, 1, 21])[0] or ""

        portals = [{'portal': p.split(" ")[2], 'iqn': p.split(" ")[3]}
                   for p in out.splitlines() if p.startswith("tcp:")]

        stripped_portal = iscsi_properties['target_portal'].split(",")[0]
        if len(portals) == 0 or len([s for s in portals
                                     if stripped_portal ==
                                     s['portal'].split(",")[0]
                                     and
                                     s['iqn'] ==
                                     iscsi_properties['target_iqn']]
                                    ) == 0:
            try:
                self._run_iscsiadm(iscsi_properties,
                                   ("--login",),
                                   check_exit_code=[0, 255])
            except processutils.ProcessExecutionError as err:
                #as this might be one of many paths,
                #only set successful logins to startup automatically
                if err.exit_code in [15]:
                    self._iscsiadm_update(iscsi_properties,
                                          "node.startup",
                                          "automatic")
                    return

            self._iscsiadm_update(iscsi_properties,
                                  "node.startup",
                                  "automatic")

    def _disconnect_from_iscsi_portal(self, iscsi_properties):
        self._iscsiadm_update(iscsi_properties, "node.startup", "manual",
                              check_exit_code=[0, 21, 255])
        self._run_iscsiadm(iscsi_properties, ("--logout",),
                           check_exit_code=[0, 21, 255])
        self._run_iscsiadm(iscsi_properties, ('--op', 'delete'),
                           check_exit_code=[0, 21, 255])

    def _get_multipath_device_name(self, single_path_device):
        device = os.path.realpath(single_path_device)

        out = self._run_multipath(['-ll',
                                  device],
                                  check_exit_code=[0, 1])[0]
        mpath_line = [line for line in out.splitlines()
                      if "scsi_id" not in line]  # ignore udev errors
        if len(mpath_line) > 0 and len(mpath_line[0]) > 0:
            return "/dev/mapper/%s" % mpath_line[0].split(" ")[0]

        return None

    def _get_iscsi_devices(self):
        try:
            devices = list(os.walk('/dev/disk/by-path'))[0][-1]
        except IndexError:
            return []
        return [entry for entry in devices if entry.startswith("ip-")]

    def _run_iscsiadm_bare(self, iscsi_command, **kwargs):
        check_exit_code = kwargs.pop('check_exit_code', 0)
        (out, err) = utils.execute('iscsiadm',
                                   *iscsi_command,
                                   run_as_root=True,
                                   check_exit_code=check_exit_code)
        LOG.debug("iscsiadm %(command)s: stdout=%(out)s stderr=%(err)s",
                  {'command': iscsi_command, 'out': out, 'err': err})
        return (out, err)

    def _rescan_iscsi(self):
        self._run_iscsiadm_bare(('-m', 'node', '--rescan'),
                                check_exit_code=[0, 1, 21, 255])
        self._run_iscsiadm_bare(('-m', 'session', '--rescan'),
                                check_exit_code=[0, 1, 21, 255])

    def _get_host_device(self, iscsi_properties):
        return ("/dev/disk/by-path/ip-%s-iscsi-%s-lun-%s" %
                (iscsi_properties['target_portal'],
                 iscsi_properties['target_iqn'],
                 iscsi_properties.get('target_lun', 0)))

    def _reconnect(self, iscsi_properties):
        self._run_iscsiadm(iscsi_properties, ('--op', 'new'))
