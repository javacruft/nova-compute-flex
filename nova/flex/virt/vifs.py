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

from nova import exception
from nova import utils
from nova.network import manager
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
        if_local_name = 'tap%s' % vif['id'][:11]
        if_remote_name = 'ns%s' % vif['id'][:11]

        utils.execute('ip', 'link', 'add', 'name', if_local_name, 'type',
                      'veth', 'peer', 'name', if_remote_name,
                      run_as_root=True)
        linux_net.create_ovs_vif_port(vif['network']['bridge'],
                                      if_local_name,
                                      self.get_ovs_interfaceid(vif),
                                      vif['address'],
                                      instance['uuid'])

        utils.execute('ip', 'link', 'set', if_local_name, 'up',
                      run_as_root=True)

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
        pass
