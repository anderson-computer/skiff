"""WinSCP-style site manager."""

from __future__ import annotations

import copy
import os
from typing import Dict, List, Optional

from .config import default_site, load_sites, save_sites
from .qtcompat import (
    QCheckBox,
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
    Qt,
    exec_dialog,
    qt_dialog_role,
    qt_dialog_std,
    qt_echo,
    qt_item_data,
)


class SiteManagerDialog(QDialog):
    def __init__(self, parent=None, sites: Optional[List[Dict]] = None, passwords=None):
        super().__init__(parent)
        # PasswordManager (keychain / vault); None means saving is off.
        self.passwords = passwords
        self.store_label = passwords.label if passwords is not None else None
        # site id -> ("set", password) | ("forget", None), applied on Save/Login.
        self._pw_actions: Dict[str, tuple] = {}
        self.setWindowTitle("Site Manager")
        self.resize(780, 480)
        self.sites: List[Dict] = copy.deepcopy(sites if sites is not None else load_sites())
        self._current_id: Optional[str] = None
        self.chosen: Optional[Dict] = None

        layout = QHBoxLayout(self)

        left = QVBoxLayout()
        left.addWidget(QLabel("Stored sites"))
        self.list = QListWidget()
        left.addWidget(self.list, 1)
        btns = QHBoxLayout()
        self.btn_new = QPushButton("New")
        self.btn_dup = QPushButton("Duplicate")
        self.btn_del = QPushButton("Delete")
        btns.addWidget(self.btn_new)
        btns.addWidget(self.btn_dup)
        btns.addWidget(self.btn_del)
        left.addLayout(btns)
        layout.addLayout(left, 1)

        right = QVBoxLayout()
        form_box = QGroupBox("Session")
        form = QFormLayout(form_box)
        self.name = QLineEdit()
        self.host = QLineEdit()
        self.port = QSpinBox()
        self.port.setRange(1, 65535)
        self.port.setValue(22)
        self.username = QLineEdit()
        self.protocol = QComboBox()
        self.protocol.addItem("SFTP", "sftp")
        self.auth = QComboBox()
        self.auth.addItem("SSH agent / default keys", "agent")
        self.auth.addItem("Private key file", "key")
        self.auth.addItem("Password", "password")
        self.password = QLineEdit()
        self.password.setEchoMode(qt_echo("Password"))
        self.save_password = QCheckBox("Save password")
        if self.store_label is None:
            self.save_password.setEnabled(False)
            self.save_password.setToolTip("Saving passwords is off (Options ▸ Passwords)")
        else:
            self.save_password.setToolTip("Store in: %s" % self.store_label)
            self.password.textEdited.connect(
                lambda t: t and self.save_password.setChecked(True))
        key_row = QWidget()
        key_l = QHBoxLayout(key_row)
        key_l.setContentsMargins(0, 0, 0, 0)
        self.key_file = QLineEdit()
        self.btn_key = QPushButton("…")
        self.btn_key.setFixedWidth(32)
        key_l.addWidget(self.key_file, 1)
        key_l.addWidget(self.btn_key)
        self.remote_dir = QLineEdit()
        self.local_dir = QLineEdit()
        self.timeout = QSpinBox()
        self.timeout.setRange(5, 120)
        self.timeout.setValue(20)
        self.strict_host = QCheckBox("Verify host key against ~/.ssh/known_hosts")
        self.strict_host.setChecked(True)

        form.addRow("Name:", self.name)
        form.addRow("Protocol:", self.protocol)
        form.addRow("Host name:", self.host)
        form.addRow("Port:", self.port)
        form.addRow("User name:", self.username)
        form.addRow("Authentication:", self.auth)
        form.addRow("Password / key passphrase:", self.password)
        form.addRow("", self.save_password)
        form.addRow("Private key:", key_row)
        form.addRow("Remote directory:", self.remote_dir)
        form.addRow("Local directory:", self.local_dir)
        form.addRow("Timeout (s):", self.timeout)
        form.addRow("", self.strict_host)
        right.addWidget(form_box)

        note = QLabel(
            "Agent auth uses ssh-agent and ~/.ssh keys (closest to WinSCP + Pageant). "
            + ("Saved passwords are kept in the %s, never in sites.json, and are "
               "handed to ssh through a private helper. Untick Save password to "
               "forget a saved password." % self.store_label
               if self.store_label else
               "Saving passwords is off (Options ▸ Passwords): the password is used "
               "for this login only.")
        )
        note.setWordWrap(True)
        right.addWidget(note)

        box = QDialogButtonBox()
        self.btn_login = box.addButton("Login", qt_dialog_role("AcceptRole"))
        self.btn_save = box.addButton("Save", qt_dialog_role("ApplyRole"))
        self.btn_close = box.addButton(qt_dialog_std("Close"))
        right.addWidget(box)
        layout.addLayout(right, 2)

        self.list.currentRowChanged.connect(self._on_select)
        self.btn_new.clicked.connect(self._new)
        self.btn_dup.clicked.connect(self._dup)
        self.btn_del.clicked.connect(self._delete)
        self.btn_key.clicked.connect(self._browse_key)
        self.btn_login.clicked.connect(self._login)
        self.btn_save.clicked.connect(self._save_clicked)
        self.btn_close.clicked.connect(self.reject)
        self.auth.currentIndexChanged.connect(self._auth_changed)

        self._reload_list()
        if self.sites:
            self.list.setCurrentRow(0)
        else:
            self._new()
        self._auth_changed()

    def _reload_list(self, select_id: Optional[str] = None) -> None:
        self.list.blockSignals(True)
        self.list.clear()
        for site in self.sites:
            item = QListWidgetItem(site.get("name") or site.get("host") or "(unnamed)")
            item.setData(qt_item_data("UserRole"), site["id"])
            self.list.addItem(item)
        self.list.blockSignals(False)
        if select_id:
            for i in range(self.list.count()):
                if self.list.item(i).data(qt_item_data("UserRole")) == select_id:
                    self.list.setCurrentRow(i)
                    break

    def _find(self, site_id: str) -> Optional[Dict]:
        for site in self.sites:
            if site["id"] == site_id:
                return site
        return None

    def _flush(self) -> None:
        if not self._current_id:
            return
        site = self._find(self._current_id)
        if not site:
            return
        site["name"] = self.name.text().strip() or self.host.text().strip() or "New site"
        site["host"] = self.host.text().strip()
        site["port"] = int(self.port.value())
        site["username"] = self.username.text().strip()
        site["protocol"] = self.protocol.currentData() or "sftp"
        site["auth"] = self.auth.currentData() or "agent"
        text = self.password.text()
        site["password"] = text  # in memory only; save_sites() never writes it
        if self.store_label is not None:
            if self.save_password.isChecked():
                if text:
                    self._pw_actions[site["id"]] = ("set", text)
                elif self._pw_actions.get(site["id"], (None,))[0] == "forget":
                    self._pw_actions.pop(site["id"], None)  # re-ticked: keep it
            elif site.get("save_password") or self._pw_actions.get(site["id"], (None,))[0] == "set":
                self._pw_actions[site["id"]] = ("forget", None)
        site["key_file"] = self.key_file.text().strip()
        site["remote_dir"] = self.remote_dir.text().strip()
        site["local_dir"] = self.local_dir.text().strip()
        site["timeout"] = int(self.timeout.value())
        site["strict_host"] = self.strict_host.isChecked()

    def _load(self, site: Dict) -> None:
        self._current_id = site["id"]
        self.name.setText(site.get("name") or "")
        self.host.setText(site.get("host") or "")
        self.port.setValue(int(site.get("port") or 22))
        self.username.setText(site.get("username") or "")
        auth = site.get("auth") or "agent"
        idx = max(0, self.auth.findData(auth))
        self.auth.setCurrentIndex(idx)
        self.password.setText(site.get("password") or "")
        pending = self._pw_actions.get(site["id"], (None,))[0]
        saved = bool(site.get("save_password")) and pending != "forget"
        self.save_password.setChecked(saved or pending == "set")
        self._update_password_placeholder(site)
        self.key_file.setText(site.get("key_file") or "")
        self.remote_dir.setText(site.get("remote_dir") or "")
        self.local_dir.setText(site.get("local_dir") or os.path.expanduser("~"))
        self.timeout.setValue(int(site.get("timeout") or 20))
        self.strict_host.setChecked(bool(site.get("strict_host", True)))
        self._auth_changed()

    def _update_password_placeholder(self, site: Dict) -> None:
        if self.store_label is None:
            self.password.setPlaceholderText(
                "Not saved (saving passwords is off: Options ▸ Passwords)")
        elif site.get("save_password"):
            self.password.setPlaceholderText("Saved — type to replace")
        else:
            self.password.setPlaceholderText("(optional) saved securely")

    def password_action(self, site_id: str):
        """("set", pw) / ("forget", None) / (None, None) for no change."""
        return self._pw_actions.get(site_id, (None, None))

    def _apply_password_actions(self) -> None:
        if self.passwords is None:
            self._pw_actions.clear()
            return
        for site in self.sites:
            action = self._pw_actions.pop(site["id"], None)
            if action:
                self.passwords.apply_action(site, action)
        self._pw_actions.clear()

    def _on_select(self, row: int) -> None:
        self._flush()
        if row < 0:
            return
        site_id = self.list.item(row).data(qt_item_data("UserRole"))
        site = self._find(site_id)
        if site:
            self._load(site)

    def _new(self) -> None:
        self._flush()
        site = default_site()
        self.sites.append(site)
        self._reload_list(site["id"])
        self._load(site)

    def _dup(self) -> None:
        self._flush()
        if not self._current_id:
            return
        src = self._find(self._current_id)
        if not src:
            return
        site = default_site()
        keep_id = site["id"]
        site.update(copy.deepcopy(src))
        site["id"] = keep_id
        site["name"] = (src.get("name") or "Site") + " copy"
        # The secret itself isn't copied (same as MultiSSH Manager).
        site["save_password"] = False
        site["password"] = ""
        self.sites.append(site)
        self._reload_list(site["id"])
        self._load(site)

    def _delete(self) -> None:
        if not self._current_id:
            return
        doomed = self._find(self._current_id)
        if doomed and doomed.get("save_password") and self.passwords is not None:
            # Deleting a site deletes its saved password.
            self.passwords.forget(doomed)
        self._pw_actions.pop(self._current_id, None)
        self.sites = [s for s in self.sites if s["id"] != self._current_id]
        save_sites(self.sites)
        self._current_id = None
        self._reload_list()
        if self.sites:
            self.list.setCurrentRow(0)
        else:
            self._new()

    def _browse_key(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select private key", os.path.expanduser("~/.ssh"), "All files (*)"
        )
        if path:
            self.key_file.setText(path)

    def _auth_changed(self) -> None:
        auth = self.auth.currentData()
        self.key_file.setEnabled(auth == "key")
        self.btn_key.setEnabled(auth == "key")

    def _save_clicked(self) -> None:
        self._flush()
        self._apply_password_actions()
        save_sites(self.sites)
        self._reload_list(self._current_id)
        QMessageBox.information(self, "Site Manager", "Sites saved.")

    def _login(self) -> None:
        self._flush()
        site = self._find(self._current_id) if self._current_id else None
        if not site or not site.get("host"):
            QMessageBox.warning(self, "Site Manager", "Enter a host name.")
            return
        self._apply_password_actions()
        save_sites(self.sites)
        self.chosen = copy.deepcopy(site)
        self.accept()
