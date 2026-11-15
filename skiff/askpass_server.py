"""
In-process server that answers the askpass helper (askpass.py).

The OpenSSH backend registers a random token and a handler for each
connection. ssh/sftp are started with the socket path and that token in
their environment; when they need a password they run the helper, which
sends {token, prompt, kind} here. Connections from other users are rejected
by peer credentials, and the socket lives in a 0700 directory under
$XDG_RUNTIME_DIR (or a private temp dir). The password never touches the
disk, argv or the environment.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import socket
import struct
import tempfile
import threading
from typing import Callable, Dict, List, Optional

HELPER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "askpass.py")

Handler = Callable[[str, str], Optional[str]]


class AskpassServer:
    def __init__(self):
        self._handlers: Dict[str, Handler] = {}
        self._lock = threading.Lock()
        self._sock: Optional[socket.socket] = None
        self.path: Optional[str] = None
        self._dir: Optional[str] = None
        self._own_dir = False

    @property
    def running(self) -> bool:
        return self._sock is not None

    def start(self) -> None:
        if self._sock is not None:
            return
        base = os.environ.get("XDG_RUNTIME_DIR")
        if base and os.path.isdir(base) and os.access(base, os.W_OK):
            d = os.path.join(base, "skiff")
            os.makedirs(d, mode=0o700, exist_ok=True)
            self._own_dir = False
        else:
            d = tempfile.mkdtemp(prefix="skiff-")
            self._own_dir = True
        os.chmod(d, 0o700)
        self._dir = d
        self.path = os.path.join(d, "askpass-%d.sock" % os.getpid())
        try:
            os.unlink(self.path)
        except FileNotFoundError:
            pass
        s = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        s.bind(self.path)
        os.chmod(self.path, 0o600)
        s.listen(8)
        self._sock = s
        threading.Thread(target=self._accept_loop, name="skiff-askpass", daemon=True).start()

    def stop(self) -> None:
        sock, self._sock = self._sock, None
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                sock.close()
            except OSError:
                pass
        if self.path is not None:
            try:
                os.unlink(self.path)
            except OSError:
                pass
        if self._own_dir and self._dir:
            shutil.rmtree(self._dir, ignore_errors=True)

    def register(self, handler: Handler) -> str:
        token = secrets.token_hex(24)
        with self._lock:
            self._handlers[token] = handler
        return token

    def unregister(self, token: Optional[str]) -> None:
        if token:
            with self._lock:
                self._handlers.pop(token, None)

    def env_for(self, token: str) -> Dict[str, str]:
        return {
            "SSH_ASKPASS": HELPER,
            "SSH_ASKPASS_REQUIRE": "force",
            "SKIFF_ASKPASS_SOCK": self.path or "",
            "SKIFF_ASKPASS_TOKEN": token,
        }

    # ------------------------------------------------------------------
    def _accept_loop(self) -> None:
        while self._sock is not None:
            try:
                conn, _ = self._sock.accept()
            except OSError:
                return
            threading.Thread(target=self._serve, args=(conn,), daemon=True).start()

    def _serve(self, conn: socket.socket) -> None:
        with conn:
            try:
                creds = conn.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED,
                                        struct.calcsize("3i"))
                _pid, uid, _gid = struct.unpack("3i", creds)
                if uid != os.getuid():
                    return
                raw = b""
                while len(raw) < 65536:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    raw += chunk
                req = json.loads(raw.decode("utf-8"))
                with self._lock:
                    handler = self._handlers.get(str(req.get("token", "")))
                if handler is None:
                    conn.sendall(b'{"ok": false}')
                    return
                try:
                    answer = handler(str(req.get("prompt", "")), str(req.get("kind", "")))
                except Exception:  # never leave ssh hanging
                    answer = None
                reply = {"ok": answer is not None, "answer": answer or ""}
                conn.sendall(json.dumps(reply).encode("utf-8"))
            except (OSError, ValueError):
                return


_SERVER: Optional[AskpassServer] = None
_SERVER_LOCK = threading.Lock()


def shared_server() -> AskpassServer:
    """One server per process, started on first use."""
    global _SERVER
    with _SERVER_LOCK:
        if _SERVER is None:
            _SERVER = AskpassServer()
        _SERVER.start()
        return _SERVER


def password_handler(password: str) -> Handler:
    """Answer password / passphrase prompts with the given secret; refuse
    yes/no confirmations and informational prompts (host keys are handled by
    StrictHostKeyChecking, never by answering "yes" for the user)."""
    def handle(prompt: str, kind: str) -> Optional[str]:
        if kind in ("confirm", "none") or "(yes/no" in prompt.lower():
            return None
        return password
    return handle
