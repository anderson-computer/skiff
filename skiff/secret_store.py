"""
Password storage backends (same model as MultiSSH Manager 2.2.0).

  none      passwords are never stored
  keyring   the desktop's Secret Service keychain (GNOME Keyring / KWallet)
            via libsecret. Unlocked with your login; works offline.
  vault     an encrypted file (AES-256-GCM, key derived from a master
            password with scrypt). Works anywhere, including headless and
            airgapped machines; unlocked once per app session.

Passwords are keyed by site id. Nothing here ever writes a password to
sites.json, settings.json, logs, argv or the environment.

This module has no Qt dependency so it can be unit tested headless.
"""

from __future__ import annotations

import base64
import json
import os
from typing import Dict, List, Optional, Tuple

from .config import atomic_write, config_dir

BACKEND_NONE = "none"
BACKEND_KEYRING = "keyring"
BACKEND_VAULT = "vault"
BACKENDS = (BACKEND_NONE, BACKEND_KEYRING, BACKEND_VAULT)
BACKEND_LABELS = {
    BACKEND_NONE: "Don't save passwords",
    BACKEND_KEYRING: "System keychain (GNOME Keyring / Secret Service)",
    BACKEND_VAULT: "Encrypted vault file (master password)",
}
STORE_LABELS = {BACKEND_KEYRING: "system keychain", BACKEND_VAULT: "encrypted vault"}

MIN_MASTER_LEN = 8


class VaultError(Exception):
    pass


def default_vault_path() -> str:
    return os.path.join(config_dir(), "vault.json")


def vault_path_from_settings(settings: Dict) -> str:
    v = (settings.get("vault_file") or "").strip()
    return os.path.expanduser(v) if v else default_vault_path()


def normalize_backend(value) -> str:
    return value if value in BACKENDS else BACKEND_NONE


# ---------------------------------------------------------------------------
# Backend selection
# ---------------------------------------------------------------------------
def backend_choices(keyring_available: bool, keyring_error: str = "") -> List[Tuple[str, str, bool]]:
    """(key, label, enabled) for the "Store passwords" list. The keychain is
    shown but disabled, with the reason, when no Secret Service is usable."""
    out = []
    for key in BACKENDS:
        label = BACKEND_LABELS[key]
        enabled = True
        if key == BACKEND_KEYRING and not keyring_available:
            enabled = False
            label += " — not available" + (": " + keyring_error if keyring_error else "")
        out.append((key, label, enabled))
    return out


def migration_backend(keyring_available: bool) -> str:
    """Store suggested for passwords found in plain text in an old sites.json:
    the keychain when one is running, otherwise the encrypted vault."""
    return BACKEND_KEYRING if keyring_available else BACKEND_VAULT


def store_label(backend: str) -> Optional[str]:
    """Short name shown next to "Save password", or None when saving is off."""
    return STORE_LABELS.get(backend)


# ---------------------------------------------------------------------------
# Encrypted file vault
# ---------------------------------------------------------------------------
class FileVault:
    FORMAT = "skiff-vault"
    VERSION = 1
    # scrypt cost: ~0.1-0.3 s on a desktop CPU, 32 MiB of memory.
    SCRYPT_N, SCRYPT_R, SCRYPT_P = 2 ** 15, 8, 1

    def __init__(self, path: str):
        self.path = os.path.abspath(os.path.expanduser(str(path)))
        self._key: Optional[bytes] = None
        self._salt: Optional[bytes] = None
        self._data: Dict[str, str] = {}

    # --- state ------------------------------------------------------------
    @property
    def exists(self) -> bool:
        return os.path.isfile(self.path)

    @property
    def unlocked(self) -> bool:
        return self._key is not None

    def lock(self) -> None:
        self._key = None
        self._data = {}

    # --- crypto -----------------------------------------------------------
    @classmethod
    def _derive(cls, master: str, salt: bytes, n=None, r=None, p=None) -> bytes:
        from cryptography.hazmat.backends import default_backend
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
        kdf = Scrypt(salt=salt, length=32, n=int(n or cls.SCRYPT_N), r=int(r or cls.SCRYPT_R),
                     p=int(p or cls.SCRYPT_P), backend=default_backend())
        return kdf.derive(master.encode("utf-8"))

    def create(self, master: str) -> None:
        if self.exists:
            raise VaultError("A vault already exists at %s" % self.path)
        if len(master) < MIN_MASTER_LEN:
            raise VaultError("Master password must be at least %d characters" % MIN_MASTER_LEN)
        self._salt = os.urandom(16)
        self._key = self._derive(master, self._salt)
        self._data = {}
        self._write()

    def unlock(self, master: str) -> None:
        from cryptography.exceptions import InvalidTag
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        try:
            with open(self.path, "r", encoding="utf-8") as fh:
                blob = json.load(fh)
            if blob.get("format") != self.FORMAT:
                raise VaultError("%s is not a Skiff vault" % self.path)
            kdf = blob["kdf"]
            salt = base64.b64decode(kdf["salt"])
            nonce = base64.b64decode(blob["nonce"])
            ct = base64.b64decode(blob["ciphertext"])
        except (OSError, ValueError, KeyError, TypeError, AttributeError) as e:
            raise VaultError("Cannot read vault %s: %s" % (self.path, e)) from e
        key = self._derive(master, salt, kdf.get("n"), kdf.get("r"), kdf.get("p"))
        try:
            plain = AESGCM(key).decrypt(nonce, ct, self.FORMAT.encode())
        except InvalidTag:
            raise VaultError("Wrong master password (or the vault file was modified).")
        self._data = json.loads(plain.decode("utf-8"))
        self._key, self._salt = key, salt

    def change_master(self, old: str, new: str) -> None:
        if len(new) < MIN_MASTER_LEN:
            raise VaultError("Master password must be at least %d characters" % MIN_MASTER_LEN)
        self.unlock(old)
        self._salt = os.urandom(16)
        self._key = self._derive(new, self._salt)
        self._write()

    def _write(self) -> None:
        from cryptography.hazmat.primitives.ciphers.aead import AESGCM
        assert self._key is not None and self._salt is not None
        nonce = os.urandom(12)
        ct = AESGCM(self._key).encrypt(
            nonce, json.dumps(self._data).encode("utf-8"), self.FORMAT.encode())
        blob = {
            "format": self.FORMAT, "version": self.VERSION, "cipher": "AES-256-GCM",
            "kdf": {"name": "scrypt", "n": self.SCRYPT_N, "r": self.SCRYPT_R,
                    "p": self.SCRYPT_P, "salt": base64.b64encode(self._salt).decode()},
            "nonce": base64.b64encode(nonce).decode(),
            "ciphertext": base64.b64encode(ct).decode(),
        }
        atomic_write(self.path, json.dumps(blob, indent=2), backup=True)

    # --- secrets ----------------------------------------------------------
    def _need_unlocked(self):
        if not self.unlocked:
            raise VaultError("The vault is locked.")

    def get(self, site_id: str) -> Optional[str]:
        self._need_unlocked()
        return self._data.get(site_id)

    def set(self, site_id: str, password: str, label: str = "") -> None:
        self._need_unlocked()
        self._data[site_id] = password
        self._write()

    def delete(self, site_id: str) -> None:
        self._need_unlocked()
        if self._data.pop(site_id, None) is not None:
            self._write()

    def ids(self):
        self._need_unlocked()
        return list(self._data)


# ---------------------------------------------------------------------------
# Secret Service keychain
# ---------------------------------------------------------------------------
class KeyringStore:
    SCHEMA_NAME = "us.andersoncomputer.Skiff.Password"

    def __init__(self):
        self._schema = None
        self.error: Optional[str] = None
        try:
            import gi
            gi.require_version("Secret", "1")
            from gi.repository import Secret
            self._Secret = Secret
            self._schema = Secret.Schema.new(
                self.SCHEMA_NAME, Secret.SchemaFlags.NONE,
                {"site_id": Secret.SchemaAttributeType.STRING})
        except (ImportError, ValueError, AttributeError) as e:
            self.error = "libsecret is not available: %s" % e

    @property
    def available(self) -> bool:
        if self._schema is None:
            return False
        try:
            from gi.repository import Gio, GLib
            bus = Gio.bus_get_sync(Gio.BusType.SESSION, None)
            res = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                "org.freedesktop.DBus", "NameHasOwner",
                                GLib.Variant("(s)", ("org.freedesktop.secrets",)),
                                None, Gio.DBusCallFlags.NONE, 2000, None)
            if res.unpack()[0]:
                return True
            # Activatable but not yet running also counts.
            res = bus.call_sync("org.freedesktop.DBus", "/org/freedesktop/DBus",
                                "org.freedesktop.DBus", "ListActivatableNames",
                                None, None, Gio.DBusCallFlags.NONE, 2000, None)
            if "org.freedesktop.secrets" in res.unpack()[0]:
                return True
            self.error = ("No Secret Service (GNOME Keyring/KWallet) is running "
                          "in this session.")
            return False
        except Exception as e:  # no session bus, etc.
            self.error = str(e) or "No D-Bus session bus."
            return False

    def get(self, site_id: str) -> Optional[str]:
        try:
            return self._Secret.password_lookup_sync(self._schema, {"site_id": site_id}, None)
        except Exception as e:
            raise VaultError("Keychain lookup failed: %s" % e) from e

    def set(self, site_id: str, password: str, label: str = "") -> None:
        try:
            ok = self._Secret.password_store_sync(
                self._schema, {"site_id": site_id}, self._Secret.COLLECTION_DEFAULT,
                label or "Skiff SFTP (%s)" % site_id, password, None)
        except Exception as e:
            raise VaultError("Keychain store failed: %s" % e) from e
        if not ok:
            raise VaultError("The keychain refused to store the password.")

    def delete(self, site_id: str) -> None:
        try:
            self._Secret.password_clear_sync(self._schema, {"site_id": site_id}, None)
        except Exception as e:
            raise VaultError("Keychain delete failed: %s" % e) from e


def keyring_label(site: Dict) -> str:
    return "Skiff SFTP: %s (%s@%s:%s)" % (
        site.get("name") or site.get("host"), site.get("username"),
        site.get("host"), site.get("port") or 22)


def migrate_plaintext(sites: List[Dict], plaintext: Dict[str, str], store) -> int:
    """Move passwords found in plain text into store (keychain or unlocked
    vault). Marks each site save_password and drops the plaintext from the
    in-memory site. The caller must then save_sites() so the file no longer
    holds them. Returns the number moved; raises VaultError on failure."""
    moved = 0
    for site in sites:
        pw = plaintext.get(site.get("id", ""))
        if not pw:
            continue
        store.set(site["id"], pw, keyring_label(site))
        site["save_password"] = True
        site["password"] = ""
        moved += 1
    return moved


def drop_plaintext(sites: List[Dict], plaintext: Dict[str, str]) -> int:
    """Forget plain-text passwords (user chose "Don't save passwords")."""
    n = 0
    for site in sites:
        if site.get("id") in plaintext:
            site["password"] = ""
            site["save_password"] = False
            n += 1
    return n
