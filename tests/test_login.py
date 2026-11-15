"""Login plumbing without Qt: host keys, auth error mapping, OpenSSH options."""
import os
import stat
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skiff import hostkeys  # noqa: E402
from skiff import sftp_backend as b  # noqa: E402

# A real ed25519 public key blob (test key, not used anywhere).
ED_B64 = "AAAAC3NzaC1lZDI1NTE5AAAAIGb2b2uW7dXrB2y3Zr8Qm7q8m3m1d9vT8v4jJ8s3Qk8x"


class HostKeyTests(unittest.TestCase):
    def test_entry(self):
        self.assertEqual(hostkeys.host_entry("h", 22), "h")
        self.assertEqual(hostkeys.host_entry("h", 2222), "[h]:2222")

    def test_fingerprint_matches_ssh_keygen(self):
        with tempfile.TemporaryDirectory() as d:
            key = os.path.join(d, "k")
            try:
                subprocess.run(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", key], check=True)
                want = subprocess.run(["ssh-keygen", "-lf", key + ".pub"], stdout=subprocess.PIPE,
                                      check=True).stdout.decode().split()[1]
            except (OSError, subprocess.CalledProcessError):
                self.skipTest("ssh-keygen not available")
            blob = open(key + ".pub").read().split()[1]
            self.assertEqual(hostkeys.fingerprint(blob), want)

    def test_add_known_host_creates_private_file_and_appends(self):
        with tempfile.TemporaryDirectory() as d:
            path = os.path.join(d, "ssh", "known_hosts")
            hostkeys.add_known_host("h", 2222, "ssh-ed25519", ED_B64, path=path)
            self.assertEqual(stat.S_IMODE(os.stat(os.path.dirname(path)).st_mode), 0o700)
            self.assertEqual(stat.S_IMODE(os.stat(path).st_mode), 0o600)
            with open(path, "a") as fh:
                fh.write("other ssh-rsa AAAA")  # no trailing newline
            hostkeys.add_known_host("h2", 22, "ssh-ed25519", ED_B64, path=path)
            lines = open(path).read().splitlines()
            self.assertEqual(lines, ["[h]:2222 ssh-ed25519 " + ED_B64, "other ssh-rsa AAAA",
                                     "h2 ssh-ed25519 " + ED_B64])

    def test_add_rejects_garbage(self):
        with tempfile.TemporaryDirectory() as d:
            for kt, kb in (("ssh-ed25519", "AAAA\nevil"), ("a b", ED_B64), ("ssh-ed25519", "!!!")):
                with self.assertRaises(Exception):
                    hostkeys.add_known_host("h", 22, kt, kb, path=os.path.join(d, "kh"))

    def test_parse_keyscan_prefers_ed25519(self):
        out = ("# h:22 SSH-2.0\n[h]:2 ssh-rsa RSAKEY\n[h]:2 ecdsa-sha2-nistp256 ECKEY\n"
               "[h]:2 ssh-ed25519 EDKEY\n")
        self.assertEqual(hostkeys.parse_keyscan(out)[0], ("ssh-ed25519", "EDKEY"))
        self.assertEqual(hostkeys.parse_keyscan(""), [])


class _Proc:
    def __init__(self, rc=0, out=b"", err=b""):
        self.returncode, self.stdout, self.stderr = rc, out, err


class OpenSSHLoginTests(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.reply = _Proc(0, b"/home/u\n")
        real = b.subprocess.run

        def fake(cmd, *a, **k):
            self.calls.append((list(cmd), k))
            return self.reply

        b.subprocess.run = fake
        self.addCleanup(setattr, b.subprocess, "run", real)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        p = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.tmp.name})
        p.start()
        self.addCleanup(p.stop)

    def site(self, **kw):
        s = {"host": "h", "port": 2222, "username": "u", "auth": "password", "timeout": 5, "strict_host": True}
        s.update(kw)
        return s

    def test_never_reads_a_terminal(self):
        be = b.OpenSSHBackend()
        be.connect(self.site(password="pw_x"))
        cmd, kw = self.calls[0]
        self.assertIs(kw.get("stdin"), subprocess.DEVNULL)
        self.assertTrue(kw.get("start_new_session"))
        self.assertEqual(kw["env"]["SSH_ASKPASS_REQUIRE"], "force")
        self.assertIn("BatchMode=no", cmd)
        self.assertIn("PreferredAuthentications=password,keyboard-interactive", cmd)
        self.assertIn("PubkeyAuthentication=no", cmd)
        be.close()

    def test_no_password_means_batch_mode(self):
        be = b.OpenSSHBackend()
        be.connect(self.site(auth="agent"))
        cmd = self.calls[0][0]
        self.assertIn("BatchMode=yes", cmd)
        self.assertNotIn("PubkeyAuthentication=no", cmd)

    def test_permission_denied_is_auth_error(self):
        self.reply = _Proc(255, b"", b"u@h: Permission denied (publickey,password).\n")
        with self.assertRaises(b.AuthError):
            b.OpenSSHBackend().connect(self.site(password="wrong"))

    def test_unknown_host_key(self):
        self.reply = _Proc(255, b"", b"No ED25519 host key is known for [h]:2222 and you have requested "
                                     b"strict checking.\nHost key verification failed.\n")
        with mock.patch.object(hostkeys, "scan", return_value=[("ssh-ed25519", ED_B64)]):
            with self.assertRaises(b.UnknownHostKey) as cm:
                b.OpenSSHBackend().connect(self.site(password="pw"))
        e = cm.exception
        self.assertEqual((e.host, e.port, e.key_type), ("h", 2222, "ssh-ed25519"))
        self.assertTrue(e.fingerprint.startswith("SHA256:"))
        self.assertNotIsInstance(e, b.AuthError)

    def test_changed_host_key_is_a_plain_error(self):
        self.reply = _Proc(255, b"", b"@@@ WARNING: REMOTE HOST IDENTIFICATION HAS CHANGED! @@@\n"
                                     b"Host key verification failed.\n")
        with self.assertRaises(b.SftpError) as cm:
            b.OpenSSHBackend().connect(self.site())
        self.assertIn("mismatch", str(cm.exception))
        self.assertNotIsInstance(cm.exception, (b.AuthError, b.UnknownHostKey))

    def test_rejects_option_like_names(self):
        for kw in ({"host": "-oProxyCommand=id"}, {"username": "-oProxyCommand=id"}):
            with self.assertRaises(b.SftpError):
                b.OpenSSHBackend().connect(self.site(**kw))
        self.assertEqual(self.calls, [])


if __name__ == "__main__":
    unittest.main()
