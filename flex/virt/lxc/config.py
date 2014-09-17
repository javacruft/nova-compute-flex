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

from oslo.config import cfg

from flex.virt.lxc import utils as container_utils

from nova.openstack.common import fileutils
from nova.openstack.common.gettextutils import _ # noqa
from nova.openstack.common import importutils
from nova.openstack.common import log as logging
from nova import exception
from nova import context as nova_context
from nova import objects
from nova import utils

LOG = logging.getLogger(__name__)

CONF = cfg.CONF


class LXCConfig(object):
    def __init__(self, container, instance, image_meta, network_info, idmap):
        self.container = container
        self.instance = instance
        self.image_meta = image_meta
        self.network_info = network_info
        self.idmap = idmap

        self.flavor = objects.Flavor.get_by_id(
            nova_context.get_admin_context(read_deleted='yes'),
            instance['instance_type_id'])
        self.lxc_type = container_utils.get_lxc_security_info(self.flavor)

    def get_config(self):
        LOG.debug('Building LXC container configuration file')

        lxc_template = self._get_lxc_template()
        if lxc_template:
            self._write_lxc_template(lxc_template)

            self.container.load_config()
            self.config_lxc_name()
            self.config_lxc_rootfs()
            self.config_lxc_user()
            self.config_lxc_logging()
            self.config_lxc_network()
            self.config_lxc_console()
            self.config_lxc_limits()
            self.container.save_config()

    def _get_lxc_template(self):
        LOG.debug('Fetching LXC template')

        templates = []
        if (self.image_meta and
            self.image_meta.get('properties', {}).get('template')):
                lxc_template = self.image_meta['propeties'].get('template')
        else:
                lxc_template = CONF.lxc.lxc_default_template
        path = os.listdir(CONF.lxc.lxc_template_dir)
        for line in path:
            templates.append(line.replace('lxc-', ''))
        if lxc_template in templates:
            return lxc_template

    def _write_lxc_template(self, template_name):
        config_file = container_utils.get_container_config(self.instance)
        f = open(config_file, 'w')
        f.write('lxc.include = %s/%s.common.conf\n' % (CONF.lxc.lxc_config_dir,
                                                       template_name))
        f.write('lxc.include = %s/%s.userns.conf\n' % (CONF.lxc.lxc_config_dir,
                                                       template_name))
        f.close()

    def config_lxc_name(self):
        if self.instance:
            self.container.append_config_item('lxc.utsname',
                                              self.instance['uuid'])

    def config_lxc_rootfs(self):
        container_rootfs = container_utils.get_container_rootfs(self.instance)
        if os.path.exists(container_rootfs):
            self.container.append_config_item('lxc.rootfs', container_rootfs)

    def config_lxc_logging(self):
        self.container.append_config_item('lxc.logfile',
                        container_utils.get_container_logfile(self.instance))

    def config_lxc_network(self):
        for vif in self.network_info:
            bridge = vif['network']['bridge']
            mac = vif['address']

        self.container.append_config_item('lxc.network.type', 'veth')
        self.container.append_config_item('lxc.network.hwaddr', mac)
        self.container.append_config_item('lxc.network.link', bridge)

    def config_lxc_console(self):
        self.container.append_config_item('lxc.console.logfile',
                    container_utils.get_container_console(self.instance))

    def config_lxc_limits(self):
        return
        #flavor = flavors.extract_flavor(self.instance)
        #self.container.append_config_item('lxc.cgroup.memory.limit.in_bytes', '%sM' % flavor['memory_mb'])

    def config_lxc_user(self):
        if self.lxc_type == 'unprivileged':
            for ent in self.idmap.lxc_conf_lines():
                self.container.append_config_item(*ent)
