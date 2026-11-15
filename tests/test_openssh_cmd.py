"""OpenSSH backend command lines: password via askpass must reach sftp too."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from skiff import sftp_backend as b  # noqa: E402

SECRET = "cmd_test-pw! x"


class _Done:
    returncode = 0
    stdout = b"/home/u\n"
    stderr = b""


class OpenSSHCommandTest(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.tmp = self._tmpdir.name
        patcher = mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": self.tmp})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.calls = []
        self._real = b.subprocess.run

        def fake(cmd, *a, **k):
            self.calls.append((list(cmd), dict(k.get("env") or {})))
            return _Done()

        b.subprocess.run = fake

    def tearDown(self):
        b.subprocess.run = self._real

    def _connect(self):
        be = b.OpenSSHBackend()
        site = {"host": "h.example", "port": 2200, "username": "u",
                "auth": "password", "password": SECRET, "strict_host": True, "timeout": 5}
        be.connect(site)
        return be

    def test_batchmode_no_precedes_sftp_b(self):
        be = self._connect()
        try:
            be._sftp_batch(["pwd"])
        finally:
            be.close()
        cmd = self.calls[-1][0]
        self.assertEqual(cmd[0], "sftp")
        # sftp expands -b into "-oBatchMode yes" where it sees it; ssh keeps
        # the first value, so our BatchMode=no must come before -b.
        self.assertLess(cmd.index("BatchMode=no"), cmd.index("-b"))
        self.assertIn("-P", cmd)
        self.assertNotIn("-p", cmd)

    def test_password_not_in_argv_or_env(self):
        be = self._connect()
        try:
            be._sftp_batch(["pwd"])
        finally:
            be.close()
        for cmd, env in self.calls:
            self.assertFalse(any(SECRET in x for x in cmd))
            self.assertFalse(any(SECRET in v for v in env.values()))
            self.assertEqual(env.get("SSH_ASKPASS_REQUIRE"), "force")
        self.assertIsNone(be._askpass_token)


if __name__ == "__main__":
    unittest.main()
