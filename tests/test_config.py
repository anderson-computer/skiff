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

    def test_password_never_written_even_when_saved(self):
        # save_password means "kept in the keychain/vault", never in sites.json.
        site = config.default_site()
        site["host"] = "box"
        site["password"] = "pw_never!on-disk"
        site["save_password"] = True
        config.save_sites([site])
        with open(config.sites_path(), encoding="utf-8") as fh:
            raw = fh.read()
        self.assertNotIn("pw_never!on-disk", raw)
        self.assertNotIn('"password"', raw)
        loaded = config.load_sites()
        self.assertTrue(loaded[0]["save_password"])
        self.assertEqual(loaded[0]["password"], "")
        self.assertEqual(config.plaintext_passwords(loaded), {})
        mode = os.stat(config.sites_path()).st_mode & 0o777
        self.assertEqual(mode, 0o600)

    def test_legacy_plaintext_detected(self):
        # Skiff 1.0 wrote {"password": "..."} for sites with save_password.
        import json
        legacy = config.default_site()
        legacy.update(host="old", password="legacy_pw!", save_password=True)
        other = config.default_site()
        other.update(host="nopw", password="", save_password=False)
        with open(config.sites_path(), "w", encoding="utf-8") as fh:
            json.dump({"version": 1, "sites": [legacy, other]}, fh)
        sites = config.load_sites()
        self.assertEqual(config.plaintext_passwords(sites), {legacy["id"]: "legacy_pw!"})

    def test_settings(self):
        s = config.load_settings()
        s["show_hidden"] = True
        config.save_settings(s)
        again = config.load_settings()
        self.assertTrue(again["show_hidden"])
        self.assertEqual(again["password_backend"], "none")
        self.assertEqual(again["vault_file"], "")


if __name__ == "__main__":
    unittest.main()
