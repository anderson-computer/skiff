"""~/.ssh/known_hosts helpers shared by both backends (no Qt).

When a server's host key isn't known yet, the backends raise UnknownHostKey
with the key and its SHA256 fingerprint. The window shows the fingerprint and,
if you accept it, the key is appended to ~/.ssh/known_hosts (the same file and
format ssh uses) and the connection is retried with strict checking.
"""

from __future__ import annotations

import base64
import hashlib
import os
import subprocess
from typing import List, Optional, Tuple

# ssh-keyscan types, in the order ssh prefers them.
PREFERRED_TYPES = ("ssh-ed25519", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384",
                   "ecdsa-sha2-nistp521", "rsa-sha2-512", "rsa-sha2-256", "ssh-rsa")


def known_hosts_path() -> str:
    return os.path.expanduser("~/.ssh/known_hosts")


def host_entry(host: str, port: int) -> str:
    """known_hosts host field: "host" on port 22, "[host]:port" otherwise."""
    port = int(port or 22)
    return host if port == 22 else "[%s]:%d" % (host, port)


def fingerprint(key_b64: str) -> str:
    """OpenSSH-style SHA256 fingerprint of a base64 public key blob."""
    digest = hashlib.sha256(base64.b64decode(key_b64)).digest()
    return "SHA256:" + base64.b64encode(digest).decode("ascii").rstrip("=")


def add_known_host(host: str, port: int, key_type: str, key_b64: str,
                   path: Optional[str] = None) -> str:
    """Append one key to known_hosts (creating ~/.ssh 0700 / file 0600)."""
    if not key_type or " " in key_type or not key_b64 or any(c.isspace() for c in key_b64):
        raise ValueError("bad host key")
    base64.b64decode(key_b64, validate=True)
    path = path or known_hosts_path()
    folder = os.path.dirname(path)
    if not os.path.isdir(folder):
        os.makedirs(folder, mode=0o700, exist_ok=True)
    line = "%s %s %s\n" % (host_entry(host, port), key_type, key_b64)
    new = not os.path.exists(path)
    needs_nl = False
    if not new:
        with open(path, "rb") as fh:
            fh.seek(0, os.SEEK_END)
            if fh.tell():
                fh.seek(-1, os.SEEK_END)
                needs_nl = fh.read(1) != b"\n"
    fd = os.open(path, os.O_WRONLY | os.O_APPEND | os.O_CREAT, 0o600)
    with os.fdopen(fd, "a", encoding="ascii") as fh:
        fh.write(("\n" if needs_nl else "") + line)
    return line


def parse_keyscan(output: str) -> List[Tuple[str, str]]:
    """[(key_type, base64)] from ssh-keyscan output, best type first."""
    keys = []
    for line in (output or "").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 3:
            keys.append((parts[1], parts[2]))
    order = {t: i for i, t in enumerate(PREFERRED_TYPES)}
    keys.sort(key=lambda k: order.get(k[0], len(order)))
    return keys


def scan(host: str, port: int, timeout: int = 10) -> List[Tuple[str, str]]:
    """Ask the server for its host keys with ssh-keyscan (OpenSSH backend)."""
    try:
        proc = subprocess.run(
            ["ssh-keyscan", "-T", str(int(timeout)), "-p", str(int(port or 22)), "--", host],
            stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, stdin=subprocess.DEVNULL,
            timeout=timeout + 5, check=False)
    except (OSError, subprocess.TimeoutExpired):
        return []
    return parse_keyscan(proc.stdout.decode("utf-8", "replace"))
