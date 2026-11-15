"""Main commander window — dual pane, queue, F-keys, site manager."""

from __future__ import annotations

import os
import shutil
from typing import Dict, List, Optional

from . import APP_NAME, __version__
from .config import load_settings, load_sites, save_settings
from .file_panel import FilePanel
from .models import FileEntry, posix_join
from .qtcompat import (
    QAction,
    QApplication,
    QCheckBox,
    QDesktopServices,
    QHBoxLayout,
    QInputDialog,
    QKeySequence,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSize,
    QSplitter,
    QStatusBar,
    QTimer,
    QToolBar,
    QUrl,
    QVBoxLayout,
    QWidget,
    Qt,
    pyqtSignal,
    qt_key,
    qt_msg_btn,
    qt_orient,
    qt_shortcut_context,
)
from .site_manager import SiteManagerDialog
from .transfer_queue import TransferQueue
from .worker import SftpWorker, WorkerThread


class MainWindow(QMainWindow):
    req_connect = pyqtSignal(dict)
    req_disconnect = pyqtSignal()
    req_list = pyqtSignal(str, bool)
    req_mkdir = pyqtSignal(str)
    req_remove = pyqtSignal(str, bool)
    req_rename = pyqtSignal(str, str)
    req_chmod = pyqtSignal(str, int)
    req_download = pyqtSignal(str, str, str, bool)
    req_upload = pyqtSignal(str, str, str, bool)

    def __init__(self):
        super().__init__()
        self.setWindowTitle(APP_NAME)
        self.settings = load_settings()
        self.resize(int(self.settings.get("window_width") or 1200),
                    int(self.settings.get("window_height") or 760))
        self.site: Optional[Dict] = None
        self.remote_home = "/"
        self.connected = False
        self._queue: List[tuple] = []
        self._active_job: Optional[str] = None
        self._pending_refresh = False

        self.worker = SftpWorker()
        self.thread = WorkerThread(self.worker)
        self.thread.start()

        self._build_ui()
        self._connect_signals()
        self._load_initial_local()
        self._set_connected(False)

    # ── UI ────────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        self._build_menus()
        self._build_toolbar()

        central = QWidget()
        self.setCentralWidget(central)
        v = QVBoxLayout(central)
        v.setContentsMargins(6, 4, 6, 4)
        v.setSpacing(4)

        self.splitter = QSplitter(qt_orient("Vertical"))
        panes = QSplitter(qt_orient("Horizontal"))
        self.local = FilePanel("Local", remote=False)
        self.remote = FilePanel("Remote", remote=True)
        panes.addWidget(self.local)
        panes.addWidget(self.remote)
        panes.setStretchFactor(0, 1)
        panes.setStretchFactor(1, 1)
        self.queue = TransferQueue()
        self.splitter.addWidget(panes)
        self.splitter.addWidget(self.queue)
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        self.splitter.setSizes([600, int(self.settings.get("queue_height") or 140)])
        v.addWidget(self.splitter, 1)

        self.fkey = self._build_fkeys()
        v.addWidget(self.fkey)

        status = QStatusBar()
        self.setStatusBar(status)
        self.status_conn = QLabel("Disconnected")
        self.status_proto = QLabel("SFTP")
        self.status_busy = QLabel("")
        status.addWidget(self.status_conn, 1)
        status.addPermanentWidget(self.status_proto)
        status.addPermanentWidget(self.status_busy)

        self.local.set_show_hidden(bool(self.settings.get("show_hidden")))
        self.remote.set_show_hidden(bool(self.settings.get("show_hidden")))

    def _build_menus(self) -> None:
        session = self.menuBar().addMenu("&Session")
        self.act_new = session.addAction("&New Session…")
        self.act_new.setShortcut(QKeySequence("Ctrl+N"))
        self.act_sites = session.addAction("Site &Manager…")
        self.act_sites.setShortcut(QKeySequence("Ctrl+S"))
        session.addSeparator()
        self.act_disconnect = session.addAction("&Disconnect")
        session.addSeparator()
        self.act_quit = session.addAction("E&xit")
        self.act_quit.setShortcuts([QKeySequence("F10"), QKeySequence("Alt+F4")])

        files = self.menuBar().addMenu("&Files")
        self.act_copy = files.addAction("&Copy  (F5)")
        self.act_copy.setShortcut(QKeySequence("F5"))
        self.act_move = files.addAction("&Move  (F6)")
        self.act_move.setShortcut(QKeySequence("F6"))
        self.act_mkdir = files.addAction("&New Folder  (F7)")
        self.act_mkdir.setShortcut(QKeySequence("F7"))
        self.act_delete = files.addAction("&Delete  (F8)")
        self.act_delete.setShortcut(QKeySequence("F8"))
        self.act_rename = files.addAction("&Rename  (F2)")
        self.act_rename.setShortcut(QKeySequence("F2"))
        self.act_props = files.addAction("&Properties  (F9)")
        self.act_props.setShortcut(QKeySequence("F9"))
        files.addSeparator()
        self.act_refresh = files.addAction("Re&fresh")
        self.act_refresh.setShortcut(QKeySequence("Ctrl+R"))

        mark = self.menuBar().addMenu("&Mark")
        self.act_hidden = mark.addAction("Show &hidden files")
        self.act_hidden.setCheckable(True)
        self.act_hidden.setChecked(bool(self.settings.get("show_hidden")))

        opts = self.menuBar().addMenu("&Options")
        self.act_confirm = opts.addAction("&Confirm deletes")
        self.act_confirm.setCheckable(True)
        self.act_confirm.setChecked(bool(self.settings.get("confirm_delete", True)))

        helpm = self.menuBar().addMenu("&Help")
        self.act_help = helpm.addAction("Skiff &Help")
        self.act_help.setShortcut(QKeySequence("F1"))
        self.act_help.setShortcutContext(qt_shortcut_context("WindowShortcut"))
        helpm.addSeparator()
        self.act_about = helpm.addAction("&About Skiff")

        for act in (
            self.act_copy, self.act_move, self.act_mkdir, self.act_delete,
            self.act_rename, self.act_props, self.act_refresh,
        ):
            act.setShortcutContext(qt_shortcut_context("WindowShortcut"))

    def _build_toolbar(self) -> None:
        bar = QToolBar("Main")
        bar.setMovable(False)
        bar.setIconSize(QSize(20, 20))
        self.addToolBar(bar)
        bar.addAction(self.act_new)
        bar.addAction(self.act_sites)
        bar.addAction(self.act_disconnect)
        bar.addSeparator()
        bar.addAction(self.act_refresh)
        bar.addAction(self.act_copy)
        bar.addAction(self.act_mkdir)
        bar.addAction(self.act_delete)
        bar.addSeparator()
        bar.addAction(self.act_hidden)

    def _build_fkeys(self) -> QWidget:
        box = QWidget()
        row = QHBoxLayout(box)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        specs = [
            ("F2 Rename", self._rename),
            ("F5 Copy", self._copy),
            ("F6 Move", self._move),
            ("F7 New Folder", self._mkdir),
            ("F8 Delete", self._delete),
            ("F9 Properties", self._props),
            ("F10 Quit", self.close),
        ]
        self._fkey_btns = []
        for text, slot in specs:
            btn = QPushButton(text)
            btn.setAutoDefault(False)
            btn.clicked.connect(slot)
            row.addWidget(btn, 1)
            self._fkey_btns.append(btn)
        return box

    def _connect_signals(self) -> None:
        self.act_new.triggered.connect(self._new_session)
        self.act_sites.triggered.connect(self._open_sites)
        self.act_disconnect.triggered.connect(self._disconnect)
        self.act_quit.triggered.connect(self.close)
        self.act_copy.triggered.connect(self._copy)
        self.act_move.triggered.connect(self._move)
        self.act_mkdir.triggered.connect(self._mkdir)
        self.act_delete.triggered.connect(self._delete)
        self.act_rename.triggered.connect(self._rename)
        self.act_props.triggered.connect(self._props)
        self.act_refresh.triggered.connect(self._refresh_both)
        self.act_hidden.toggled.connect(self._toggle_hidden)
        self.act_confirm.toggled.connect(
            lambda v: self.settings.__setitem__("confirm_delete", bool(v))
        )
        self.act_about.triggered.connect(self._about)
        self.act_help.triggered.connect(self._help)

        self.local.path_changed.connect(lambda p: self.local.set_path(p))
        self.local.activate_entry.connect(self._open_local)
        self.local.transfer_requested.connect(self._drop_on_local)
        self.remote.path_changed.connect(self._remote_cd)
        self.remote.activate_entry.connect(self._open_remote)
        self.remote.transfer_requested.connect(self._drop_on_remote)

        w = self.worker
        self.req_connect.connect(w.do_connect)
        self.req_disconnect.connect(w.do_disconnect)
        self.req_list.connect(w.do_list)
        self.req_mkdir.connect(w.do_mkdir)
        self.req_remove.connect(w.do_remove)
        self.req_rename.connect(w.do_rename)
        self.req_chmod.connect(w.do_chmod)
        self.req_download.connect(w.do_download)
        self.req_upload.connect(w.do_upload)
        w.connected.connect(self._on_connected)
        w.disconnected.connect(self._on_disconnected)
        w.listed.connect(self._on_listed)
        w.error.connect(self._on_error)
        w.busy.connect(self._on_busy)
        w.transfer_progress.connect(self.queue.set_progress)
        w.transfer_done.connect(self._on_transfer_done)
        w.op_done.connect(self._on_op_done)

    def _load_initial_local(self) -> None:
        home = os.path.expanduser("~")
        self.local.set_path(home)

    # ── Session ───────────────────────────────────────────────────────────

    def _new_session(self) -> None:
        self._open_sites()

    def _open_sites(self) -> None:
        dlg = SiteManagerDialog(self, load_sites())
        from .qtcompat import exec_dialog
        if exec_dialog(dlg) and dlg.chosen:
            self._login(dlg.chosen)

    def _login(self, site: Dict) -> None:
        if self.connected:
            self.req_disconnect.emit()
        self.site = site
        local = site.get("local_dir") or os.path.expanduser("~")
        if os.path.isdir(os.path.expanduser(local)):
            self.local.set_path(os.path.expanduser(local))
        self.status_conn.setText("Connecting to %s…" % site.get("host"))
        self.req_connect.emit(site)

    def _disconnect(self) -> None:
        if self.connected:
            self.req_disconnect.emit()

    def _set_connected(self, ok: bool, label: str = "") -> None:
        self.connected = ok
        self.remote.set_connected(ok, label)
        self.act_disconnect.setEnabled(ok)
        for act in (self.act_copy, self.act_move):
            act.setEnabled(ok)
        self.status_conn.setText(label if ok else "Disconnected")
        self.status_proto.setText("SFTP" if ok else "")
        if ok:
            self.setWindowTitle("%s — %s" % (APP_NAME, label))
        else:
            self.setWindowTitle(APP_NAME)
            self.remote.table.set_entries([])
            self.remote.path = ""
            self.remote.path_edit.setText("")

    def _on_connected(self, home: str, label: str) -> None:
        self.remote_home = home or "/"
        self._set_connected(True, label)
        start = (self.site or {}).get("remote_dir") or home
        self.req_list.emit(start, self.act_hidden.isChecked())

    def _on_disconnected(self) -> None:
        self._set_connected(False)

    def _on_listed(self, path: str, entries) -> None:
        self.remote.set_path(path, entries)

    def _on_error(self, message: str) -> None:
        QMessageBox.warning(self, APP_NAME, message)
        self.status_busy.setText("")

    def _on_busy(self, busy: bool, text: str) -> None:
        self.status_busy.setText(text if busy else "")

    def _remote_cd(self, path: str) -> None:
        if not self.connected:
            return
        target = path or self.remote_home
        self.req_list.emit(target, self.act_hidden.isChecked())

    def _refresh_both(self) -> None:
        self.local.refresh()
        if self.connected:
            self.remote.refresh()

    def _toggle_hidden(self, checked: bool) -> None:
        self.settings["show_hidden"] = bool(checked)
        self.local.set_show_hidden(bool(checked))
        self.remote.set_show_hidden(bool(checked))
        self._refresh_both()

    # ── Active pane ───────────────────────────────────────────────────────

    def _active_is_remote(self) -> bool:
        w = QApplication.focusWidget()
        while w is not None:
            if w is self.remote or self.remote.isAncestorOf(w):
                return True
            if w is self.local or self.local.isAncestorOf(w):
                return False
            w = w.parentWidget() if hasattr(w, "parentWidget") else None
        return False

    def _src_panel(self) -> FilePanel:
        return self.remote if self._active_is_remote() else self.local

    def _dst_panel(self) -> FilePanel:
        return self.local if self._active_is_remote() else self.remote

    # ── File operations ───────────────────────────────────────────────────

    def _copy(self) -> None:
        self._transfer(move=False)

    def _move(self) -> None:
        self._transfer(move=True)

    def _transfer(self, move: bool) -> None:
        if not self.connected:
            QMessageBox.information(self, APP_NAME, "Connect to a site first.")
            return
        src_panel = self._src_panel()
        dst_panel = self._dst_panel()
        items = src_panel.selected()
        if not items:
            QMessageBox.information(self, APP_NAME, "Select one or more files.")
            return
        upload = not src_panel.remote
        for entry in items:
            if upload:
                dest = posix_join(dst_panel.path or self.remote_home, entry.name)
                job = self.queue.add_job("Upload" if not move else "Upload+del",
                                         entry.path, dest, entry.size, entry.is_dir)
                self._enqueue(("upload", job, entry.path, dest, entry.is_dir, move, entry.path, False))
            else:
                dest = os.path.join(dst_panel.path, entry.name)
                job = self.queue.add_job("Download" if not move else "Download+del",
                                         entry.path, dest, entry.size, entry.is_dir)
                self._enqueue(("download", job, entry.path, dest, entry.is_dir, move, entry.path, True))
        self._kick_queue()

    def _drop_on_remote(self, paths: List[str]) -> None:
        if not self.connected:
            return
        for path in paths:
            path = path.strip()
            if not path or not os.path.exists(path):
                continue
            name = os.path.basename(path.rstrip("/\\"))
            dest = posix_join(self.remote.path or self.remote_home, name)
            is_dir = os.path.isdir(path)
            size = 0 if is_dir else os.path.getsize(path)
            job = self.queue.add_job("Upload", path, dest, size, is_dir)
            self._enqueue(("upload", job, path, dest, is_dir, False, None, False))
        self._kick_queue()

    def _drop_on_local(self, paths: List[str]) -> None:
        # Remote paths dropped onto local → download those names if they exist remotely.
        if not self.connected:
            return
        remote_names = {e.name: e for e in self.remote.selected()}
        for path in paths:
            name = os.path.basename(path.rstrip("/"))
            entry = remote_names.get(name)
            if entry is None:
                # try treat path as remote path
                if path.startswith("/"):
                    dest = os.path.join(self.local.path, os.path.basename(path))
                    job = self.queue.add_job("Download", path, dest, 0, False)
                    self._enqueue(("download", job, path, dest, False, False, None, False))
            else:
                dest = os.path.join(self.local.path, entry.name)
                job = self.queue.add_job("Download", entry.path, dest, entry.size, entry.is_dir)
                self._enqueue(("download", job, entry.path, dest, entry.is_dir, False, None, False))
        self._kick_queue()

    def _enqueue(self, job: tuple) -> None:
        self._queue.append(job)

    def _kick_queue(self) -> None:
        if self._active_job or not self._queue:
            return
        job = self._queue.pop(0)
        kind, job_id, src, dst, is_dir = job[0], job[1], job[2], job[3], job[4]
        self._active_job = job_id
        self._current_job = job
        if kind == "upload":
            self.req_upload.emit(job_id, src, dst, is_dir)
        else:
            self.req_download.emit(job_id, src, dst, is_dir)

    def _on_transfer_done(self, job_id: str, ok: bool, message: str) -> None:
        self.queue.set_done(job_id, ok, message)
        job = getattr(self, "_current_job", None)
        if ok and job and len(job) >= 8 and job[5]:
            # move: delete source after copy
            src, is_remote_src, is_dir = job[6], job[7], job[4]
            if is_remote_src:
                self.req_remove.emit(src, is_dir)
            else:
                try:
                    if is_dir:
                        shutil.rmtree(src)
                    else:
                        os.remove(src)
                except OSError as exc:
                    QMessageBox.warning(self, APP_NAME, "Copied, but could not remove source:\n%s" % exc)
        dest = None
        if job and len(job) >= 4:
            dest = job[3]
        self._active_job = None
        self._pending_refresh = True
        open_after = getattr(self, "_open_after", None)
        if ok and open_after and dest == open_after and os.path.isfile(open_after):
            self._open_after = None
            QDesktopServices.openUrl(QUrl.fromLocalFile(open_after))
        self._kick_queue()
        if not self._queue:
            self.local.refresh()
            if self.connected:
                self.remote.refresh()

    def _on_op_done(self, kind: str, ok: bool, message: str) -> None:
        if not ok:
            QMessageBox.warning(self, APP_NAME, message)
        if self.connected:
            self.remote.refresh()
        self.local.refresh()

    def _mkdir(self) -> None:
        name, ok = QInputDialog.getText(self, "New Folder", "Folder name:")
        if not ok or not name.strip():
            return
        name = name.strip()
        if self._active_is_remote():
            if not self.connected:
                return
            path = posix_join(self.remote.path or self.remote_home, name)
            self.req_mkdir.emit(path)
        else:
            path = os.path.join(self.local.path, name)
            try:
                os.mkdir(path)
                self.local.refresh()
            except OSError as exc:
                QMessageBox.warning(self, APP_NAME, str(exc))

    def _delete(self) -> None:
        panel = self._src_panel()
        items = panel.selected()
        if not items:
            return
        if self.act_confirm.isChecked():
            names = "\n".join(e.name for e in items[:10])
            extra = "" if len(items) <= 10 else "\n… and %d more" % (len(items) - 10)
            box = QMessageBox(self)
            box.setWindowTitle(APP_NAME)
            box.setText("Delete the selected item(s)?\n\n%s%s" % (names, extra))
            box.setStandardButtons(qt_msg_btn("Yes") | qt_msg_btn("No"))
            box.setDefaultButton(qt_msg_btn("No"))
            from .qtcompat import exec_dialog
            if exec_dialog(box) != qt_msg_btn("Yes"):
                return
        if panel.remote:
            for entry in items:
                self.req_remove.emit(entry.path, entry.is_dir)
        else:
            for entry in items:
                try:
                    if entry.is_dir:
                        shutil.rmtree(entry.path)
                    else:
                        os.remove(entry.path)
                except OSError as exc:
                    QMessageBox.warning(self, APP_NAME, str(exc))
            self.local.refresh()

    def _rename(self) -> None:
        panel = self._src_panel()
        items = panel.selected()
        if len(items) != 1:
            QMessageBox.information(self, APP_NAME, "Select a single item to rename.")
            return
        entry = items[0]
        name, ok = QInputDialog.getText(self, "Rename", "New name:", text=entry.name)
        if not ok or not name.strip() or name.strip() == entry.name:
            return
        name = name.strip()
        if panel.remote:
            dest = posix_join(panel.path, name)
            self.req_rename.emit(entry.path, dest)
        else:
            dest = os.path.join(panel.path, name)
            try:
                os.rename(entry.path, dest)
                self.local.refresh()
            except OSError as exc:
                QMessageBox.warning(self, APP_NAME, str(exc))

    def _props(self) -> None:
        panel = self._src_panel()
        items = panel.selected()
        if len(items) != 1:
            return
        e = items[0]
        text = (
            "Name: %s\nPath: %s\nType: %s\nSize: %s\nChanged: %s\nPermissions: %s\nOwner: %s  Group: %s"
            % (e.name, e.path, e.type_label(), e.size_label(), e.mtime_label(),
               e.perms_label(), e.owner, e.group)
        )
        if panel.remote:
            mode, ok = QInputDialog.getText(
                self, "Properties", text + "\n\nNew mode (octal, e.g. 644):",
                text=oct(e.mode & 0o777)[2:] if e.mode else "644",
            )
            if ok and mode.strip():
                try:
                    value = int(mode.strip(), 8)
                except ValueError:
                    QMessageBox.warning(self, APP_NAME, "Invalid octal mode.")
                    return
                self.req_chmod.emit(e.path, value)
        else:
            QMessageBox.information(self, "Properties", text)

    def _open_local(self, entry: FileEntry) -> None:
        QDesktopServices.openUrl(QUrl.fromLocalFile(entry.path))

    def _open_remote(self, entry: FileEntry) -> None:
        if not self.connected or entry.is_dir:
            return
        dest = os.path.join("/tmp", "skiff-open-" + entry.name)
        job = self.queue.add_job("Open", entry.path, dest, entry.size, False)
        self._enqueue(("download", job, entry.path, dest, False, False, None, False))
        self._open_after = dest
        self._kick_queue()

    # ── Misc ──────────────────────────────────────────────────────────────

    def _help(self) -> None:
        from .help_dialogs import HelpDialog
        dlg = getattr(self, "_help_dlg", None)
        if dlg is None:
            dlg = self._help_dlg = HelpDialog(self)
        dlg.show()
        dlg.raise_()
        dlg.activateWindow()

    def _about(self) -> None:
        from .help_dialogs import AboutDialog
        from .qtcompat import exec_dialog
        exec_dialog(AboutDialog(self))

    def closeEvent(self, event) -> None:
        self.settings["window_width"] = self.width()
        self.settings["window_height"] = self.height()
        sizes = self.splitter.sizes()
        if len(sizes) > 1:
            self.settings["queue_height"] = sizes[1]
        self.settings["show_hidden"] = self.act_hidden.isChecked()
        self.settings["confirm_delete"] = self.act_confirm.isChecked()
        save_settings(self.settings)
        try:
            self.req_disconnect.emit()
        except Exception:
            pass
        self.thread.quit()
        self.thread.wait(1500)
        event.accept()
