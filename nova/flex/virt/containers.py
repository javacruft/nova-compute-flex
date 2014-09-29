# Copyright (c) 2014 Canonical Ltd
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
import pwd
import uuid

import lxc

from oslo.config import cfg

from nova.flex.virt import config
from nova.flex.virt import images
from nova.flex.virt import utils as container_utils
from nova.flex.virt import volumes

from nova.openstack.common.gettextutils import _  # noqa
from nova.openstack.common import importutils
from nova.openstack.common import log as logging
from nova.openstack.common import units
from nova import context as nova_context
from nova import objects
from nova import utils

MAX_CONSOLE_BYTES = 100 * units.Ki

lxc_opts = [
    cfg.StrOpt('lxc_default_template',
               default='ubuntu-cloud',
               help='Default LXC template'),
    cfg.StrOpt('lxc_template_dir',
               default='/usr/share/lxc/templates',
               help='Default template directory'),
    cfg.StrOpt('lxc_config_dir',
               default='/usr/share/lxc/config',
               help='Default lxc config dir'),
    cfg.StrOpt('vif_driver',
               default='nova.flex.virt.vifs.LXCGenericDriver',
               help='Default vif driver'),
    cfg.IntOpt('num_iscsi_scan_tries',
               default=5,
               help='Number of times to rescan iSCSI target to find volume'),
]

LOG = logging.getLogger(__name__)

CONF = cfg.CONF
CONF.register_opts(lxc_opts, 'lxc')


class Containers(object):
    def __init__(self):
        self.instance_path = None
        self.container_rootfs = None

        vif_class = importutils.import_class(CONF.lxc.vif_driver)
        self.vif_driver = vif_class()
        self.volumes = volumes.VolumeOps()
        self.idmap = container_utils.LXCUserIdMap()

    def init_container(self):
        if not lxc.version:
            raise Exception('LXC is not installed')

        lxc_cgroup = uuid.uuid4()
        utils.execute('cgm', 'create', 'all', lxc_cgroup,
                      run_as_root=True)
        utils.execute('cgm', 'chown', 'all', lxc_cgroup,
                      pwd.getpwuid(os.getuid()).pw_uid,
                      pwd.getpwuid(os.getuid()).pw_gid,
                      run_as_root=True)
        utils.execute('cgm', 'movepid', 'all', lxc_cgroup, os.getpid())

    def spawn(self, context, instance, image_meta, injected_files,
              admin_password, network_info, block_device_info=None):
        LOG.debug('Spawning containers')

        # Check for a vlid image:
        file_type = container_utils.get_disk_format(image_meta)
        if file_type == 'root-tar':
            container_image = '%s.tar.gz' % instance['image_ref']

        # Setup the LXC instance
        instance_name = instance['uuid']
        container = lxc.Container(instance_name)
        container.set_config_path(CONF.instances_path)

        # Grab the flavor information to determine
        # what kind of conatiner we are running
        flavor = objects.Flavor.get_by_id(
            nova_context.get_admin_context(read_deleted='yes'),
            instance['instance_type_id'])

        lxc_type = container_utils.get_lxc_security_info(instance)

        # Create the LXC container from the image
        images.create_container(context, instance, image_meta,
                               container_image, self.idmap, flavor)

        # Write the LXC confgiuration file
        cfg = config.LXCConfig(container, instance, image_meta, network_info,
                               self.idmap)
        cfg.get_config()


        for vif in network_info:
            self.vif_driver.plug(instance, vif)

        # Startint the container
        if not container.running:
            if lxc_type == 'unprivileged':
                LOG.info(_('Starting unprivileged container'))
                if container.start():
                    LOG.info(_('Container started'))
            elif lxc_type == 'privileged':
                try:
                    LOG.info(_('Starting privileged container'))
                    utils.execute('lxc-start', '-n', instance['uuid'],
                                  '-P', CONF.instances_path,
                                  run_as_root=True)
                except OSError as exc:
                    LOG.warn(_("Container failed to start"))

    def destroy_container(self, context, instance, network_info,
                          block_device_info, destroy_disks):
        LOG.debug('Destroying container')
        container = self.get_container_root(instance)
        if container.running:
            container.stop()
        if container.defined:
            # work around for segfaulting api call
            utils.execute('lxc-destroy', '-n', instance['uuid'],
                          '-P', CONF.instances_path)

    def reboot_container(self, context, instance, network_info, reboot_type,
                         block_device_info, bad_volumes_callback):
        LOG.debug('Rebooting container')
        container = self.get_container_root(instance)
        if container.running:
            if container.reboot():
                LOG.info(_('Container rebooted'))

    def stop_container(self, instance):
        LOG.debug('Stopping container')
        container = self.get_container_root(instance)
        if container.running:
            if container.stop():
                LOG.info(_('Container stopped'))

    def start_container(self, context, instance, network_info,
                        block_device_info):
        LOG.debug('Starting container')
        container = self.get_container_root(instance)
        if container.start():
            LOG.info(_('Container started'))

    def shutdown_container(self, instance, network_info, block_device_info):
        LOG.debug('Shutdown container')
        container = self.get_container_root(instance)
        if container.running:
            for vif in network_info:
                self.driver.unplug(instance, vif)
            container.shutdown()

    def suspend_container(self, instance):
        LOG.debug('Suspend container')
        container = self.get_container_root(instance)
        if container.defined and container.controllable:
            container.freeze()

    def resume_container(self, context, instance, network_info,
                         block_device_info):
        LOG.debug('Suspend container')
        container = self.get_container_root(instance)
        if container.defined and container.controllable:
            container.unfreeze()

    def get_container_console(self, instance):
        LOG.debug('Container console log')

        console_log = container_utils.get_container_console(instance)
        with open(console_log, 'rb') as fp:
            log_data, remaining = utils.last_bytes(fp, MAX_CONSOLE_BYTES)
            if remaining > 0:
                LOG.info(_('Truncated console log returned, '
                           '%d bytes ignored'),
                           remaining, instance=instance)
            return log_data

    def attach_container_volume(self, context, connection_info, instance,
                                mountpoint, disk_bus=None, device_type=None,
                                encryption=None):
        host_device = self.volumes.connect_volume(connection_info, instance,
                                                  mountpoint)
        if host_device:
            container = self.get_container_root(instance)
            if container.running:
                path_stat = os.stat(host_device)

                container.set_cgroup_item("devices.allow",
                                          "b %s:%s rwm"
                                          % (int(path_stat.st_rdev / 256),
                                             int(path_stat.st_rdev % 256)))

                # Create the target
                target = '%s%s' % (container_utils.get_container_rootfs(
                                          instance), mountpoint)
                utils.execute('mknod', 'b', int(path_stat.st_rdev / 256),
                              int(path_stat.st_rdev % 256),
                              target, run_as_root=True)

    def detach_container_volume(self, connection_info, instance, mountpoint,
                                encryption):
        self.volumes.disconnect_volume(connection_info, instance, mountpoint)

    def setup_network(self, instance, network_info):
        container = self.get_container_root(instance)
        for vif in network_info:
            self.vif_driver.plug(container, instance, vif)

    def teardown_network(self, instance, network_info):
        self.vif_driver.unplug(instance, network_info)

    def container_exists(self, instance):
        container = self.get_container_root(instance)
        if container.running:
            return True
        else:
            return False

    def get_container_pid(self, instance):
        container = self.get_container_root(instance)
        if container.running:
            return container.init_pid

    def get_container_root(self, instance):
        container = lxc.Container(instance['uuid'])
        container.set_config_path(CONF.instances_path)
        return container
