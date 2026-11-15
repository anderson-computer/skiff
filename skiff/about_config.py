"""Fixed content for Help > About Skiff."""

from __future__ import annotations

import os

from . import APP_NAME as _APP_NAME
from . import __version__

LOGO_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "skiff.svg")

APP_NAME = _APP_NAME
VERSION = __version__
TAGLINE = "WinSCP-style dual-pane SFTP client for Rocky Linux 9 and 10"
AUTHOR = "Mike Anderson"
COPYRIGHT = "Copyright (c) 2026 Mike Anderson"
LINKS = [
    ("Project page", "https://github.com/mike0615/skiff"),
    ("www.andersoncomputer.net", "https://www.andersoncomputer.net"),
]

LICENSE_NOTICE = (
    "Skiff SFTP is free software, released under the MIT License. You may "
    "use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies "
    "of it, provided the copyright notice and permission notice are included in "
    "all copies or substantial portions of the software.\n\n"
    "Skiff SFTP is provided \"as is\", without warranty of any kind, express "
    "or implied, including but not limited to the warranties of merchantability, "
    "fitness for a particular purpose and noninfringement. See the MIT License "
    "for more details."
)
