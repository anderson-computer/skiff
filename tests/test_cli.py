"""Command line (skiff --host/--user/--port, sftp:// URLs) and target parsing. No Qt."""
import contextlib
import io
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skiff.cli import parse_cli  # noqa: E402
from skiff.target import TargetError, parse_target  # noqa: E402


def _cli(*args):
    return parse_cli(["skiff"] + list(args))


def _cli_error(*args):
    err = io.StringIO()
    with contextlib.redirect_stderr(err), unittest.TestCase().assertRaises(SystemExit) as cm:
        _cli(*args)
    return cm.exception.code, err.getvalue()


class CliTests(unittest.TestCase):
    def test_no_args(self):
        self.assertEqual(_cli(), (["skiff"], None))

    def test_host_user_port(self):
        argv, t = _cli("--host", "files.example.com", "--user", "mike", "--port", "2222")
        self.assertEqual(argv, ["skiff"])
        self.assertEqual(t, {"host": "files.example.com", "port": 2222, "username": "mike", "remote_dir": ""})

    def test_sonar_template_with_empty_values(self):
        # skiff_args=--host {host} --user {user} --port {port} with user/port unknown
        self.assertEqual(_cli("--host", "10.0.0.5", "--user", "--port")[1],
                         {"host": "10.0.0.5", "port": 22, "username": "", "remote_dir": ""})
        self.assertEqual(_cli("--host", "10.0.0.5", "--user", "", "--port", "")[1]["port"], 22)

    def test_equals_form_and_user_at_host(self):
        t = _cli("--host=mike@h:2200")[1]
        self.assertEqual((t["username"], t["host"], t["port"]), ("mike", "h", 2200))
        t = _cli("--host", "mike@h:2200", "--user", "bob", "--port", "22")[1]
        self.assertEqual((t["username"], t["port"]), ("bob", 22))  # explicit options win

    def test_url(self):
        argv, t = _cli("sftp://mike@h.example:2200/var/www", "-platform", "offscreen")
        self.assertEqual(argv, ["skiff", "-platform", "offscreen"])
        self.assertEqual(t, {"host": "h.example", "port": 2200, "username": "mike", "remote_dir": "/var/www"})

    def test_qt_args_pass_through(self):
        argv, t = _cli("-platform", "offscreen", "--host", "h", "-style", "fusion")
        self.assertEqual(argv, ["skiff", "-platform", "offscreen", "-style", "fusion"])
        self.assertEqual(t["host"], "h")

    def test_errors(self):
        for args in (["--host", "h:99999"], ["--host", "h", "--port", "x"], ["--user", "mike"],
                     ["--host", "-oProxyCommand=id"], ["--host=-oProxyCommand=id"], ["ftp://h"],
                     ["sftp://a", "sftp://b"], ["--host", "h", "sftp://h"]):
            code, err = _cli_error(*args)
            self.assertEqual(code, 2, args)
            self.assertIn("usage:", err)

    def test_version_and_help(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            _cli("--help")
        self.assertIn("--host", out.getvalue())
        self.assertIn("sftp://", out.getvalue())


class TargetTests(unittest.TestCase):
    def test_forms(self):
        cases = {
            "h": ("h", 22, ""),
            "h:2200": ("h", 2200, ""),
            "bob@h": ("h", 22, "bob"),
            "bob@corp@h:23": ("h", 23, "bob@corp"),
            "[::1]:2222": ("::1", 2222, ""),
            "bob@[fe80::1%eth0]": ("fe80::1%eth0", 22, "bob"),
            "::1": ("::1", 22, ""),
            "sftp://h": ("h", 22, ""),
            "ssh://bob%40corp@h:2": ("h", 2, "bob@corp"),
        }
        for text, (host, port, user) in cases.items():
            t = parse_target(text)
            self.assertEqual((t["host"], t["port"], t["username"]), (host, port, user), text)

    def test_url_path(self):
        self.assertEqual(parse_target("sftp://h/srv/a%20b")["remote_dir"], "/srv/a b")
        self.assertEqual(parse_target("sftp://h/~/x")["remote_dir"], "")

    def test_rejects(self):
        for bad in ("", " ", "-oProxyCommand=x", "h:0", "h:abc", "a b", "http://h", "[::1", "bob x@h"):
            with self.assertRaises(TargetError, msg=bad):
                parse_target(bad)



class CredentialHandoffTests(unittest.TestCase):
    """--key and --password-fd (used by Porthole's Open in Skiff)."""

    def _pipe(self, data):
        r, w = os.pipe()
        os.write(w, data)
        os.close(w)
        return r

    def test_password_fd_read_and_closed(self):
        r = self._pipe(b"s3cret pw\n")
        argv, t = _cli("--host", "h", "--user", "u", "--password-fd", str(r))
        self.assertEqual(t["password"], "s3cret pw")
        self.assertNotIn("s3cret pw", " ".join(argv))
        with self.assertRaises(OSError):
            os.fstat(r)  # closed after reading

    def test_password_fd_keeps_inner_whitespace(self):
        r = self._pipe(b" a b \r\n")
        self.assertEqual(_cli("--host", "h", "--password-fd", str(r))[1]["password"], " a b ")

    def test_password_fd_errors(self):
        code, err = _cli_error("--host", "h", "--password-fd", "987")
        self.assertEqual(code, 2)
        self.assertIn("--password-fd", err)
        code, _ = _cli_error("--password-fd", "3")  # needs --host
        self.assertEqual(code, 2)
        code, err = _cli_error("--host", "h", "--password-fd", "2")  # stderr is never read
        self.assertIn("invalid file descriptor", err)

    def test_key(self):
        import tempfile
        with tempfile.NamedTemporaryFile() as f:
            t = _cli("--host", "h", "--key", f.name)[1]
            self.assertEqual(t["key_file"], f.name)
        code, err = _cli_error("--host", "h", "--key", "/nonexistent/key")
        self.assertIn("key file not found", err)

    def test_apply_cli_credentials(self):
        try:
            from skiff.main_window import MainWindow
        except Exception as exc:  # no Qt in this environment
            self.skipTest("Qt not available: %s" % exc)
        site = {"auth": "agent", "password": "", "save_password": True, "key_file": ""}
        out = MainWindow._apply_cli_credentials(dict(site), {"password": "pw"})
        self.assertEqual((out["auth"], out["password"], out["save_password"]), ("password", "pw", False))
        out = MainWindow._apply_cli_credentials(dict(site), {"key_file": "/k"})
        self.assertEqual((out["auth"], out["key_file"]), ("key", "/k"))
        out = MainWindow._apply_cli_credentials(dict(site), {"password": ""})
        self.assertEqual((out["auth"], out["save_password"]), ("agent", True))  # empty pipe: unchanged


if __name__ == "__main__":
    unittest.main()
