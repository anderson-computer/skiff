#!/usr/bin/env python3
"""Headless smoke test: main window, Help page and About page (QT_QPA_PLATFORM=offscreen)."""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

ROOT = os.environ.get("SKIFF_ROOT") or os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from skiff import about_config  # noqa: E402
from skiff.help_content import HELP_TOPICS  # noqa: E402
from skiff.help_dialogs import AboutDialog, HelpDialog  # noqa: E402
from skiff.main_window import MainWindow  # noqa: E402
from skiff.qtcompat import QApplication, QT_VERSION  # noqa: E402


def main():
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    win = MainWindow()
    win.show()
    app.processEvents()
    print("QT_VERSION", QT_VERSION)
    print("title", win.windowTitle())
    print("local_path", win.local.path)

    # Help menu wiring
    menus = {a.text().replace("&", ""): a for a in win.menuBar().actions()}
    help_actions = [a.text().replace("&", "") for a in menus["Help"].menu().actions() if a.text()]
    print("help_menu", help_actions)
    assert "Skiff Help" in help_actions and "About Skiff" in help_actions, help_actions
    assert win.act_help.shortcut().toString() == "F1", win.act_help.shortcut().toString()

    # Help page via the real slot (non-modal)
    win.act_help.trigger()
    app.processEvents()
    hd = win._help_dlg
    assert isinstance(hd, HelpDialog) and hd.isVisible()
    text = hd.browser.toPlainText()
    for heading, _ in HELP_TOPICS:
        assert heading in text, heading
    print("help_dialog OK", hd.windowTitle(), len(text), "chars,", len(HELP_TOPICS), "topics")
    hd.close()

    # About page (constructed directly; the menu action runs it modally)
    ad = AboutDialog(win)
    ad.show()
    app.processEvents()
    assert about_config.APP_NAME in ad.name.text()
    assert ad.version.text() == "Version " + about_config.VERSION
    assert ad.author.text() == "Author: Mike Anderson"
    assert len(ad.link_labels) == len(about_config.LINKS)
    print("about_dialog OK", ad.windowTitle(), "|", ad.version.text(), "|", ad.author.text(),
          "| logo", "yes" if ad.logo.pixmap() is not None and not ad.logo.pixmap().isNull() else "no (qtsvg missing?)")
    ad.close()

    print("SMOKE OK")
    win.close()
    win.thread.quit()
    win.thread.wait(2000)
    return 0


if __name__ == "__main__":
    sys.exit(main())
