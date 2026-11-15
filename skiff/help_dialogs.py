"""Help > Skiff Help and Help > About Skiff windows."""

from __future__ import annotations

import html
import os

from . import about_config as about
from .help_content import HELP_TOPICS, OVERVIEW, SHORTCUTS
from .qtcompat import (
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QIcon,
    QLabel,
    QTextBrowser,
    QVBoxLayout,
    qt_align,
    qt_dialog_std,
)


def _para(text: str) -> str:
    """Plain help text -> HTML paragraphs, keeping indented bullet lines."""
    out = []
    for block in text.strip("\n").split("\n\n"):
        lines = [html.escape(line) for line in block.split("\n")]
        out.append("<p>" + "<br>".join(l.replace("  ", "&nbsp;&nbsp;") for l in lines) + "</p>")
    return "\n".join(out)


def help_html() -> str:
    parts = ["<h2>%s — Help</h2>" % html.escape(about.APP_NAME), _para(OVERVIEW)]
    parts.append("<h3>Keyboard shortcuts</h3><table cellspacing='0' cellpadding='3'>")
    for keys, desc in SHORTCUTS:
        parts.append("<tr><td><tt><b>%s</b></tt>&nbsp;&nbsp;&nbsp;</td><td>%s</td></tr>"
                     % (html.escape(keys), html.escape(desc)))
    parts.append("</table>")
    parts.append("<h3>Topics</h3><ul>")
    for i, (heading, _body) in enumerate(HELP_TOPICS):
        parts.append("<li><a href='#t%d'>%s</a></li>" % (i, html.escape(heading)))
    parts.append("</ul>")
    for i, (heading, body) in enumerate(HELP_TOPICS):
        parts.append("<h3><a name='t%d'></a>%s</h3>%s" % (i, html.escape(heading), _para(body)))
    return "\n".join(parts)


class HelpDialog(QDialog):
    """Scrollable help page (F1). Non-modal so it can stay open while you work."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("%s Help" % about.APP_NAME)
        self.resize(760, 640)
        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setHtml(help_html())
        layout.addWidget(self.browser, 1)
        box = QDialogButtonBox(qt_dialog_std("Close"))
        box.rejected.connect(self.close)
        box.accepted.connect(self.close)
        layout.addWidget(box)


class AboutDialog(QDialog):
    """Logo, name, version, tagline, author, links and license notice."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("About %s" % about.APP_NAME)
        self.setMinimumWidth(520)
        center = qt_align("AlignHCenter")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 16)
        layout.setSpacing(8)

        self.logo = QLabel()
        self.logo.setAlignment(center)
        if os.path.isfile(about.LOGO_FILE):
            pix = QIcon(about.LOGO_FILE).pixmap(128, 128)
            if not pix.isNull():
                self.logo.setPixmap(pix)
        layout.addWidget(self.logo)

        self.name = QLabel("<span style='font-size:18pt; font-weight:bold'>%s</span>"
                           % html.escape(about.APP_NAME))
        self.version = QLabel("Version %s" % about.VERSION)
        self.tagline = QLabel(about.TAGLINE)
        self.author = QLabel("Author: %s" % about.AUTHOR)
        self.copyright = QLabel(about.COPYRIGHT)
        for w in (self.name, self.version, self.tagline, self.author, self.copyright):
            w.setAlignment(center)
            layout.addWidget(w)
        self.version.setEnabled(False)  # dim, like the reference About page

        links = QHBoxLayout()
        links.addStretch(1)
        self.link_labels = []
        for label, url in about.LINKS:
            lbl = QLabel("<a href='%s'>%s</a>" % (html.escape(url, quote=True), html.escape(label)))
            lbl.setOpenExternalLinks(True)
            links.addWidget(lbl)
            self.link_labels.append(lbl)
        links.addStretch(1)
        layout.addLayout(links)

        self.license = QLabel(about.LICENSE_NOTICE)
        self.license.setWordWrap(True)
        self.license.setAlignment(center)
        self.license.setEnabled(False)
        layout.addSpacing(12)
        layout.addWidget(self.license)

        box = QDialogButtonBox(qt_dialog_std("Close"))
        box.rejected.connect(self.close)
        box.accepted.connect(self.close)
        layout.addWidget(box)
