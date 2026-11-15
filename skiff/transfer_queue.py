"""Bottom transfer queue, WinSCP-style."""

from __future__ import annotations

import uuid
from typing import Dict, List

from .qtcompat import (
    QHeaderView,
    QLabel,
    QProgressBar,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
    qt_align,
    qt_header_resize,
    qt_item_data,
)
from .models import format_size


class TransferQueue(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)
        self.caption = QLabel("Transfer queue")
        font = self.caption.font()
        font.setBold(True)
        self.caption.setFont(font)
        layout.addWidget(self.caption)
        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(
            ["Direction", "Source", "Destination", "Size", "Progress", "Status"]
        )
        self.table.verticalHeader().setVisible(False)
        self.table.setShowGrid(False)
        self.table.setSelectionBehavior(self.table.SelectRows if hasattr(self.table, "SelectRows") else self.table.selectionBehavior())
        header = self.table.horizontalHeader()
        header.setSectionResizeMode(1, qt_header_resize("Stretch"))
        header.setSectionResizeMode(2, qt_header_resize("Stretch"))
        layout.addWidget(self.table)
        self._jobs: Dict[str, int] = {}

    def add_job(self, direction: str, src: str, dst: str, size: int, is_dir: bool) -> str:
        job_id = str(uuid.uuid4())
        row = self.table.rowCount()
        self.table.insertRow(row)
        self.table.setItem(row, 0, QTableWidgetItem(direction))
        self.table.setItem(row, 1, QTableWidgetItem(src))
        self.table.setItem(row, 2, QTableWidgetItem(dst))
        size_item = QTableWidgetItem("<DIR>" if is_dir else format_size(size))
        size_item.setTextAlignment(qt_align("AlignRight") | qt_align("AlignVCenter"))
        self.table.setItem(row, 3, size_item)
        bar = QProgressBar()
        bar.setRange(0, 100)
        bar.setValue(0)
        bar.setTextVisible(True)
        self.table.setCellWidget(row, 4, bar)
        self.table.setItem(row, 5, QTableWidgetItem("Queued"))
        self.table.item(row, 0).setData(qt_item_data("UserRole"), job_id)
        self._jobs[job_id] = row
        return job_id

    def _row(self, job_id: str):
        # Rows can shift; scan.
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 0)
            if item and item.data(qt_item_data("UserRole")) == job_id:
                return row
        return self._jobs.get(job_id)

    def set_progress(self, job_id: str, done: int, total: int) -> None:
        row = self._row(job_id)
        if row is None:
            return
        bar = self.table.cellWidget(row, 4)
        if isinstance(bar, QProgressBar):
            if total > 0:
                bar.setRange(0, 100)
                bar.setValue(int(done * 100 / total))
            else:
                bar.setRange(0, 0)
        status = self.table.item(row, 5)
        if status:
            status.setText("Transferring…")

    def set_done(self, job_id: str, ok: bool, message: str) -> None:
        row = self._row(job_id)
        if row is None:
            return
        bar = self.table.cellWidget(row, 4)
        if isinstance(bar, QProgressBar):
            bar.setRange(0, 100)
            bar.setValue(100 if ok else bar.value())
        status = self.table.item(row, 5)
        if status:
            status.setText("Done" if ok else message)
        self.caption.setText("Transfer queue — last: %s" % ("OK" if ok else "failed"))

    def pending_count(self) -> int:
        n = 0
        for row in range(self.table.rowCount()):
            item = self.table.item(row, 5)
            if item and item.text() in ("Queued", "Transferring…"):
                n += 1
        return n
