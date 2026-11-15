"""Run the remote SFTP server through sudo (no Qt, no I/O).

Skiff logs in as the site's user and then starts the remote sftp-server as
another user (root by default) with ``sudo -n``. ``-n`` means sudo never
prompts: the SFTP subsystem has no TTY, so a password prompt would hang or
corrupt the SFTP stream. Hosts must allow the sftp-server command without a
password (NOPASSWD); Skiff never asks for or stores a sudo password.
"""

from __future__ import annotations

import re
import shlex
import time
from typing import Iterable, List, Optional, Tuple

# Where distributions install OpenSSH's sftp-server, in probe order.
SFTP_SERVER_CANDIDATES = (
    "/usr/libexec/openssh/sftp-server",  # RHEL / Rocky / Fedora
    "/usr/lib/openssh/sftp-server",      # Debian / Ubuntu
    "/usr/lib/ssh/sftp-server",          # Arch / SUSE / others
)
DEFAULT_SUDO_USER = "root"
DETECT_MARK = "SKIFF_SFTP_SERVER="
PASSWORD_HINT = "sudo requires a password on this host. Configure NOPASSWD for the sftp-server command"

_USER_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,31}\$?$")
_PATH_RE = re.compile(r"^/[A-Za-z0-9._/+-]+$")


class SudoConfigError(ValueError):
    """The site's sudo settings are not usable (bad user name or path)."""


def sudo_user(site: dict) -> str:
    user = (site.get("sudo_user") or "").strip() or DEFAULT_SUDO_USER
    if not _USER_RE.match(user):
        raise SudoConfigError("Invalid sudo user name: %r" % user)
    return user


def server_path(site: dict) -> str:
    """The configured sftp-server path, or "" for auto-detect."""
    path = (site.get("sftp_server") or "").strip()
    if path and (not _PATH_RE.match(path) or "/../" in path + "/"):
        raise SudoConfigError(
            "Invalid sftp-server path: %r (use an absolute path such as %s)" % (path, SFTP_SERVER_CANDIDATES[0]))
    return path


def enabled(site: dict) -> bool:
    return bool(site.get("sudo"))


def detect_script(candidates: Iterable[str] = SFTP_SERVER_CANDIDATES) -> str:
    """POSIX sh snippet that prints the first executable sftp-server."""
    quoted = " ".join(shlex.quote(c) for c in candidates)
    return ('for p in %s; do if [ -x "$p" ]; then echo "%s$p"; break; fi; done' % (quoted, DETECT_MARK))


def parse_detect(output: str) -> str:
    for line in (output or "").splitlines():
        line = line.strip()
        if line.startswith(DETECT_MARK):
            path = line[len(DETECT_MARK):]
            if _PATH_RE.match(path):
                return path
    return ""


def not_found_message() -> str:
    return ("Could not find sftp-server on the remote host (looked in %s). "
            "Set the path in Site Manager > sudo > SFTP server path." % ", ".join(SFTP_SERVER_CANDIDATES))


def sudo_command(user: str, path: str) -> str:
    """Remote command line that starts sftp-server as *user* without prompting."""
    if not _USER_RE.match(user or ""):
        raise SudoConfigError("Invalid sudo user name: %r" % user)
    if not _PATH_RE.match(path or ""):
        raise SudoConfigError("Invalid sftp-server path: %r" % path)
    return "sudo -n -u %s %s" % (shlex.quote(user), shlex.quote(path))


def sudoers_line(login_user: str, user: str, path: str) -> str:
    return "%s ALL=(%s) NOPASSWD: %s" % (login_user or "USER", user or DEFAULT_SUDO_USER,
                                         path or SFTP_SERVER_CANDIDATES[0])


def is_sudo_failure(stderr: str) -> bool:
    return any(line.strip().startswith("sudo:") for line in (stderr or "").splitlines())


def explain_failure(stderr: str, login_user: str, user: str, path: str) -> Optional[str]:
    """Turn sudo's stderr into a clear message, or None if it isn't from sudo."""
    lines = [l.strip() for l in (stderr or "").splitlines() if l.strip().startswith("sudo:")]
    if not lines:
        return None
    text = " ".join(lines)
    low = text.lower()
    sample = sudoers_line(login_user, user, path)
    fix = ("\n\nAdd this with visudo (for example in /etc/sudoers.d/skiff) on the server:\n"
           "    %s" % sample)
    if "password is required" in low or "a terminal is required" in low or "no tty present" in low:
        return "%s.%s\n\n(sudo said: %s)" % (PASSWORD_HINT, fix, text)
    if "not allowed" in low or "not in the sudoers" in low or "may not run sudo" in low:
        return ("%s may not run %s as %s with sudo.%s\n\n(sudo said: %s)"
                % (login_user, path, user, fix, text))
    if "unknown user" in low:
        return "sudo user %r does not exist on the server.\n\n(sudo said: %s)" % (user, text)
    if "command not found" in low or "not found" in low:
        return "sudo could not run %s.\n\n(sudo said: %s)" % (path, text)
    return "sudo failed: %s%s" % (text, fix)


# ── OpenSSH sftp "ls -la" parsing (used in sudo mode, where the remote shell
#    commands Skiff normally uses would run as the login user, not as root) ──

_MONTHS = {m: i for i, m in enumerate(
    ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"), 1)}


def _mode_from_perms(perms: str) -> int:
    import stat as st
    kinds = {"d": st.S_IFDIR, "l": st.S_IFLNK, "-": st.S_IFREG, "c": st.S_IFCHR,
             "b": st.S_IFBLK, "p": st.S_IFIFO, "s": st.S_IFSOCK}
    mode = kinds.get(perms[:1], st.S_IFREG)
    bits = perms[1:10].ljust(9, "-")
    for i, ch in enumerate(bits):
        if ch not in "-ST":
            mode |= 1 << (8 - i)
    if bits[2] in "sS":
        mode |= st.S_ISUID
    if bits[5] in "sS":
        mode |= st.S_ISGID
    if bits[8] in "tT":
        mode |= st.S_ISVTX
    if bits[2] == "S":
        mode &= ~0o100
    if bits[5] == "S":
        mode &= ~0o010
    if bits[8] == "T":
        mode &= ~0o001
    return mode


def _parse_time(month: str, day: str, tod: str, now: float) -> float:
    mon = _MONTHS.get(month[:3].title())
    if not mon:
        return 0.0
    try:
        d = int(day)
        if ":" in tod:
            hh, mm = (int(x) for x in tod.split(":", 1))
            year = time.localtime(now).tm_year
            t = time.mktime((year, mon, d, hh, mm, 0, 0, 0, -1))
            if t > now + 86400:  # ls shows HH:MM for the last ~6 months
                t = time.mktime((year - 1, mon, d, hh, mm, 0, 0, 0, -1))
            return t
        return time.mktime((int(tod), mon, d, 0, 0, 0, 0, 0, -1))
    except (ValueError, OverflowError):
        return 0.0


def parse_ls(output: str, now: Optional[float] = None) -> List[Tuple[str, int, int, float, str, str]]:
    """Parse ``sftp`` ``ls -la`` lines into (name, mode, size, mtime, owner, group).

    Run after ``cd DIR`` so names are bare. Lines echoed by sftp's batch mode
    ("sftp> ...") and "." / ".." are skipped.
    """
    now = time.time() if now is None else now
    rows = []
    for line in (output or "").splitlines():
        if not line or line.startswith("sftp>"):
            continue
        parts = line.split(None, 8)
        if len(parts) < 9 or len(parts[0]) < 10 or parts[0][0] not in "-dlcbps":
            continue
        perms, _links, owner, group, size, month, day, tod, name = parts
        if name in (".", ".."):
            continue
        try:
            nbytes = int(size)
        except ValueError:
            nbytes = 0
        rows.append((name, _mode_from_perms(perms), nbytes, _parse_time(month, day, tod, now), owner, group))
    return rows
