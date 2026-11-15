"""Parse connection targets for Quick Connect and the command line (no Qt).

Accepted forms:  host   host:port   user@host   user@host:port
                 sftp://[user@]host[:port][/path]   (also ssh://)
                 [v6addr]  [v6addr]:port  user@[v6addr]:port
"""

from __future__ import annotations

import re
from typing import Dict, Optional
from urllib.parse import unquote, urlsplit

_HOST_RE = re.compile(r"^[A-Za-z0-9._%-]+$")
_V6_RE = re.compile(r"^[0-9A-Fa-f:.]+(%[A-Za-z0-9_.-]+)?$")


class TargetError(ValueError):
    pass


def _port(text, default: int = 22) -> int:
    if text in (None, ""):
        return default
    try:
        port = int(str(text).strip())
    except ValueError:
        raise TargetError("Invalid port: %r" % text)
    if not 1 <= port <= 65535:
        raise TargetError("Port out of range: %d" % port)
    return port


def _check_host(host: str) -> str:
    host = (host or "").strip()
    if host.startswith("[") and host.endswith("]"):
        host = host[1:-1]
    if not host:
        raise TargetError("Host is required")
    if host.startswith("-") or not (_HOST_RE.match(host) or (":" in host and _V6_RE.match(host))):
        raise TargetError("Invalid host name: %r" % host)
    return host


def _check_user(user: Optional[str]) -> str:
    user = (user or "").strip()
    if user.startswith("-") or any(c.isspace() or c in ":/" for c in user):
        raise TargetError("Invalid user name: %r" % user)
    return user


def parse_target(text: str, user: Optional[str] = None, port=None) -> Dict:
    """-> {"host", "port", "username", "remote_dir"}; explicit user/port win."""
    text = (text or "").strip()
    if not text:
        raise TargetError("Host is required")
    remote_dir = ""
    t_user, t_port = "", None
    if "://" in text:
        parts = urlsplit(text)
        if parts.scheme.lower() not in ("sftp", "ssh"):
            raise TargetError("Only sftp:// (or ssh://) URLs are supported")
        try:
            t_port = parts.port
        except ValueError:
            raise TargetError("Invalid port in %r" % text)
        t_user = unquote(parts.username or "")
        host = parts.hostname or ""
        if parts.path and parts.path != "/":
            remote_dir = unquote(parts.path)
            if remote_dir.startswith("/~"):
                remote_dir = ""  # home-relative paths: start in the home folder
    else:
        if "@" in text:
            t_user, text = text.rsplit("@", 1)
        if text.startswith("["):
            end = text.find("]")
            if end < 0:
                raise TargetError("Invalid host: %r" % text)
            host, rest = text[1:end], text[end + 1:]
            if rest:
                if not rest.startswith(":"):
                    raise TargetError("Invalid host: %r" % text)
                t_port = rest[1:]
        elif text.count(":") == 1:
            host, t_port = text.split(":")
        else:
            host = text  # bare IPv6 without brackets, or a plain host
    result = {
        "host": _check_host(host),
        "port": _port(port if port not in (None, "") else t_port),
        "username": _check_user(user if user not in (None, "") else t_user),
        "remote_dir": remote_dir,
    }
    return result
