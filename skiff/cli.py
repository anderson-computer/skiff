"""Command-line options (no Qt): --version, --help and "open this host"."""

from __future__ import annotations

import os

from . import APP_ID, APP_NAME, __version__


USAGE_EXAMPLES = """\
examples:
  skiff                                   start with no connection
  skiff --host files.example.com          connect; ask for the user name and password
  skiff --host 10.0.0.5 --user mike --port 2222
  skiff sftp://mike@files.example.com:2222/var/www
  skiff --host 10.0.0.5 --user mike --key ~/.ssh/id_ed25519
  skiff --host 10.0.0.5 --user mike --password-fd 3   (password on fd 3)
Missing user names and passwords are asked for in a login window; nothing
secret is ever passed on the command line."""


def parse_cli(argv):
    """Handle --help/--version and the connection options before Qt starts.

    Returns (qt_argv, target) where target is None or a dict from
    skiff.target.parse_target. Unknown options are passed through to Qt.
    """
    import argparse

    from .target import TargetError, parse_target

    parser = argparse.ArgumentParser(
        prog=APP_ID,
        usage="%(prog)s [--host HOST] [--user USER] [--port PORT] [--key PATH] [--password-fd N] "
              "[sftp://[user@]host[:port][/path]] [Qt options]",
        description=APP_NAME + " - WinSCP-style dual-pane SFTP client.",
        epilog=USAGE_EXAMPLES + "\n\nStandard Qt options (e.g. -platform offscreen) are passed through. "
        "Sites are stored in ~/.config/" + APP_ID + "/sites.json.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--version", action="version", version=APP_NAME + " " + __version__)
    # nargs="?" so an empty template value (e.g. "--user --port 22") is not an error.
    parser.add_argument("--host", nargs="?", const="", default=None,
                        help="connect to this host on start (also user@host:port)")
    parser.add_argument("--user", nargs="?", const="", default=None,
                        help="user name (asked for if missing)")
    parser.add_argument("--port", nargs="?", const="", default=None,
                        help="SSH port (default 22)")
    parser.add_argument("--key", metavar="PATH", default=None,
                        help="log in with this private key file")
    parser.add_argument("--password-fd", metavar="N", type=int, default=None,
                        help="read the password from open file descriptor N (a pipe from "
                             "the program that started Skiff); never put it in argv or env")
    opts, rest = parser.parse_known_args(argv[1:])
    urls = [a for a in rest if "://" in a and not a.startswith("-")]
    rest = [a for a in rest if a not in urls]
    if len(urls) > 1:
        parser.error("give one sftp:// URL")
    target = None
    if opts.host is not None or urls:
        text = urls[0] if urls else opts.host
        if opts.host and urls:
            parser.error("use either --host or an sftp:// URL, not both")
        try:
            target = parse_target(text or "", opts.user, opts.port)
        except TargetError as exc:
            parser.error(str(exc))
    elif opts.user or opts.port or opts.key or opts.password_fd is not None:
        parser.error("--user, --port, --key and --password-fd need --host (or an sftp:// URL)")
    if target is not None and opts.key:
        key = os.path.expanduser(opts.key)
        if not os.path.isfile(key):
            parser.error("key file not found: %s" % opts.key)
        target["key_file"] = key
    if target is not None and opts.password_fd is not None:
        try:
            target["password"] = read_password_fd(opts.password_fd)
        except (OSError, ValueError) as exc:
            parser.error("--password-fd %s: %s" % (opts.password_fd, exc))
    return [argv[0]] + rest, target


def read_password_fd(fd: int, limit: int = 65536) -> str:
    """Read a password from an inherited fd until EOF, then close it.
    One trailing newline is dropped. A terminal is refused (use the login
    window instead)."""
    if fd < 0 or fd in (1, 2):
        raise ValueError("invalid file descriptor (use 0 or a pipe on 3 or higher)")
    try:
        if os.isatty(fd):
            raise ValueError("is a terminal")
        chunks, size = [], 0
        while True:
            chunk = os.read(fd, 4096)
            if not chunk:
                break
            size += len(chunk)
            if size > limit:
                raise ValueError("too much data")
            chunks.append(chunk)
    finally:
        try:
            os.close(fd)
        except OSError:
            pass
    text = b"".join(chunks).decode("utf-8")
    if text.endswith("\r\n"):
        text = text[:-2]
    elif text.endswith("\n"):
        text = text[:-1]
    return text
