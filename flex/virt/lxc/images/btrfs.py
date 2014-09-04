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
import tarfile


from oslo.config import cfg

from flex.virt.lxc import utils as container_utils

from nova import exception
from nova.compute import flavors
from nova.openstack.common import fileutils
from nova.openstack.common import log as logging
from nova.openstack.common.gettextutils import _
from nova import utils
from nova.virt import images

CONF = cfg.CONF
LOG = logging.getLogger(__name__)


class FlexBtrfsFs(object):
    def create_container(self, context, instance, image_meta, container_image, idmap):
        try:
            self._fetch_image(context, instance, image_meta, container_image, idmap)
            self._create_container(instance, container_image)
        except Exception as ex:
            LOG.error(_('Failed: %s') % ex)

    def _fetch_image(self,context, instance, image_meta, container_image, idmap):
        """Fetch the image from a glance image server."""
        LOG.debug("Downloading image from glance")

        base_dir = os.path.join(CONF.instances_path,
                                CONF.image_cache_subdirectory_name)
        image_dir = os.path.join(base_dir, instance['image_ref'])
        if not os.path.exists(base_dir):
            fileutils.ensure_tree(base_dir)
        base = os.path.join(base_dir, container_image)
        if not os.path.exists(base):
            images.fetch_to_raw(context, instance['image_ref'], base,
                                instance['user_id'], instance['project_id'])
        if not tarfile.is_tarfile(base):
            os.unlink(base)
            raise exception.InvalidDiskFormat(
                disk_format=container_utils.get_disk_format(image_meta))
        if not os.path.exists(image_dir):
            utils.execute('btrfs', 'sub', 'create', image_dir)

            tar = ['tar', '--directory', image_dir,
                  '--anchored', '--numeric-owner', '-xpzf', base]
            nsexec = (['lxc-usernsexec'] + idmap.usernsexec_margs(with_read="user") +
                      ['--'])
            args = tuple(nsexec + tar)
            utils.execute(*args, check_exit_code=[0, 2])
            utils.execute(*tuple(nsexec + ['chown', '0:0', container_rootfs]))

            os.unlink(base)

    def _create_container(self, instance, container_image):
        """Create the LXC container"""
        LOG.debug("Creating LXC container")

        container_rootfs = container_utils.get_container_rootfs(instance)
        console_log = container_utils.get_container_console(instance)

        base_dir = os.path.join(CONF.instances_path,
                                CONF.image_cache_subdirectory_name)
        image_dir = os.path.join(base_dir, instance['image_ref'])
        instance_dir = os.path.join(CONF.instances_path, instance['uuid'])

        flavor = flavors.extract_flavor(instance)

        if not os.path.exists(instance_dir):
            fileutils.ensure_tree(instance_dir)

        if not os.path.exists(container_rootfs):
            utils.execute('btrfs', 'subvolume', 'snapshot', image_dir, container_rootfs)
            utils.execute('chown', '0:0', container_rootfs)

        if not os.path.exists(console_log):
            utils.execute('touch', console_log)
