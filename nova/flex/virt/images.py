import os
import tarfile

from oslo.config import cfg

from nova.flex.virt import utils as container_utils
from nova import exception
from nova.compute import flavors
from nova.openstack.common import fileutils
from nova.openstack.common import log as logging
from nova.openstack.common.gettextutils import _
from nova import utils
from nova.virt import images

CONF = cfg.CONF

LOG = logging.getLogger(__name__)

def create_container(context, instance, image_meta, container_image, idmap, flavor):
    try:
        _fetch_image(context, instance, image_meta, container_image, idmap, flavor)
        _setup_container(instance, container_image, idmap)
    except Exception as ex:
        LOG.error(_('Failed: %s') % ex)

def _fetch_image(context, instance, image_meta, container_image, idmap, flavor):
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
            raise exeception.InvalidDiskFormat(
                disk_format=container_utils.get_disk_format(image_meta))
        
    if not os.path.exists(image_dir):
        (user, group) = idmap.get_user()
        utils.execute('btrfs', 'sub', 'create', image_dir)

        lxc_type = container_utils.get_lxc_security_info(instance)
        if lxc_type == 'unprivileged':
            utils.execute('chown', '%s:%s' % (user, group), image_dir, run_as_root=True)

            tar = ['tar', '--directory', image_dir,
                   '--anchored', '--numeric-owner', '-xpzf', base]
            nsexec = (['lxc-usernsexec'] + idmap.usernsexec_margs(with_read="user") +
                      ['--'])
            
            args = tuple(nsexec + tar)
            utils.execute(*args, check_exit_code=[0,2])
            utils.execute(*tuple(nsexec + ['chown', '0:0', image_dir]))
        else:
            utils.execute('tar', '--directory', image_dir,
                          '--anchored', '--numeric-owner', '-xpzf', base,
                          run_as_root=True)
            utils.execute('chown', 'root:root', image_dir)

def _setup_container(instance, comtainer_image, idmap):
    container_rootfs = container_utils.get_container_rootfs(instance)
    console_log = container_utils.get_container_console(instance)

    base_dir = os.path.join(CONF.instances_path,
                            CONF.image_cache_subdirectory_name)
    image_dir = os.path.join(base_dir, instance['image_ref'])
    instance_dir = os.path.join(CONF.instances_path,
                                instance['uuid'])

    fileutils.ensure_tree(instance_dir)
    if not os.path.exists(image_dir):
        raise exception.InvaidDiskFormat(
            disk_format=container_utils.get_disk_format(image_meta))

    if not os.path.exists(container_rootfs):
        flavor = flavors.extract_flavor(instance)
        if os.path.exists(image_dir):
            try:
                utils.execute('btrfs', 'subvolume', 'snapshot', image_dir, container_rootfs,
                              run_as_root=True)
            except:
                utils.execute('btrfs', 'subvolume', 'delete', container_rootfs,
                              run_as_root=True)

        if not os.path.exists(console_log):
            utils.execute('touch', console_log)

        # setup the user quotas
        size = instance['root_gb']
        utils.execute('btrfs', 'quota', 'enable', container_rootfs,
                      run_as_root=True)
        utils.execute('btrfs', 'quota', 'rescan', container_rootfs,
                      run_as_root=True)
        utils.execute('btrfs', 'qgroup', 'limit', '%sG' % size, container_rootfs,
                      run_as_root=True)
