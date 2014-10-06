import fixtures
import mox

from oslo.config import cfg

from ncflex.nova.virt.flex import containers
from ncflex.nova.virt.flex import driver as lxc_connection
from ncflex.nova.virt.flex import images
from nova.compute import flavors
from nova.compute import power_state
from nova import context
from nova import db
from nova import test

CONF = cfg.CONF
CONF.import_opt('instances_path', 'nova.compute.manager')

class GraniteDriverTestCase(test.TestCase):
    def setUp(self):
        super(GraniteDriverTestCase, self).setUp()
        self.flags(instances_path=self.useFixture(fixtures.TempDir()).path)
        self.lxc_connection = lxc_connection.LXCDriver(None)

        instance_type = db.flavor_get(context.get_admin_context(), 5)
        sys_meta = flavors.save_flavor_info({}, instance_type)

        self.instance = {
            'uuid': '32dfcb37-5af1-552b-357c-be8c3aa38310',
            'memory_kb': '1024000',
            'basepath': '/some/path',
            'bridge_name': 'br100',
            'vcpus': 2,
            'project_id': 'fake',
            'bridge': 'br101',
            'image_ref': '155d900f-4e14-4e4c-a73d-069cbf4541e6',
            'root_gb': 10,
            'ephemeral_gb': 20,
            'instance_type_id': '5',  # m1.small
            'extra_specs': {},
            'system_metadata': sys_meta}

    def test_list_instances(self):
        lxc = self.lxc_connection.list_instances()
        self.assertEqual(lxc.__class__, tuple)

    def test_list_instances_fail(self):
        pass

    def test_start_container(self):
        pass

    def test_start_container_fail(self):
        pass

    def test_reboot_container(self):
        pass

    def test_reboot_container_fail(self):
        pass

    def test_power_off_container(self):
        pass

    def test_power_off_container_fail(self):
        pass

    def test_power_on_container(self):
        pass

    def test_power_on_container_fail(self):
        pass

    def test_destroy_container(self):
        pass

    def test_destroy_container_fail(self):
        pass

    def test_get_container_info(self):
        self.mox.StubOutWithMock(containers.Containers, 'container_exists')
        containers.Containers.container_exists(mox.IgnoreArg()).AndReturn(True)
        self.mox.ReplayAll()
        state = self.lxc_connection.get_info(self.instance)
        self.assertEqual(state['state'], power_state.RUNNING)
