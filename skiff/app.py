"""Application entry point. Fusion style so KDE, GNOME, and Cinnamon look the same."""

from __future__ import annotations

import os
import sys

from . import APP_ID, APP_NAME, __version__
from .cli import parse_cli
from .qtcompat import QApplication, QIcon, Qt, QTimer


def _force_fusion(app: QApplication) -> None:
    app.setStyle("Fusion")
    # Keep the system palette (KDE dark / GNOME light / Cinnamon) so we
    # do not fight the desktop. Fusion widgets then look like WinSCP on all three.


def _set_name(app: QApplication) -> None:
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName("Anderson Computer")
    app.setOrganizationDomain("andersoncomputer.us")
    try:
        app.setDesktopFileName(APP_ID)
    except Exception:
        pass


def _load_icon() -> QIcon:
    candidates = [
        os.path.join(os.path.dirname(__file__), "icons", "skiff.svg"),
        os.path.join(os.path.dirname(__file__), "icons", "skiff.png"),
        "/usr/share/icons/hicolor/scalable/apps/skiff.svg",
        "/usr/share/pixmaps/skiff.svg",
    ]
    for path in candidates:
        if os.path.isfile(path):
            return QIcon(path)
    return QIcon()


def main(argv=None) -> int:
    argv = list(sys.argv if argv is None else argv)
    argv, target = parse_cli(argv)
    # Wayland + X11 both work with Qt; this keeps GNOME Wayland and KDE Plasma happy.
    os.environ.setdefault("QT_AUTO_SCREEN_SCALE_FACTOR", "1")

    app = QApplication(argv)
    _set_name(app)
    _force_fusion(app)
    icon = _load_icon()
    if not icon.isNull():
        app.setWindowIcon(icon)

    from .main_window import MainWindow

    win = MainWindow()
    if not icon.isNull():
        win.setWindowIcon(icon)
    win.show()
    def _startup():
        win.run_startup_tasks()
        if target:
            win.quick_connect(target)

    QTimer.singleShot(0, _startup)
    try:
        return app.exec_()
    except AttributeError:
        return app.exec()


if __name__ == "__main__":
    sys.exit(main())
