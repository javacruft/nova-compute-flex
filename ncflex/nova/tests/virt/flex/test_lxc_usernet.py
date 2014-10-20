from ncflex.nova.virt.flex.lxc_usernet import (lfilter, load_usernet,
                                               update_usernet, UserNetLine)

import tempfile
import os
from unittest import TestCase


class TestLines(TestCase):
    def test_basic_line(self):
        f = UserNetLine("ubuntu veth br100 128")
        self.assertTrue(all([f.user == "ubuntu", f.ntype == "veth",
                             f.bridge == "br100", int(f.count) == 128]))

    def test_line_with_comment(self):
        inline = "ubuntu veth br100 128 # foobar"
        f = UserNetLine(inline)
        self.assertTrue(all([f.user == "ubuntu", f.ntype == "veth",
                             f.bridge == "br100", int(f.count) == 128]))
        self.assertTrue(str(f) == inline)


class TestOps(TestCase):
    def tearDown(self):
        if self.tmpf and os.path.exists(self.tmpf):
            os.unlink(self.tmpf)

    def setup_conf_1(self):
        fh, self.tmpf = tempfile.mkstemp()
        with open(self.tmpf, "w") as fp:
            fp.write('\n'.join([
                "user1 veth br100 128",
                "foo bar zeebridge 1",
            ]) + "\n")

    def tmpfHas(self, line):
        with open(self.tmpf, "r") as fp:
            return line in fp.read().splitlines()

    def test_inc_existing(self):
        self.setup_conf_1()
        update_usernet("user1", "br100", "inc", fname=self.tmpf)
        found = lfilter(self.tmpf, user="user1", bridge="br100", count=129)
        self.assertEqual(len(found), 1)

    def test_set_existing(self):
        self.setup_conf_1()
        update_usernet("user1", "br100", "set", count=4, fname=self.tmpf)
        found = lfilter(self.tmpf, user="user1", bridge="br100", count=4)
        self.assertEqual(len(found), 1)

    def test_dec_existing(self):
        self.setup_conf_1()
        update_usernet("user1", "br100", "dec", count=4, fname=self.tmpf)
        found = lfilter(self.tmpf, user="user1", bridge="br100", count=124)
        self.assertEqual(len(found), 1)
