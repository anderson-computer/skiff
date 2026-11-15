#!/usr/bin/env python3
"""Keychain backend selection, fallback and plain-text migration. No Qt needed."""
import os
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skiff import config, secret_store as ss  # noqa: E402


class FakeStore:
    def __init__(self):
        self.data = {}

    def set(self, key, pw, label=""):
        self.data[key] = pw

    def get(self, key):
        return self.data.get(key)

    def delete(self, key):
        self.data.pop(key, None)


class BackendSelectionTests(unittest.TestCase):
    def test_labels_match_multissh_wording(self):
        self.assertEqual(ss.BACKEND_LABELS[ss.BACKEND_NONE], "Don't save passwords")
        self.assertEqual(ss.BACKEND_LABELS[ss.BACKEND_KEYRING],
                         "System keychain (GNOME Keyring / Secret Service)")
        self.assertEqual(ss.BACKEND_LABELS[ss.BACKEND_VAULT],
                         "Encrypted vault file (master password)")

    def test_choices_disable_missing_keychain(self):
        on = {k: e for k, _l, e in ss.backend_choices(True)}
        self.assertEqual(on, {"none": True, "keyring": True, "vault": True})
        off = ss.backend_choices(False, "no Secret Service")
        enabled = {k: e for k, _l, e in off}
        self.assertEqual(enabled, {"none": True, "keyring": False, "vault": True})
        label = [l for k, l, _e in off if k == "keyring"][0]
        self.assertIn("not available", label)
        self.assertIn("no Secret Service", label)

    def test_migration_prefers_keychain_then_vault(self):
        self.assertEqual(ss.migration_backend(True), ss.BACKEND_KEYRING)
        self.assertEqual(ss.migration_backend(False), ss.BACKEND_VAULT)

    def test_normalize_and_store_label(self):
        self.assertEqual(ss.normalize_backend("bogus"), ss.BACKEND_NONE)
        self.assertEqual(ss.normalize_backend(None), ss.BACKEND_NONE)
        self.assertEqual(ss.normalize_backend("vault"), ss.BACKEND_VAULT)
        self.assertIsNone(ss.store_label(ss.BACKEND_NONE))
        self.assertEqual(ss.store_label(ss.BACKEND_KEYRING), "system keychain")
        self.assertEqual(ss.store_label(ss.BACKEND_VAULT), "encrypted vault")

    def test_vault_path_setting(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": d}):
            self.assertEqual(ss.vault_path_from_settings({}), os.path.join(d, "skiff", "vault.json"))
            self.assertEqual(ss.vault_path_from_settings({"vault_file": "/x/v.json"}), "/x/v.json")


class KeyringFallbackTests(unittest.TestCase):
    def test_without_libsecret_bindings(self):
        # gi missing (e.g. running from source without python3-gobject-base).
        with mock.patch.dict(sys.modules, {"gi": None}):
            ring = ss.KeyringStore()
        self.assertFalse(ring.available)
        self.assertIn("libsecret is not available", ring.error)

    def test_without_session_bus(self):
        try:
            import gi  # noqa: F401
            gi.require_version("Secret", "1")
            from gi.repository import Secret  # noqa: F401
        except (ImportError, ValueError):
            self.skipTest("libsecret typelib not installed")
        env = {"DBUS_SESSION_BUS_ADDRESS": "unix:path=/nonexistent/skiff-test-bus"}
        with mock.patch.dict(os.environ, env):
            ring = ss.KeyringStore()
            self.assertFalse(ring.available)
        self.assertTrue(ring.error)


class MigrationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.env = mock.patch.dict(os.environ, {"XDG_CONFIG_HOME": self.tmp.name})
        self.env.start()
        self.addCleanup(self.env.stop)

    def _legacy_sites(self):
        a = config.default_site()
        a.update(name="a", host="a", password="pw_a!", save_password=True)
        b = config.default_site()
        b.update(name="b", host="b", password="", save_password=False)
        return [a, b]

    def test_migrate_into_store_leaves_no_plaintext(self):
        sites = self._legacy_sites()
        legacy = config.plaintext_passwords(sites)
        store = FakeStore()
        self.assertEqual(ss.migrate_plaintext(sites, legacy, store), 1)
        self.assertEqual(store.get(sites[0]["id"]), "pw_a!")
        self.assertTrue(sites[0]["save_password"])
        self.assertEqual(sites[0]["password"], "")
        config.save_sites(sites)
        with open(config.sites_path(), encoding="utf-8") as fh:
            self.assertNotIn("pw_a!", fh.read())
        self.assertEqual(config.plaintext_passwords(config.load_sites()), {})

    def test_migrate_into_real_vault(self):
        sites = self._legacy_sites()
        legacy = config.plaintext_passwords(sites)
        vault = ss.FileVault(ss.default_vault_path())
        vault.create("correct horse_battery")
        ss.migrate_plaintext(sites, legacy, vault)
        config.save_sites(sites)
        again = ss.FileVault(ss.default_vault_path())
        again.unlock("correct horse_battery")
        self.assertEqual(again.get(sites[0]["id"]), "pw_a!")

    def test_drop_plaintext(self):
        sites = self._legacy_sites()
        legacy = config.plaintext_passwords(sites)
        self.assertEqual(ss.drop_plaintext(sites, legacy), 1)
        self.assertFalse(sites[0]["save_password"])
        self.assertEqual(sites[0]["password"], "")


if __name__ == "__main__":
    unittest.main()
