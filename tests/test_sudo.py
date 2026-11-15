"""sudo mode: command construction, sftp-server detection, error mapping,
listing parser, and both backends' wiring (no network)."""
import io
import os
import stat
import subprocess
import sys
import tempfile
import time
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skiff import sudo  # noqa: E402
from skiff import sftp_backend as b  # noqa: E402
from skiff.config import default_site  # noqa: E402

RHEL = "/usr/libexec/openssh/sftp-server"


class CommandTests(unittest.TestCase):
    def test_command(self):
        self.assertEqual(sudo.sudo_command("root", RHEL), "sudo -n -u root " + RHEL)
        self.assertEqual(sudo.sudo_command("svc-app", "/opt/x/sftp-server"),
                         "sudo -n -u svc-app /opt/x/sftp-server")

    def test_always_non_interactive(self):
        self.assertIn(" -n ", sudo.sudo_command("root", RHEL))

    def test_rejects_injection(self):
        for user in ("root;id", "ro ot", "$(id)", "-u", "", "a" * 40):
            with self.assertRaises(sudo.SudoConfigError, msg=user):
                sudo.sudo_command(user, RHEL)
        for path in ("relative/sftp-server", "/x;id", "/a b", "/x$(id)", "", "/x`id`"):
            with self.assertRaises(sudo.SudoConfigError, msg=path):
                sudo.sudo_command("root", path)

    def test_site_defaults(self):
        site = default_site()
        self.assertFalse(site["sudo"])
        self.assertFalse(sudo.enabled(site))
        self.assertEqual(sudo.sudo_user(site), "root")
        self.assertEqual(sudo.server_path(site), "")
        site.update(sudo=True, sudo_user=" backup ", sftp_server=" /usr/lib/ssh/sftp-server ")
        self.assertEqual(sudo.sudo_user(site), "backup")
        self.assertEqual(sudo.server_path(site), "/usr/lib/ssh/sftp-server")
        site["sftp_server"] = "/usr/../tmp/evil"
        with self.assertRaises(sudo.SudoConfigError):
            sudo.server_path(site)

    def test_sudoers_line(self):
        self.assertEqual(sudo.sudoers_line("mike", "root", RHEL),
                         "mike ALL=(root) NOPASSWD: " + RHEL)


class DetectTests(unittest.TestCase):
    def test_candidates_order(self):
        self.assertEqual(sudo.SFTP_SERVER_CANDIDATES,
                         (RHEL, "/usr/lib/openssh/sftp-server", "/usr/lib/ssh/sftp-server"))

    def test_script_picks_first_executable(self):
        with tempfile.TemporaryDirectory() as d:
            a, b_, c = (os.path.join(d, n) for n in ("a", "b", "c"))
            for p, mode in ((a, 0o644), (b_, 0o755), (c, 0o755)):
                open(p, "w").close()
                os.chmod(p, mode)
            out = subprocess.run(["sh", "-c", sudo.detect_script([os.path.join(d, "missing"), a, b_, c])],
                                 stdout=subprocess.PIPE, check=True).stdout.decode()
            self.assertEqual(sudo.parse_detect("/home/u\n" + out), b_)

    def test_script_none(self):
        out = subprocess.run(["sh", "-c", sudo.detect_script(["/nonexistent/sftp-server"])],
                             stdout=subprocess.PIPE, check=True).stdout.decode()
        self.assertEqual(out, "")
        self.assertEqual(sudo.parse_detect(out), "")
        self.assertIn(RHEL, sudo.not_found_message())

    def test_parse_rejects_garbage(self):
        self.assertEqual(sudo.parse_detect(sudo.DETECT_MARK + "/x;rm -rf /"), "")


class ErrorTests(unittest.TestCase):
    def test_password_required(self):
        msg = sudo.explain_failure("sudo: a password is required\nConnection closed\n", "tester", "root", RHEL)
        self.assertIn(sudo.PASSWORD_HINT, msg)
        self.assertIn("tester ALL=(root) NOPASSWD: " + RHEL, msg)

    def test_not_allowed(self):
        msg = sudo.explain_failure(
            "Sorry, user tester is not allowed\nsudo: sorry, user tester is not allowed to execute", "tester", "root", RHEL)
        self.assertIn("may not run", msg)

    def test_unknown_user(self):
        msg = sudo.explain_failure("sudo: unknown user nobody2", "t", "nobody2", RHEL)
        self.assertIn("does not exist", msg)

    def test_not_sudo(self):
        self.assertIsNone(sudo.explain_failure("Permission denied (publickey).", "t", "root", RHEL))
        self.assertFalse(sudo.is_sudo_failure("Connection closed"))


class ParseLsTests(unittest.TestCase):
    OUT = (
        "sftp> cd '/srv/root only'\n"
        "sftp> ls -la\n"
        "drwx------    ? root     root         4096 Nov 15 01:42 .\n"
        "drwxr-xr-x    ? root     root         4096 Nov 15 01:42 ..\n"
        "-rw-r--r--    ? root     root            3 Nov 15 01:42 a  file.txt\n"
        "lrwxrwxrwx    ? root     wheel           4 Dec 31  2024 lnk\n"
        "drwsr-sr-t    ? 0        0            4096 Jan  2 03:04 .hidden dir\n"
    )

    def test_parse(self):
        now = time.mktime((2026, 11, 15, 12, 0, 0, 0, 0, -1))
        rows = {r[0]: r for r in sudo.parse_ls(self.OUT, now=now)}
        self.assertEqual(set(rows), {"a  file.txt", "lnk", ".hidden dir"})
        name, mode, size, mtime, owner, group = rows["a  file.txt"]
        self.assertTrue(stat.S_ISREG(mode))
        self.assertEqual(stat.S_IMODE(mode), 0o644)
        self.assertEqual((size, owner, group), (3, "root", "root"))
        self.assertEqual(time.localtime(mtime)[:5], (2026, 11, 15, 1, 42))
        self.assertTrue(stat.S_ISLNK(rows["lnk"][1]))
        self.assertEqual(time.localtime(rows["lnk"][3])[:3], (2024, 12, 31))
        hid = rows[".hidden dir"][1]
        self.assertTrue(stat.S_ISDIR(hid))
        self.assertEqual(stat.S_IMODE(hid), 0o7755)
        # "Jan 2 03:04" is after "now" (Nov) -> previous year
        self.assertEqual(time.localtime(rows[".hidden dir"][3]).tm_year, 2026)


class _Proc:
    def __init__(self, rc=0, out=b"", err=b""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class OpenSSHSudoTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.sftp_reply = _Proc(0, b"sftp> pwd\nRemote working directory: /home/tester\n")
        real = b.subprocess.run

        def fake(cmd, *a, **k):
            self.calls.append((list(cmd), k.get("input")))
            if cmd[0] == "ssh":
                return _Proc(0, b"/home/tester\n" + (sudo.DETECT_MARK + RHEL + "\n").encode())
            reply = self.sftp_reply
            return reply(k.get("input") or b"") if callable(reply) else reply

        b.subprocess.run = fake
        self.addCleanup(setattr, b.subprocess, "run", real)

    def site(self, **kw):
        s = {"host": "h.example", "port": 2200, "username": "tester", "auth": "agent",
             "strict_host": True, "timeout": 5, "sudo": True}
        s.update(kw)
        return s

    def test_connect_detects_and_uses_sudo(self):
        be = b.OpenSSHBackend()
        self.assertEqual(be.connect(self.site()), "/home/tester")
        self.assertEqual(be.sudo_user, "root")
        ssh_cmd = self.calls[0][0]
        self.assertEqual(ssh_cmd[0], "ssh")
        self.assertIn(RHEL, ssh_cmd[-1])  # detection script, quoted for the remote shell
        sftp_cmd = self.calls[1][0]
        self.assertEqual(sftp_cmd[0], "sftp")
        i_s, i_b = sftp_cmd.index("-s"), sftp_cmd.index("-b")
        self.assertEqual(sftp_cmd[i_s + 1], "sudo -n -u root " + RHEL)
        self.assertLess(sftp_cmd.index("-P"), i_b)
        self.assertLess(i_s, i_b)
        self.assertEqual(sftp_cmd[-1], "tester@h.example")
        be.close()
        self.assertEqual(be.sudo_user, "")

    def test_configured_path_skips_detection(self):
        be = b.OpenSSHBackend()
        be.connect(self.site(sudo_user="backup", sftp_server="/usr/lib/ssh/sftp-server"))
        self.assertEqual(self.calls[0][0][-1], "pwd")
        self.assertIn("sudo -n -u backup /usr/lib/ssh/sftp-server", self.calls[1][0])
        self.assertEqual(be.sudo_user, "backup")

    def test_no_sudo_has_no_s_flag(self):
        be = b.OpenSSHBackend()
        be.connect(self.site(sudo=False))
        be._sftp_batch(["pwd"])
        self.assertNotIn("-s", self.calls[-1][0])
        self.assertEqual(be.sudo_user, "")

    def test_password_required_error(self):
        self.sftp_reply = _Proc(255, b"", b"sudo: a password is required\nConnection closed\n")
        be = b.OpenSSHBackend()
        with self.assertRaises(b.SftpError) as cm:
            be.connect(self.site())
        self.assertIn(sudo.PASSWORD_HINT, str(cm.exception))
        self.assertIn("tester ALL=(root) NOPASSWD: " + RHEL, str(cm.exception))
        self.assertEqual(be.sudo_user, "")

    def test_bad_settings_rejected_before_running_anything(self):
        with self.assertRaises(b.SftpError):
            b.OpenSSHBackend().connect(self.site(sudo_user="root; id"))
        self.assertEqual(self.calls, [])

    def test_listing_and_rmtree_go_through_sftp(self):
        be = b.OpenSSHBackend()
        be.connect(self.site())
        self.sftp_reply = _Proc(0, ParseLsTests.OUT.encode())
        names = [e.name for e in be.listdir("/srv/root only", True)]
        self.assertEqual(names[0], "..")
        self.assertIn("a  file.txt", names)
        self.assertEqual(self.calls[-1][1].decode().splitlines(), ["cd '/srv/root only'", "ls -la"])
        self.assertNotIn(".hidden dir", [e.name for e in be.listdir("/srv/root only", False)])
        self.sftp_reply = lambda body: _Proc(0, b"" if b".hidden dir" in body else ParseLsTests.OUT.encode())
        lines = be._rmtree_lines("/srv/root only")
        self.assertIn("rmdir '/srv/root only/.hidden dir'", lines)
        self.assertLess(lines.index("rmdir '/srv/root only/.hidden dir'"), len(lines) - 1)
        self.assertIn("rm '/srv/root only/a  file.txt'", lines)
        self.assertIn("rm '/srv/root only/lnk'", lines)  # links are removed, never followed
        self.assertEqual(lines[-1], "rmdir '/srv/root only'")


class _Chan:
    def __init__(self, stderr=b""):
        self.cmd = None
        self._err = io.BytesIO(stderr)
        self.closed = False
        self.timeout = "unset"

    def settimeout(self, t):
        self.timeout = t

    def exec_command(self, cmd):
        self.cmd = cmd

    def recv_stderr_ready(self):
        return self._err.tell() < len(self._err.getvalue())

    def recv_stderr(self, n):
        return self._err.read(n)

    def exit_status_ready(self):
        return True

    def close(self):
        self.closed = True


class _Client:
    def __init__(self, chan, detect=RHEL):
        self.chan, self.detect, self.execs = chan, detect, []

    def exec_command(self, cmd, timeout=None):
        self.execs.append(cmd)
        out = io.BytesIO(((sudo.DETECT_MARK + self.detect + "\n") if self.detect else "").encode())
        return None, out, None

    def get_transport(self):
        client = self

        class T:
            def open_session(self, timeout=None):
                return client.chan
        return T()


class ParamikoSudoTests(unittest.TestCase):
    def test_opens_sftp_over_sudo_channel(self):
        chan = _Chan()
        fake = mock.Mock()
        fake.SFTPClient.side_effect = lambda c: ("sftp-over", c)
        sftp, user = b.ParamikoBackend._open_sudo_sftp(fake, _Client(chan), {"sudo": True}, "tester", 5)
        self.assertEqual(user, "root")
        self.assertEqual(chan.cmd, "sudo -n -u root " + RHEL)
        self.assertEqual(sftp, ("sftp-over", chan))
        self.assertIsNone(chan.timeout)  # no timeout on the long-lived SFTP stream

    def test_configured_path_and_user(self):
        chan = _Chan()
        client = _Client(chan)
        fake = mock.Mock()
        b.ParamikoBackend._open_sudo_sftp(
            fake, client, {"sudo": True, "sudo_user": "backup", "sftp_server": "/opt/s/sftp-server"}, "t", 5)
        self.assertEqual(client.execs, [])
        self.assertEqual(chan.cmd, "sudo -n -u backup /opt/s/sftp-server")

    def test_password_required(self):
        chan = _Chan(b"sudo: a password is required\n")
        fake = mock.Mock()
        fake.SFTPClient.side_effect = EOFError("EOF during negotiation")
        with self.assertRaises(b.SftpError) as cm:
            b.ParamikoBackend._open_sudo_sftp(fake, _Client(chan), {"sudo": True}, "tester", 5)
        self.assertIn(sudo.PASSWORD_HINT, str(cm.exception))
        self.assertTrue(chan.closed)

    def test_server_not_found(self):
        with self.assertRaises(b.SftpError) as cm:
            b.ParamikoBackend._open_sudo_sftp(mock.Mock(), _Client(_Chan(), detect=""), {"sudo": True}, "t", 5)
        self.assertIn("Could not find sftp-server", str(cm.exception))


if __name__ == "__main__":
    unittest.main()
