"""Single background thread for all SFTP work so the UI stays responsive."""

from __future__ import annotations

import traceback
from typing import Any, Dict, Optional

from .qtcompat import QObject, QThread, pyqtSignal
from .sftp_backend import SftpError, create_backend


class SftpWorker(QObject):
    connected = pyqtSignal(str, str)          # home, status
    disconnected = pyqtSignal()
    listed = pyqtSignal(str, object)          # path, entries
    transfer_progress = pyqtSignal(str, int, int)  # job_id, done, total
    transfer_done = pyqtSignal(str, bool, str)     # job_id, ok, message
    op_done = pyqtSignal(str, bool, str)           # kind, ok, message
    error = pyqtSignal(str)
    busy = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()
        self.backend = create_backend()
        self._site: Optional[Dict[str, Any]] = None

    def do_connect(self, site: dict) -> None:
        self.busy.emit(True, "Connecting to %s…" % site.get("host", ""))
        try:
            home = self.backend.connect(site)
            self._site = site
            label = "%s@%s:%s" % (site.get("username"), site.get("host"), site.get("port") or 22)
            self.connected.emit(home, label)
        except SftpError as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit("%s\n%s" % (exc, traceback.format_exc()))
        finally:
            self.busy.emit(False, "")

    def do_disconnect(self) -> None:
        try:
            self.backend.close()
        finally:
            self._site = None
            self.disconnected.emit()
            self.busy.emit(False, "")

    def do_list(self, path: str, show_hidden: bool) -> None:
        self.busy.emit(True, "Listing %s" % path)
        try:
            entries = self.backend.listdir(path, show_hidden)
            self.listed.emit(path, entries)
        except SftpError as exc:
            self.error.emit(str(exc))
        except Exception as exc:
            self.error.emit(str(exc))
        finally:
            self.busy.emit(False, "")

    def do_mkdir(self, path: str) -> None:
        try:
            self.backend.mkdir(path)
            self.op_done.emit("mkdir", True, path)
        except Exception as exc:
            self.op_done.emit("mkdir", False, str(exc))

    def do_remove(self, path: str, is_dir: bool) -> None:
        try:
            self.backend.remove(path, is_dir)
            self.op_done.emit("remove", True, path)
        except Exception as exc:
            self.op_done.emit("remove", False, str(exc))

    def do_rename(self, src: str, dst: str) -> None:
        try:
            self.backend.rename(src, dst)
            self.op_done.emit("rename", True, dst)
        except Exception as exc:
            self.op_done.emit("rename", False, str(exc))

    def do_chmod(self, path: str, mode: int) -> None:
        try:
            self.backend.chmod(path, mode)
            self.op_done.emit("chmod", True, path)
        except Exception as exc:
            self.op_done.emit("chmod", False, str(exc))

    def do_download(self, job_id: str, remote: str, local: str, is_dir: bool) -> None:
        def cb(done, total):
            self.transfer_progress.emit(job_id, done, total)

        try:
            if is_dir:
                self.backend.download_tree(remote, local, cb)
            else:
                self.backend.download(remote, local, cb)
            self.transfer_done.emit(job_id, True, "Done")
        except Exception as exc:
            self.transfer_done.emit(job_id, False, str(exc))

    def do_upload(self, job_id: str, local: str, remote: str, is_dir: bool) -> None:
        def cb(done, total):
            self.transfer_progress.emit(job_id, done, total)

        try:
            if is_dir:
                self.backend.upload_tree(local, remote, cb)
            else:
                self.backend.upload(local, remote, cb)
            self.transfer_done.emit(job_id, True, "Done")
        except Exception as exc:
            self.transfer_done.emit(job_id, False, str(exc))


class WorkerThread(QThread):
    def __init__(self, worker: SftpWorker):
        super().__init__()
        self.worker = worker
        worker.moveToThread(self)
