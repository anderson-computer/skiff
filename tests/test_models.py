#!/usr/bin/env python3
import os
import stat
import sys
import tempfile
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skiff.models import (  # noqa: E402
    FileEntry,
    format_mode,
    format_size,
    local_listdir,
    posix_join,
    posix_parent,
)


class ModelTests(unittest.TestCase):
    def test_posix_join(self):
        self.assertEqual(posix_join("/", "var"), "/var")
        self.assertEqual(posix_join("/home/mike", "docs"), "/home/mike/docs")

    def test_posix_parent(self):
        self.assertIsNone(posix_parent("/"))
        self.assertEqual(posix_parent("/var/log"), "/var")
        self.assertEqual(posix_parent("/var"), "/")

    def test_format_size(self):
        self.assertEqual(format_size(500), "500 B")
        self.assertTrue(format_size(2048).endswith("KB"))

    def test_format_mode(self):
        mode = stat.S_IFREG | 0o644
        self.assertTrue(format_mode(mode).startswith("-"))
        self.assertIn("rw-r--r--", format_mode(mode))

    def test_local_listdir_parent(self):
        with tempfile.TemporaryDirectory() as tmp:
            open(os.path.join(tmp, "a.txt"), "w").write("x")
            os.mkdir(os.path.join(tmp, "sub"))
            os.mkdir(os.path.join(tmp, ".hidden"))
            entries = local_listdir(tmp, show_hidden=False)
            names = [e.name for e in entries]
            self.assertIn("..", names)
            self.assertIn("a.txt", names)
            self.assertIn("sub", names)
            self.assertNotIn(".hidden", names)
            hidden = local_listdir(tmp, show_hidden=True)
            self.assertIn(".hidden", [e.name for e in hidden])

    def test_entry_labels(self):
        e = FileEntry("docs", "/tmp/docs", 0, 0, stat.S_IFDIR | 0o755, True)
        self.assertEqual(e.type_label(), "Folder")
        self.assertEqual(e.size_label(), "<DIR>")


if __name__ == "__main__":
    unittest.main()
