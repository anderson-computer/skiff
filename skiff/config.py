"""Site manager storage under ~/.config/skiff/."""

from __future__ import annotations

import json
import os
import shutil
import stat
import tempfile
import uuid
from copy import deepcopy
from typing import Any, Dict, List, Optional

APP_DIR_NAME = "skiff"
SITES_FILE = "sites.json"
SETTINGS_FILE = "settings.json"


def config_dir() -> str:
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        path = os.path.join(xdg, APP_DIR_NAME)
    else:
        path = os.path.join(os.path.expanduser("~"), ".config", APP_DIR_NAME)
    os.makedirs(path, mode=0o700, exist_ok=True)
    return path


def sites_path() -> str:
    return os.path.join(config_dir(), SITES_FILE)


def settings_path() -> str:
    return os.path.join(config_dir(), SETTINGS_FILE)


def atomic_write(path: str, text: str, backup: bool = False) -> None:
    """Write text to path atomically with mode 0600 from the start (the
    temporary file is created private, so nothing is ever world-readable).
    With backup=True the previous version is kept as path.bak."""
    folder = os.path.dirname(os.path.abspath(path))
    os.makedirs(folder, mode=0o700, exist_ok=True)
    if backup and os.path.exists(path):
        try:
            shutil.copy2(path, path + ".bak")
            os.chmod(path + ".bak", 0o600)
        except OSError:
            pass
    fd, tmp = tempfile.mkstemp(prefix=".tmp-", dir=folder)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
            fh.flush()
            os.fsync(fh.fileno())
        os.chmod(tmp, 0o600)
        os.replace(tmp, path)
    except BaseException:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _chmod_private(path: str) -> None:
    try:
        os.chmod(path, stat.S_IRUSR | stat.S_IWUSR)
    except OSError:
        pass


def default_site() -> Dict[str, Any]:
    return {
        "id": str(uuid.uuid4()),
        "name": "New site",
        "host": "",
        "port": 22,
        "username": os.environ.get("USER") or os.environ.get("USERNAME") or "",
        "password": "",
        "save_password": False,
        "key_file": "",
        "auth": "agent",  # agent | key | password
        "protocol": "sftp",
        "remote_dir": "",
        "local_dir": os.path.expanduser("~"),
        "timeout": 20,
        "strict_host": True,
        "sudo": False,        # start the remote sftp-server through sudo -n
        "sudo_user": "",      # "" = root
        "sftp_server": "",    # "" = auto-detect
    }


def load_sites() -> List[Dict[str, Any]]:
    path = sites_path()
    if not os.path.isfile(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        sites = data.get("sites", [])
        if not isinstance(sites, list):
            return []
        out = []
        for raw in sites:
            if not isinstance(raw, dict):
                continue
            site = default_site()
            site.update(raw)
            out.append(site)
        return out
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        return []


def save_sites(sites: List[Dict[str, Any]]) -> None:
    """Write sites.json. Passwords are never written here: a site with
    save_password set has its password in the keychain or vault (see
    secret_store), keyed by the site id."""
    path = sites_path()
    stored = []
    for site in sites:
        item = deepcopy(site)
        item.pop("password", None)
        item["save_password"] = bool(item.get("save_password"))
        stored.append(item)
    atomic_write(path, json.dumps({"version": 2, "sites": stored}, indent=2) + "\n")
    _chmod_private(path)


def plaintext_passwords(sites: List[Dict[str, Any]]) -> Dict[str, str]:
    """Passwords that an older Skiff stored in plain text in sites.json,
    keyed by site id. load_sites() keeps them in memory only so they can be
    migrated into the keychain or vault on first run."""
    return {s["id"]: s["password"] for s in sites
            if s.get("password") and s.get("id")}


def load_settings() -> Dict[str, Any]:
    defaults = {
        "show_hidden": False,
        "last_site_id": "",
        "window_width": 1200,
        "window_height": 760,
        "queue_height": 140,
        "left_ratio": 1,
        "right_ratio": 1,
        "confirm_delete": True,
        "password_backend": "none",  # none | keyring | vault
        "vault_file": "",            # "" = ~/.config/skiff/vault.json
    }
    path = settings_path()
    if not os.path.isfile(path):
        return defaults
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if isinstance(data, dict):
            defaults.update(data)
    except (OSError, json.JSONDecodeError, TypeError, ValueError):
        pass
    return defaults


def save_settings(settings: Dict[str, Any]) -> None:
    path = settings_path()
    atomic_write(path, json.dumps(settings, indent=2) + "\n")
    _chmod_private(path)


def find_site(sites: List[Dict[str, Any]], site_id: str) -> Optional[Dict[str, Any]]:
    for site in sites:
        if site.get("id") == site_id:
            return site
    return None
