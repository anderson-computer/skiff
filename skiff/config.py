"""Site manager storage under ~/.config/skiff/."""

from __future__ import annotations

import json
import os
import stat
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
    path = sites_path()
    stored = []
    for site in sites:
        item = deepcopy(site)
        if not item.get("save_password"):
            item["password"] = ""
        stored.append(item)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump({"version": 1, "sites": stored}, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    _chmod_private(path)


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
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(settings, fh, indent=2)
        fh.write("\n")
    os.replace(tmp, path)
    _chmod_private(path)


def find_site(sites: List[Dict[str, Any]], site_id: str) -> Optional[Dict[str, Any]]:
    for site in sites:
        if site.get("id") == site_id:
            return site
    return None
