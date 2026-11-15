#!/usr/bin/env python3
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skiff import config  # noqa: E402


class ConfigTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        os.environ["XDG_CONFIG_HOME"] = self.tmp.name

    def test_round_trip_strips_unsaved_password(self):
        site = config.default_site()
        site["name"] = "lab"
        site["host"] = "192.168.1.10"
        site["password"] = "secret"
        site["save_password"] = False
        config.save_sites([site])
        loaded = config.load_sites()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["host"], "192.168.1.10")
        self.assertEqual(loaded[0]["password"], "")

    def test_keeps_password_when_asked(self):
        site = config.default_site()
        site["host"] = "box"
        site["password"] = "secret"
        site["save_password"] = True
        config.save_sites([site])
        loaded = config.load_sites()
        self.assertEqual(loaded[0]["password"], "secret")
        path = config.sites_path()
        mode = os.stat(path).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_settings(self):
        s = config.load_settings()
        s["show_hidden"] = True
        config.save_settings(s)
        again = config.load_settings()
        self.assertTrue(again["show_hidden"])


if __name__ == "__main__":
    unittest.main()
