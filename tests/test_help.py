#!/usr/bin/env python3
"""Help/About content checks (no Qt needed)."""
import os
import sys
import unittest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skiff import __version__, about_config, help_content  # noqa: E402


class HelpTests(unittest.TestCase):
    def test_topics_cover_required_areas(self):
        headings = " ".join(h for h, _ in help_content.HELP_TOPICS).lower()
        for word in ("connecting", "host keys", "authentication", "browsing",
                     "uploading", "queue", "settings", "troubleshooting"):
            self.assertIn(word, headings)

    def test_shortcuts_include_f1(self):
        self.assertIn("F1", [k for k, _ in help_content.SHORTCUTS])

    def test_help_md_in_sync(self):
        path = os.path.join(ROOT, "HELP.md")
        with open(path, encoding="utf-8") as fh:
            self.assertEqual(fh.read(), help_content.as_markdown())

    def test_about_fields(self):
        self.assertEqual(about_config.VERSION, __version__)
        self.assertEqual(about_config.AUTHOR, "Mike Anderson")
        self.assertIn("MIT License", about_config.LICENSE_NOTICE)
        self.assertTrue(os.path.isfile(about_config.LOGO_FILE))


if __name__ == "__main__":
    unittest.main()
