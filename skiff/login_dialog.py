"""Login prompts: user name / password, Quick Connect, unknown host key."""

from __future__ import annotations

from typing import Optional

from . import APP_NAME
from .qtcompat import (
    QCheckBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QLabel,
    QLineEdit,
    QSpinBox,
    QVBoxLayout,
    qt_dialog_std,
    qt_echo,
)


class LoginDialog(QDialog):
    """Ask for the user name and/or password for one connection attempt.

    need_user:     show an editable user name field (required).
    need_password: the password is required (password sites, or after the
                   server refused the keys). Otherwise it is optional and
                   "leave blank to try your SSH keys first".
    save_label:    text for the Save password box, or None to hide it.
    """

    def __init__(self, parent, host: str, port: int, username: str = "",
                 need_user: bool = True, need_password: bool = True,
                 message: str = "", save_label: Optional[str] = None,
                 save_checked: bool = False, save_hint: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Log in — %s" % APP_NAME)
        self.setModal(True)
        self.need_user = need_user
        self.need_password = need_password
        lay = QVBoxLayout(self)
        where = host if int(port or 22) == 22 else "%s:%s" % (host, port)
        head = QLabel("<b>Log in to %s</b>" % _esc(where))
        lay.addWidget(head)
        self.message = QLabel(message or "")
        self.message.setWordWrap(True)
        self.message.setStyleSheet("QLabel { color: #b00020; }")
        self.message.setVisible(bool(message))
        lay.addWidget(self.message)
        form = QFormLayout()
        self.username = QLineEdit(username or "")
        self.username.setPlaceholderText("user name on the server")
        self.username.setReadOnly(not need_user)
        if not need_user:
            self.username.setEnabled(False)
        form.addRow("User name:", self.username)
        self.password = QLineEdit()
        self.password.setEchoMode(qt_echo("Password"))
        self.password.setPlaceholderText(
            "password" if need_password else "leave blank to try your SSH keys first")
        form.addRow("Password:", self.password)
        lay.addLayout(form)
        self.save = QCheckBox(save_label or "Save password")
        self.save.setChecked(bool(save_checked))
        self.save.setVisible(save_label is not None)
        if save_hint:
            self.save.setToolTip(save_hint)
        lay.addWidget(self.save)
        self.buttons = QDialogButtonBox(qt_dialog_std("Ok") | qt_dialog_std("Cancel"))
        self.ok_button = self.buttons.button(qt_dialog_std("Ok"))
        self.ok_button.setText("Log In")
        self.buttons.accepted.connect(self.accept)
        self.buttons.rejected.connect(self.reject)
        lay.addWidget(self.buttons)
        self.username.textChanged.connect(self._update)
        self.password.textChanged.connect(self._update)
        self._update()
        (self.username if need_user and not username else self.password).setFocus()
        self.resize(420, self.sizeHint().height())

    def _update(self) -> None:
        ok = bool(self.username.text().strip()) and (bool(self.password.text()) or not self.need_password)
        self.ok_button.setEnabled(ok)
        self.save.setEnabled(bool(self.password.text()))

    def values(self):
        return (self.username.text().strip(), self.password.text(),
                self.save.isVisible() and self.save.isEnabled() and self.save.isChecked())


class QuickConnectDialog(QDialog):
    """Session > Quick Connect: host (or user@host:port / sftp:// URL)."""

    def __init__(self, parent, text: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Quick Connect — %s" % APP_NAME)
        lay = QVBoxLayout(self)
        form = QFormLayout()
        self.host = QLineEdit(text)
        self.host.setPlaceholderText("host, user@host:port or sftp://user@host:port")
        self.user = QLineEdit()
        self.user.setPlaceholderText("(asked when you connect)")
        self.port = QSpinBox()
        self.port.setRange(0, 65535)
        self.port.setSpecialValueText("default")
        self.port.setValue(0)
        form.addRow("Host:", self.host)
        form.addRow("User name:", self.user)
        form.addRow("Port:", self.port)
        lay.addLayout(form)
        note = QLabel("Skiff tries your SSH keys first and asks for anything that is missing.")
        note.setWordWrap(True)
        lay.addWidget(note)
        self.error = QLabel("")
        self.error.setStyleSheet("QLabel { color: #b00020; }")
        self.error.hide()
        lay.addWidget(self.error)
        buttons = QDialogButtonBox(qt_dialog_std("Ok") | qt_dialog_std("Cancel"))
        buttons.button(qt_dialog_std("Ok")).setText("Connect")
        buttons.accepted.connect(self._accept)
        buttons.rejected.connect(self.reject)
        lay.addWidget(buttons)
        self.target = None

    def _accept(self) -> None:
        from .target import TargetError, parse_target
        try:
            self.target = parse_target(self.host.text(), self.user.text() or None,
                                       self.port.value() or None)
        except TargetError as exc:
            self.error.setText(str(exc))
            self.error.show()
            return
        self.accept()


def _esc(text: str) -> str:
    return (text or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
