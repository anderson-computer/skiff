#!/usr/bin/env python3
"""Encrypted vault (AES-256-GCM + scrypt). No Qt needed."""
import base64
import binascii
import json
import os
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skiff.secret_store import FileVault, VaultError  # noqa: E402

# Test secrets and ids deliberately contain "_", "-", "!" and spaces. None of
# those are in the base64 alphabet (A-Z a-z 0-9 + / =), so they can never
# turn up by chance inside the random salt, nonce or ciphertext: a match in
# the file can only mean a real leak. (A purely alphanumeric secret such as
# "Hunter2" can, very rarely, appear inside base64 output and make a
# no-plaintext check fail at random.)
SITE_ID = "site_id-1"
SECRET = "Hunter2_secret-pw! with spaces"
MASTER = "correct horse_battery"


class FileVaultTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = os.path.join(self.tmp.name, "vault.json")

    def _blob(self):
        with open(self.path, encoding="utf-8") as fh:
            raw = fh.read()
        return raw, json.loads(raw)

    def test_round_trip(self):
        v = FileVault(self.path)
        v.create(MASTER)
        v.set(SITE_ID, SECRET)
        v.set("site_id-2", "second_pw!")
        v2 = FileVault(self.path)
        self.assertFalse(v2.unlocked)
        v2.unlock(MASTER)
        self.assertEqual(v2.get(SITE_ID), SECRET)
        self.assertEqual(v2.get("site_id-2"), "second_pw!")
        self.assertEqual(sorted(v2.ids()), [SITE_ID, "site_id-2"])
        v2.delete(SITE_ID)
        v3 = FileVault(self.path)
        v3.unlock(MASTER)
        self.assertIsNone(v3.get(SITE_ID))

    def test_no_plaintext_on_disk(self):
        v = FileVault(self.path)
        v.create(MASTER)
        v.set(SITE_ID, SECRET)
        raw, blob = self._blob()
        # Exact, deterministic checks (see the note at the top).
        for needle in (SECRET, SITE_ID, MASTER, "_secret-pw!", "with spaces"):
            self.assertNotIn(needle, raw)
        # The file is only the fixed envelope: known keys, constants, and
        # strict base64 for the random parts.
        self.assertEqual(set(blob), {"format", "version", "cipher", "kdf", "nonce", "ciphertext"})
        self.assertEqual(blob["cipher"], "AES-256-GCM")
        self.assertEqual(blob["kdf"]["name"], "scrypt")
        for value in (blob["nonce"], blob["ciphertext"], blob["kdf"]["salt"]):
            try:
                base64.b64decode(value, validate=True)
            except binascii.Error:  # pragma: no cover
                self.fail("not strict base64: %r" % value)
        self.assertEqual(len(base64.b64decode(blob["nonce"])), 12)
        self.assertEqual(len(base64.b64decode(blob["kdf"]["salt"])), 16)
        self.assertEqual(oct(os.stat(self.path).st_mode & 0o777), "0o600")
        # The .bak kept by atomic_write is encrypted and private too.
        v.set(SITE_ID, SECRET + "2")
        with open(self.path + ".bak", encoding="utf-8") as fh:
            self.assertNotIn(SECRET, fh.read())
        self.assertEqual(oct(os.stat(self.path + ".bak").st_mode & 0o777), "0o600")

    def test_wrong_master_password(self):
        v = FileVault(self.path)
        v.create(MASTER)
        v.set(SITE_ID, SECRET)
        bad = FileVault(self.path)
        with self.assertRaises(VaultError) as ctx:
            bad.unlock("wrong horse_battery")
        self.assertIn("Wrong master password", str(ctx.exception))
        self.assertFalse(bad.unlocked)
        with self.assertRaises(VaultError):
            bad.get(SITE_ID)

    def test_tamper_detected(self):
        v = FileVault(self.path)
        v.create(MASTER)
        v.set(SITE_ID, SECRET)
        _, blob = self._blob()
        ct = bytearray(base64.b64decode(blob["ciphertext"]))
        ct[0] ^= 1
        blob["ciphertext"] = base64.b64encode(bytes(ct)).decode()
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump(blob, fh)
        with self.assertRaises(VaultError):
            FileVault(self.path).unlock(MASTER)

    def test_locked_short_master_and_existing(self):
        with self.assertRaises(VaultError):
            FileVault(self.path).create("short")
        v = FileVault(self.path)
        v.create(MASTER)
        with self.assertRaises(VaultError):
            FileVault(self.path).create(MASTER)  # never overwrite a vault
        v.lock()
        with self.assertRaises(VaultError):
            v.get(SITE_ID)

    def test_change_master(self):
        v = FileVault(self.path)
        v.create(MASTER)
        v.set(SITE_ID, SECRET)
        v.change_master(MASTER, "battery staple_2")
        with self.assertRaises(VaultError):
            FileVault(self.path).unlock(MASTER)
        v3 = FileVault(self.path)
        v3.unlock("battery staple_2")
        self.assertEqual(v3.get(SITE_ID), SECRET)

    def test_not_a_vault(self):
        with open(self.path, "w", encoding="utf-8") as fh:
            json.dump({"format": "something-else"}, fh)
        with self.assertRaises(VaultError):
            FileVault(self.path).unlock(MASTER)


if __name__ == "__main__":
    unittest.main()
