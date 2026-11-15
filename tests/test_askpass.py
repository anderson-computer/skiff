#!/usr/bin/env python3
"""askpass helper <-> in-process server round trip. No Qt needed."""
import os
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skiff.askpass_server import HELPER, AskpassServer, password_handler  # noqa: E402


class AskpassTests(unittest.TestCase):
    def test_helper_round_trip(self):
        with tempfile.TemporaryDirectory() as d, mock.patch.dict(os.environ, {"XDG_RUNTIME_DIR": d}):
            srv = AskpassServer()
            srv.start()
            self.addCleanup(srv.stop)
            token = srv.register(password_handler("s3cret_pw!"))
            env = dict(os.environ, **srv.env_for(token))
            self.assertNotIn("s3cret_pw!", "".join(env.values()))

            def run(tok, prompt="bob@h's password: ", kind=""):
                e = dict(env, SKIFF_ASKPASS_TOKEN=tok, SSH_ASKPASS_PROMPT=kind)
                return subprocess.run([sys.executable, HELPER, prompt], env=e,
                                      capture_output=True, text=True, timeout=10)

            good = run(token)
            self.assertEqual(good.returncode, 0, good.stderr)
            self.assertEqual(good.stdout, "s3cret_pw!\n")
            bad = run("not-a-token")
            self.assertNotEqual(bad.returncode, 0)
            self.assertEqual(bad.stdout, "")
            confirm = run(token, "Are you sure you want to continue connecting (yes/no)?")
            self.assertNotEqual(confirm.returncode, 0)  # never answers host-key questions
            srv.unregister(token)
            self.assertNotEqual(run(token).returncode, 0)
            self.assertEqual(oct(os.stat(os.path.join(d, "skiff")).st_mode & 0o777), "0o700")
            self.assertEqual(oct(os.stat(srv.path).st_mode & 0o777), "0o600")

    def test_helper_is_executable(self):
        self.assertTrue(os.access(HELPER, os.X_OK))


if __name__ == "__main__":
    unittest.main()
