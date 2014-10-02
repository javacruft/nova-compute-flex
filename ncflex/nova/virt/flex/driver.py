# Copyright 2010 United States Government as represented by the
# Administrator of the National Aeronautics and Space Administration.
# All Rights Reserved.
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

"""
native-lxc driver

"""

import lxc
from oslo.config import cfg

from . import containers
from . import hostops

from nova.compute import power_state
from nova.openstack.common import log as logging
from nova.virt import driver
from nova.virt import volumeutils

CONF = cfg.CONF
CONF.import_opt('host', 'nova.netconf')
CONF.import_opt('my_ip', 'nova.netconf')

LOG = logging.getLogger(__name__)


class LXCDriver(driver.ComputeDriver):
    def __init__(self, virtapi, read_only=False):
        super(LXCDriver, self).__init__(virtapi)
        self.containers = containers.Containers()
        self.hostops = hostops.HostOps()

    def init_host(self, host):
        self.containers.init_container()

    def list_instances(self):
        return lxc.list_containers(config_path=CONF.instances_path)

    def spawn(self, context, instance, image_meta, injected_files,
              admin_password, network_info=None, block_device_info=None):
        self.containers.spawn(context, instance, image_meta, injected_files,
                              admin_password, network_info, block_device_info)

    def snapshot(self, context, instance, name, update_task_state):
        pass

    def reboot(self, context, instance, network_info, reboot_type,
               block_device_info=None, bad_volumes_callback=None):
        self.containers.reboot_container(context, instance, network_info,
                                         reboot_type, block_device_info,
                                         bad_volumes_callback)

    def rescue(self, context, instance, network_info, image_meta,
               rescue_password):
        pass

    def unrescue(self, instance, network_info):
        pass

    def power_off(self, instance, timeout=0, retry_interval=0):
        self.containers.stop_container(instance)

    def power_on(self, context, instance, network_info, block_device_info):
        self.containers.start_container(context, instance, network_info,
                                        block_device_info)

    def suspend(self, instance):
        pass

    def resume(self, context, instance, network_info, block_device_info=None):
        pass

    def destroy(self, context, instance, network_info, block_device_info=None,
                destroy_disks=True):
        self.containers.destroy_container(context, instance, network_info,
                                          block_device_info, destroy_disks)

    def attach_volume(self, context, connection_info, instance, mountpoint,
                      disk_bus=None, device_type=None, encryption=None):
        """Attach the disk to the instance at mountpoint using info."""
        self.containers.attach_container_volume(context, connection_info,
                                                instance, mountpoint,
                                                disk_bus, device_type,
                                                encryption)

    def detach_volume(self, connection_info, instance, mountpoint,
                      encryption=None):
        """Detach the disk attached to the instance."""
        self.containers.detach_container_volume(connection_info, instance,
                                                mountpoint, encryption)

    def attach_interface(self, instance, image_meta, vif):
        pass

    def detach_interface(self, instance, vif):
        pass

    def get_info(self, instance):
        state = self.containers.container_exists(instance)
        if state:
            pstate = power_state.RUNNING
        elif state is False:
            pstate = power_state.SHUTDOWN
        else:
            pstate = power_state.RUNNING
        return {'state': pstate,
                'max_mem': 0,
                'mem': 0,
                'num_cpu': 2,
                'cpu_time': 0}

    def get_console_output(self, context, instance):
        return self.containers.get_container_console(instance)

    def get_available_resource(self, nodename):
        return self.hostops.get_available_resource(nodename)

    def get_host_stats(self, refresh=False):
        return self.hostops.get_host_stats(refresh)

    def get_volume_connector(self, instance):
        return {
            'ip': CONF.my_ip,
            'initiator': volumeutils.get_iscsi_initiator(),
            'host': CONF.host
        }
