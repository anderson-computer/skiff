"""Commander-style file panel (local or remote)."""

from __future__ import annotations

import os
from typing import Callable, List, Optional

from .models import FileEntry, format_size, local_listdir
from .qtcompat import (
    QAbstractItemView,
    QFileIconProvider,
    QFileInfo,
    QFrame,
    QHBoxLayout,
    QHeaderView,
    QIcon,
    QLabel,
    QLineEdit,
    QMimeData,
    QPushButton,
    QSize,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QToolButton,
    QUrl,
    QVBoxLayout,
    QWidget,
    Qt,
    pyqtSignal,
    qt_align,
    qt_drag_drop,
    qt_edit_trigger,
    qt_frame_shape,
    qt_header_resize,
    qt_item_data,
    qt_item_flag,
    qt_select_behavior,
    qt_select_mode,
    qt_style_pixmap,
)


COLS = ["Name", "Size", "Type", "Changed", "Permissions"]


class FileTable(QTableWidget):
    activated_path = pyqtSignal(object)
    dropped_urls = pyqtSignal(list)

    def __init__(self, remote: bool, parent=None):
        super().__init__(0, len(COLS), parent)
        self.remote = remote
        self.setHorizontalHeaderLabels(COLS)
        self.setSelectionBehavior(qt_select_behavior("SelectRows"))
        self.setSelectionMode(qt_select_mode("ExtendedSelection"))
        self.setEditTriggers(qt_edit_trigger("NoEditTriggers"))
        self.setAlternatingRowColors(True)
        self.setShowGrid(False)
        self.setSortingEnabled(True)
        self.verticalHeader().setVisible(False)
        self.verticalHeader().setDefaultSectionSize(24)
        header = self.horizontalHeader()
        header.setStretchLastSection(False)
        header.setSectionResizeMode(0, qt_header_resize("Stretch"))
        header.setSectionResizeMode(1, qt_header_resize("ResizeToContents"))
        header.setSectionResizeMode(2, qt_header_resize("ResizeToContents"))
        header.setSectionResizeMode(3, qt_header_resize("ResizeToContents"))
        header.setSectionResizeMode(4, qt_header_resize("ResizeToContents"))
        self.setDragEnabled(True)
        self.setAcceptDrops(True)
        self.setDropIndicatorShown(True)
        self.setDragDropMode(qt_drag_drop("DragDrop"))
        self.doubleClicked.connect(self._on_double)
        self._entries: List[FileEntry] = []
        self.parent_requested = None  # set by FilePanel

    def keyPressEvent(self, event):
        from .qtcompat import qt_key
        if event.key() == qt_key("Key_Backspace"):
            if callable(self.parent_requested):
                self.parent_requested()
                return
        if event.key() in (qt_key("Key_Return"), qt_key("Key_Enter")):
            entry = self.current_entry()
            if entry:
                self.activated_path.emit(entry)
                return
        super().keyPressEvent(event)

    def _on_double(self, index):
        entry = self.entry_at(index.row())
        if entry:
            self.activated_path.emit(entry)

    def set_entries(self, entries: List[FileEntry]) -> None:
        self._entries = list(entries)
        self.setSortingEnabled(False)
        self.setRowCount(0)
        icons = QFileIconProvider()
        style = self.style()
        for entry in entries:
            row = self.rowCount()
            self.insertRow(row)
            if entry.is_parent or entry.is_dir:
                icon = style.standardIcon(qt_style_pixmap("SP_DirIcon"))
            else:
                icon = icons.icon(QFileInfo(entry.name))
            name_item = QTableWidgetItem(icon, entry.name)
            name_item.setData(qt_item_data("UserRole"), entry)
            name_item.setToolTip(entry.path)
            self.setItem(row, 0, name_item)

            size_item = QTableWidgetItem(entry.size_label())
            size_item.setTextAlignment(qt_align("AlignRight") | qt_align("AlignVCenter"))
            size_item.setData(qt_item_data("UserRole"), entry.size)
            self.setItem(row, 1, size_item)

            self.setItem(row, 2, QTableWidgetItem(entry.type_label()))
            self.setItem(row, 3, QTableWidgetItem(entry.mtime_label()))
            self.setItem(row, 4, QTableWidgetItem(entry.perms_label()))

            if entry.is_dir:
                font = name_item.font()
                font.setBold(True)
                name_item.setFont(font)
        self.setSortingEnabled(True)
        self.sortItems(0)

    def entry_at(self, row: int) -> Optional[FileEntry]:
        item = self.item(row, 0)
        if item is None:
            return None
        data = item.data(qt_item_data("UserRole"))
        return data if isinstance(data, FileEntry) else None

    def selected_entries(self) -> List[FileEntry]:
        rows = sorted({idx.row() for idx in self.selectedIndexes()})
        out = []
        for row in rows:
            entry = self.entry_at(row)
            if entry and not entry.is_parent:
                out.append(entry)
        return out

    def current_entry(self) -> Optional[FileEntry]:
        return self.entry_at(self.currentRow())

    def mimeData(self, items):
        mime = QMimeData()
        urls = []
        if not self.remote:
            for entry in self.selected_entries():
                urls.append(QUrl.fromLocalFile(entry.path))
        mime.setUrls(urls)
        mime.setData("application/x-skiff-panel", b"remote" if self.remote else b"local")
        names = "\n".join(e.path for e in self.selected_entries())
        mime.setText(names)
        return mime

    def startDrag(self, actions):
        # Default startDrag uses selected items; keep it.
        super().startDrag(actions)

    def dragEnterEvent(self, event):
        event.acceptProposedAction()

    def dragMoveEvent(self, event):
        event.acceptProposedAction()

    def dropEvent(self, event):
        urls = []
        if event.mimeData().hasUrls():
            urls = [u.toLocalFile() for u in event.mimeData().urls() if u.isLocalFile()]
        text = event.mimeData().text() or ""
        event.acceptProposedAction()
        self.dropped_urls.emit(urls if urls else text.splitlines())


class FilePanel(QWidget):
    path_changed = pyqtSignal(str)
    transfer_requested = pyqtSignal(list)  # dropped paths
    activate_entry = pyqtSignal(object)

    def __init__(self, title: str, remote: bool = False, parent=None):
        super().__init__(parent)
        self.remote = remote
        self.path = ""
        self._show_hidden = False
        self._connected = not remote

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(2)

        header = QHBoxLayout()
        self.title_label = QLabel(title)
        font = self.title_label.font()
        font.setBold(True)
        self.title_label.setFont(font)
        header.addWidget(self.title_label)
        header.addStretch(1)
        self.summary = QLabel("")
        header.addWidget(self.summary)
        root.addLayout(header)

        nav = QHBoxLayout()
        nav.setSpacing(2)
        self.btn_parent = self._icon_btn("SP_FileDialogToParent", "Parent directory (Backspace)")
        self.btn_home = self._icon_btn("SP_DirHomeIcon", "Home")
        self.btn_refresh = self._icon_btn("SP_BrowserReload", "Refresh (Ctrl+R)")
        self.btn_root = self._icon_btn("SP_ComputerIcon", "Root / drive")
        for btn in (self.btn_parent, self.btn_home, self.btn_root, self.btn_refresh):
            nav.addWidget(btn)
        self.path_edit = QLineEdit()
        self.path_edit.setPlaceholderText("Path")
        nav.addWidget(self.path_edit, 1)
        root.addLayout(nav)

        self.table = FileTable(remote=remote)
        self.table.parent_requested = self.go_parent
        root.addWidget(self.table, 1)

        self.status = QLabel("Not connected" if remote else "")
        self.status.setFrameShape(qt_frame_shape("NoFrame"))
        root.addWidget(self.status)

        self.btn_parent.clicked.connect(self.go_parent)
        self.btn_home.clicked.connect(self.go_home)
        self.btn_root.clicked.connect(self.go_root)
        self.btn_refresh.clicked.connect(self.refresh)
        self.path_edit.returnPressed.connect(self._path_entered)
        self.table.activated_path.connect(self._activated)
        self.table.dropped_urls.connect(self.transfer_requested.emit)

    def _icon_btn(self, pixmap_name: str, tip: str) -> QToolButton:
        btn = QToolButton()
        try:
            btn.setIcon(self.style().standardIcon(qt_style_pixmap(pixmap_name)))
        except Exception:
            btn.setText("..")
        btn.setToolTip(tip)
        btn.setAutoRaise(True)
        btn.setFixedSize(QSize(28, 28))
        return btn

    def set_connected(self, connected: bool, label: str = "") -> None:
        self._connected = connected
        if self.remote:
            self.status.setText(label if connected else "Not connected")
            self.table.setEnabled(connected)
            self.path_edit.setEnabled(connected)

    def set_show_hidden(self, show: bool) -> None:
        self._show_hidden = show

    def set_path(self, path: str, entries: Optional[List[FileEntry]] = None) -> None:
        self.path = path
        self.path_edit.setText(path)
        if entries is None and not self.remote:
            try:
                entries = local_listdir(path, self._show_hidden)
                self.status.setText(self._local_free(path))
            except OSError as exc:
                self.status.setText(str(exc))
                entries = []
        if entries is not None:
            self.table.set_entries(entries)
            files = sum(1 for e in entries if not e.is_dir and not e.is_parent)
            dirs = sum(1 for e in entries if e.is_dir and not e.is_parent)
            self.summary.setText("%d folders, %d files" % (dirs, files))

    def refresh(self) -> None:
        if self.remote:
            if self._connected and self.path:
                self.path_changed.emit(self.path)
        else:
            self.set_path(self.path or os.path.expanduser("~"))

    def go_parent(self) -> None:
        if self.remote:
            if self.path and self.path != "/":
                parent = self.path.rstrip("/").rsplit("/", 1)[0] or "/"
                self.path_changed.emit(parent)
        else:
            cur = os.path.abspath(self.path or os.getcwd())
            parent = os.path.dirname(cur)
            if parent != cur:
                self.set_path(parent)

    def go_home(self) -> None:
        if self.remote:
            self.path_changed.emit("")  # worker uses backend.home
        else:
            self.set_path(os.path.expanduser("~"))

    def go_root(self) -> None:
        if self.remote:
            self.path_changed.emit("/")
        else:
            self.set_path("/" if os.name != "nt" else os.path.abspath(self.path)[:3])

    def _path_entered(self) -> None:
        text = self.path_edit.text().strip()
        if not text:
            return
        if self.remote:
            self.path_changed.emit(text)
        else:
            if os.path.isdir(text):
                self.set_path(os.path.abspath(text))

    def _activated(self, entry: FileEntry) -> None:
        if entry.is_dir:
            if self.remote:
                self.path_changed.emit(entry.path)
            else:
                self.set_path(entry.path)
        else:
            self.activate_entry.emit(entry)

    def selected(self) -> List[FileEntry]:
        return self.table.selected_entries()

    @staticmethod
    def _local_free(path: str) -> str:
        try:
            st = os.statvfs(path)
            free = st.f_bavail * st.f_frsize
            total = st.f_blocks * st.f_frsize
            return "Free %s of %s" % (format_size(free), format_size(total))
        except (AttributeError, OSError):
            return path
