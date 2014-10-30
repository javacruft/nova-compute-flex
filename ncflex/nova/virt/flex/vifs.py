# Copyright (C) 2013 VMware, Inc
# Copyright 2011 OpenStack Foundation
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

from oslo.config import cfg

from . import utils as container_utils

from nova import exception
from nova import utils
from nova import processutils
from nova.network import linux_net
from nova.network import model as network_model
from nova.openstack.common.gettextutils import _
from nova.openstack.common import log as logging

CONF = cfg.CONF
CONF.import_opt('vlan_interface', 'nova.manager')
CONF.import_opt('flat_interface', 'nova.manager')

LOG = logging.getLogger(__name__)


class LXCGenericDriver(object):

    def plug(self, instance, vif):
        vif_type = vif['type']

        LOG.debug('vif_type=%(vif_type)s instance=%(instance)s '
                  'vif=%(vif)s',
                  {'vif_type': vif_type, 'instance': instance,
                   'vif': vif})

        if vif_type is None:
            raise exception.NovaException(
                _("vif_type parameter must be present "
                  "for this vif_driver implementation"))

        if vif_type == network_model.VIF_TYPE_BRIDGE:
            self.plug_bridge(instance, vif)
        elif vif_type == network_model.VIF_TYPE_OVS:
            self.plug_ovs(instance, vif)
        else:
            raise exception.NovaException(
                _("Unexpected vif_type=%s") % vif_type)

    def plug_ovs(self, instance, vif):
        """Plug using hybrid strategy

        Create a per-VIF linux bridge, then link that bridge to the OVS
        integration bridge via a veth device, setting up the other end
        of the veth device just like a normal OVS port.  Then boot the
        VIF on the linux bridge using standard LXC mechanisms.
        """
        iface_id = self.get_ovs_interfaceid(vif)
        br_name = self.get_br_name(vif['id'])
        v1_name, v2_name = self.get_veth_pair_names(vif['id'])

        if not linux_net.device_exists(br_name):
            utils.execute('brctl', 'addbr', br_name, run_as_root=True)
            utils.execute('brctl', 'setfd', br_name, 0, run_as_root=True)
            utils.execute('brctl', 'stp', br_name, 'off', run_as_root=True)
            utils.execute('tee',
                          ('/sys/class/net/%s/bridge/multicast_snooping' %
                           br_name),
                          process_input='0',
                          run_as_root=True,
                          check_exit_code=[0, 1])

        if not linux_net.device_exists(v2_name):
            linux_net._create_veth_pair(v1_name, v2_name)
            utils.execute('ip', 'link', 'set', br_name, 'up', run_as_root=True)
            utils.execute('brctl', 'addif', br_name, v1_name, run_as_root=True)
            linux_net.create_ovs_vif_port(self.get_bridge_name(vif),
                                          v2_name, iface_id, vif['address'],
                                          instance['uuid'])

        container_utils.write_lxc_usernet(instance, br_name)

    def get_bridge_name(self, vif):
        return vif['network']['bridge']

    def get_br_name(self, iface_id):
        return ("qbr" + iface_id)[:network_model.NIC_NAME_LEN]

    def get_veth_pair_names(self, iface_id):
        return (("qvb%s" % iface_id)[:network_model.NIC_NAME_LEN],
                ("qvo%s" % iface_id)[:network_model.NIC_NAME_LEN])

    def get_ovs_interfaceid(self, vif):
        return vif.get('ovs_interfaceid') or vif['id']

    def plug_bridge(self, instance, vif):
        network = vif['network']
        if (not network.get_meta('multi_host', False) and
                network.get_meta('should_create_bridge', False)):
            if network.get_meta('should_create_vlan', False):
                iface = CONF.vlan_interface or \
                    network.get_meta('bridge_interface')
                LOG.debug('Ensuring vlan %(vlan)s and bridge %(bridge)s',
                          {'vlan': network.get_meta('vlan'),
                           'bridge': vif['network']['bridge']},
                          instance=instance)
                linux_net.LinuxBridgeInterfaceDriver.ensure_vlan_bridge(
                    network.get_meta('vlan'),
                    vif['network']['bridge'],
                    iface)
            else:
                iface = CONF.flat_interface or \
                    network.get_meta('bridge_interface')
                LOG.debug("Ensuring bridge %s",
                          vif['network']['bridge'], instance=instance)
                linux_net.LinuxBridgeInterfaceDriver.ensure_bridge(
                    vif['network']['bridge'],
                    iface)

    def unplug(self, instance, vif):
        vif_type = vif['type']

        LOG.debug('vif_type=%(vif_type)s instance=%(instance)s '
                  'vif=%(vif)s',
                  {'vif_type': vif_type, 'instance': instance,
                   'vif': vif})

        if vif_type is None:
            raise exception.NovaException(
                _("vif_type parameter must be present "
                  "for this vif_driver implementation"))

        if vif_type == network_model.VIF_TYPE_BRIDGE:
            self.unplug_bridge(instance, vif)
        elif vif_type == network_model.VIF_TYPE_OVS:
            self.unplug_ovs(instance, vif)
        else:
            raise exception.NovaException(
                _("Unexpected vif_type=%s") % vif_type)

    def unplug_bridge(self, instance, vif):
        pass

    def unplug_ovs(self, instance, vif):
        try:
            br_name = self.get_br_name(vif['id'])
            v1_name, v2_name = self.get_veth_pair_names(vif['id'])

            if linux_net.device_exists(br_name):
                utils.execute('brctl', 'delif', br_name, v1_name,
                              run_as_root=True)
                utils.execute('ip', 'link', 'set', br_name, 'down',
                              run_as_root=True)
                utils.execute('brctl', 'delbr', br_name,
                              run_as_root=True)

            linux_net.delete_ovs_vif_port(self.get_bridge_name(vif),
                                          v2_name)
        except processutils.ProcessExecutionError:
            LOG.exception(_("Failed while unplugging vif"),
                          instance=instance)
