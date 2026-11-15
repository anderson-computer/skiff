"""Saved passwords: Qt dialogs and the glue between the UI and secret_store.

Ported from MultiSSH Manager 2.2.0 (Edit ▸ Options ▸ Passwords, the master
password dialog, Lock Password Vault, and moving passwords when the store
changes), adapted to Skiff's Qt UI.
"""

from __future__ import annotations

import html
import os
from typing import Callable, Dict, List, Optional, Tuple

from .config import load_sites, save_settings, save_sites
from .qtcompat import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
    exec_dialog,
    qt_dialog_role,
    qt_dialog_std,
    qt_echo,
    qt_msg_btn,
    qt_msg_icon,
)
from .secret_store import (
    BACKEND_KEYRING,
    BACKEND_LABELS,
    BACKEND_NONE,
    BACKEND_VAULT,
    MIN_MASTER_LEN,
    FileVault,
    KeyringStore,
    VaultError,
    backend_choices,
    default_vault_path,
    drop_plaintext,
    keyring_label,
    migrate_plaintext,
    migration_backend,
    normalize_backend,
    store_label,
    vault_path_from_settings,
)

ACCEPTED = 1


def _dim(label: QLabel) -> QLabel:
    label.setEnabled(False)
    return label


def _note(text: str) -> QLabel:
    lbl = QLabel(text)
    lbl.setWordWrap(True)
    return _dim(lbl)


# ---------------------------------------------------------------------------
# Dialogs
# ---------------------------------------------------------------------------
class MasterPasswordDialog(QDialog):
    """mode: "create", "unlock" or "change"."""

    TITLES = {"create": "Create Password Vault", "unlock": "Unlock Password Vault",
              "change": "Change Master Password"}
    INTRO = {
        "create": "Choose a master password for your new vault. It encrypts every "
                  "saved site password and cannot be recovered if forgotten.",
        "unlock": "Enter the master password to unlock saved site passwords "
                  "for this session.",
        "change": "Enter the current master password and a new one.",
    }

    def __init__(self, parent, mode: str, vault_path: str, message: str = ""):
        super().__init__(parent)
        self.mode = mode
        self.setWindowTitle(self.TITLES[mode])
        self.setModal(True)
        self.setMinimumWidth(440)
        box = QVBoxLayout(self)
        intro = QLabel(self.INTRO[mode])
        intro.setWordWrap(True)
        box.addWidget(intro)
        path_lbl = _dim(QLabel(vault_path))
        path_lbl.setWordWrap(True)
        box.addWidget(path_lbl)
        self.message = QLabel("")
        if message:
            self.message.setText("<span style='color:#e5534b'>%s</span>" % html.escape(message))
            self.message.setWordWrap(True)
            box.addWidget(self.message)

        def pw(placeholder):
            e = QLineEdit()
            e.setEchoMode(qt_echo("Password"))
            e.setPlaceholderText(placeholder)
            e.textChanged.connect(lambda _t: self._validate())
            box.addWidget(e)
            return e

        self.current = pw("Current master password") if mode in ("unlock", "change") else None
        if mode in ("create", "change"):
            self.new1 = pw("New master password (min. %d characters)" % MIN_MASTER_LEN)
            self.new2 = pw("Repeat new master password")
        else:
            self.new1 = self.new2 = None
        self.hint = _dim(QLabel(""))
        box.addWidget(self.hint)
        buttons = QDialogButtonBox()
        self.ok = buttons.addButton("Unlock" if mode == "unlock" else "Save",
                                    qt_dialog_role("AcceptRole"))
        buttons.addButton(qt_dialog_std("Cancel"))
        self.ok.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        box.addWidget(buttons)
        self._validate()

    def _validate(self) -> None:
        ok, hint = True, ""
        if self.current is not None and not self.current.text():
            ok = False
        if self.new1 is not None:
            a, b = self.new1.text(), self.new2.text()
            if len(a) < MIN_MASTER_LEN:
                ok, hint = False, "At least %d characters." % MIN_MASTER_LEN
            elif a != b:
                ok, hint = False, "Passwords don't match."
        self.hint.setText(hint)
        self.ok.setEnabled(ok)

    def current_password(self) -> str:
        return self.current.text() if self.current else ""

    def new_password(self) -> str:
        return self.new1.text() if self.new1 else ""


def _fill_backend_combo(combo: QComboBox, choices, selected: str) -> None:
    combo.clear()
    for key, label, enabled in choices:
        combo.addItem(label, key)
        item = combo.model().item(combo.count() - 1)
        if item is not None and not enabled:
            item.setEnabled(False)
    idx = combo.findData(selected)
    combo.setCurrentIndex(idx if idx >= 0 else 0)


class PasswordOptionsDialog(QDialog):
    """Options ▸ Passwords: where saved passwords are kept."""

    def __init__(self, parent, settings: Dict, keyring_available: bool, keyring_error: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Options — Passwords")
        self.setMinimumWidth(560)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.backend = QComboBox()
        _fill_backend_combo(self.backend, backend_choices(keyring_available, keyring_error),
                            normalize_backend(settings.get("password_backend")))
        form.addRow("Store passwords", self.backend)

        row = QWidget()
        rl = QHBoxLayout(row)
        rl.setContentsMargins(0, 0, 0, 0)
        self.vault_entry = QLineEdit(vault_path_from_settings(settings))
        self.vault_browse = QPushButton("Browse…")
        self.vault_default = QPushButton("Default")
        rl.addWidget(self.vault_entry, 1)
        rl.addWidget(self.vault_browse)
        rl.addWidget(self.vault_default)
        form.addRow("Vault file", row)
        self.change_master_btn = QPushButton("Change Master Password…")
        form.addRow("", self.change_master_btn)
        layout.addLayout(form)
        layout.addWidget(_note(
            "Keychain: stored in your login keyring, unlocked when you log in. "
            "Vault: an AES-256 encrypted file, unlocked with a master password "
            "once per session — works without a desktop keyring. Saved "
            "passwords are handed to ssh through a private helper and are never "
            "written to sites.json, the command line or the environment."))
        buttons = QDialogButtonBox(qt_dialog_std("Ok") | qt_dialog_std("Cancel"))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        self.vault_browse.clicked.connect(self._browse)
        self.vault_default.clicked.connect(lambda: self.vault_entry.setText(default_vault_path()))
        self.backend.currentIndexChanged.connect(lambda _i: self._sync())
        self._sync()

    def _browse(self) -> None:
        path, _ = QFileDialog.getSaveFileName(self, "Choose vault file", self.vault_path(),
                                              "Vault (*.json);;All files (*)")
        if path:
            self.vault_entry.setText(path)

    def _sync(self) -> None:
        is_vault = self.selected_backend() == BACKEND_VAULT
        for w in (self.vault_entry, self.vault_browse, self.vault_default, self.change_master_btn):
            w.setEnabled(is_vault)

    def selected_backend(self) -> str:
        return normalize_backend(self.backend.currentData())

    def vault_path(self) -> str:
        text = self.vault_entry.text().strip()
        return os.path.abspath(os.path.expanduser(text)) if text else default_vault_path()

    def apply_to(self, settings: Dict) -> None:
        vp = self.vault_path()
        settings["vault_file"] = "" if vp == default_vault_path() else vp


class PlaintextMigrationDialog(QDialog):
    """Shown once when an older sites.json still holds passwords in plain text."""

    def __init__(self, parent, count: int, keyring_available: bool, keyring_error: str = ""):
        super().__init__(parent)
        self.setWindowTitle("Secure your saved passwords")
        self.setMinimumWidth(540)
        layout = QVBoxLayout(self)
        intro = QLabel(
            "Skiff found %d saved password(s) stored in plain text in sites.json "
            "by an earlier version. Choose where to keep them. They are removed "
            "from sites.json either way." % count)
        intro.setWordWrap(True)
        layout.addWidget(intro)
        form = QFormLayout()
        self.backend = QComboBox()
        choices = [c for c in backend_choices(keyring_available, keyring_error)
                   if c[0] != BACKEND_NONE]
        _fill_backend_combo(self.backend, choices, migration_backend(keyring_available))
        form.addRow("Store passwords", self.backend)
        layout.addLayout(form)
        layout.addWidget(_note(
            "\"Don't save passwords\" deletes them instead; you'll type each "
            "password when you log in."))
        buttons = QDialogButtonBox()
        self.move_btn = buttons.addButton("Move Passwords", qt_dialog_role("AcceptRole"))
        self.delete_btn = buttons.addButton("Don't Save Passwords", qt_dialog_role("DestructiveRole"))
        self.move_btn.setDefault(True)
        self.choice: Optional[str] = None
        self.move_btn.clicked.connect(self._move)
        self.delete_btn.clicked.connect(self._delete)
        layout.addWidget(buttons)

    def _move(self) -> None:
        self.choice = normalize_backend(self.backend.currentData())
        self.accept()

    def _delete(self) -> None:
        self.choice = BACKEND_NONE
        self.accept()


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------
class PasswordManager:
    """Owns the keychain handle and the (once-per-session) unlocked vault.

    The prompt_* / confirm / error hooks can be replaced (tests do) so all
    logic runs headless.
    """

    def __init__(self, parent: Optional[QWidget], settings: Dict,
                 status: Optional[Callable[[str], None]] = None):
        self.parent = parent
        self.settings = settings
        self.settings["password_backend"] = normalize_backend(settings.get("password_backend"))
        self.status = status or (lambda msg: None)
        self._vault: Optional[FileVault] = None
        self._keyring: Optional[KeyringStore] = None

    # --- UI hooks (overridable) -------------------------------------------
    def prompt_master(self, mode: str, path: str, message: str) -> Tuple[bool, str, str]:
        dlg = MasterPasswordDialog(self.parent, mode, path, message)
        ok = bool(exec_dialog(dlg))
        return ok, dlg.current_password(), dlg.new_password()

    def confirm(self, title: str, text: str, button: str) -> bool:
        box = QMessageBox(self.parent)
        box.setIcon(qt_msg_icon("Question"))
        box.setWindowTitle(title)
        box.setText(title)
        box.setInformativeText(text)
        yes = box.addButton(button, qt_dialog_role("AcceptRole"))
        box.addButton(qt_msg_btn("Cancel"))
        exec_dialog(box)
        return box.clickedButton() is yes

    def error(self, title: str, text: str) -> None:
        QMessageBox.warning(self.parent, title, text)

    def prompt_migration(self, count: int) -> Optional[str]:
        ring = self.keyring()
        dlg = PlaintextMigrationDialog(self.parent, count, ring.available, ring.error or "")
        exec_dialog(dlg)
        return dlg.choice

    # --- state --------------------------------------------------------------
    @property
    def backend(self) -> str:
        return self.settings.get("password_backend") or BACKEND_NONE

    @property
    def label(self) -> Optional[str]:
        return store_label(self.backend)

    def vault_path(self) -> str:
        return vault_path_from_settings(self.settings)

    def keyring(self) -> KeyringStore:
        if self._keyring is None:
            self._keyring = KeyringStore()
        return self._keyring

    @property
    def vault_unlocked(self) -> bool:
        return self._vault is not None and self._vault.unlocked

    def _save_settings(self) -> None:
        try:
            save_settings(self.settings)
        except OSError as e:
            self.error("Could not save options", str(e))

    # --- stores ---------------------------------------------------------------
    def open_store(self, backend: Optional[str] = None, create: bool = False,
                   vault_path: Optional[str] = None):
        """Return a ready-to-use store, prompting to unlock/create the vault
        when needed. None if unavailable or the user cancelled."""
        backend = backend or self.backend
        if backend == BACKEND_KEYRING:
            ring = self.keyring()
            if not ring.available:
                self.error("System keychain not available",
                           ring.error or "No Secret Service (GNOME Keyring/KWallet) "
                           "is running in this session. Use the encrypted vault instead.")
                return None
            return ring
        if backend != BACKEND_VAULT:
            return None
        path = vault_path or self.vault_path()
        vault = self._vault if self._vault is not None and self._vault.path == os.path.abspath(path) \
            else FileVault(path)
        if vault.unlocked:
            self._vault = vault
            return vault
        message = ""
        while True:
            if not vault.exists and not create:
                return None
            mode = "unlock" if vault.exists else "create"
            ok, current, new = self.prompt_master(mode, vault.path, message)
            if not ok:
                return None
            try:
                if mode == "create":
                    vault.create(new)
                else:
                    vault.unlock(current)
            except VaultError as e:
                message = str(e)
                continue
            self._vault = vault
            return vault

    def lock_vault(self) -> bool:
        if self.vault_unlocked:
            self._vault.lock()
            self.status("Password vault locked.")
            return True
        self.status("The password vault is not unlocked.")
        return False

    def change_master(self, path: Optional[str] = None) -> bool:
        vault = FileVault(path or self.vault_path())
        if not vault.exists:
            self.error("No vault yet", "A vault is created the first time you save a password.")
            return False
        message = ""
        while True:
            ok, old, new = self.prompt_master("change", vault.path, message)
            if not ok:
                return False
            try:
                vault.change_master(old, new)
            except VaultError as e:
                message = str(e)
                continue
            if self._vault is not None and self._vault.path == vault.path:
                self._vault = vault
            self.status("Master password changed.")
            return True

    # --- per site ---------------------------------------------------------------
    def get(self, site: Dict) -> Optional[str]:
        if not site.get("save_password") or self.backend == BACKEND_NONE:
            return None
        store = self.open_store()
        if store is None:
            return None
        try:
            return store.get(site["id"])
        except VaultError as e:
            self.status(str(e))
            self.error("Saved password unavailable", str(e))
            return None

    def save(self, site: Dict, password: str) -> bool:
        store = self.open_store(create=True)
        if store is None:
            return False
        try:
            store.set(site["id"], password, keyring_label(site))
        except VaultError as e:
            self.error("Could not save the password", str(e))
            return False
        site["save_password"] = True
        return True

    def forget(self, site: Dict) -> bool:
        if not site.get("save_password"):
            return True
        store = self.open_store()
        if store is not None:
            try:
                store.delete(site["id"])
            except VaultError as e:
                self.error("Could not remove the saved password", str(e))
                return False
        site["save_password"] = False
        return True

    def apply_action(self, site: Dict, action: Tuple[Optional[str], Optional[str]]) -> None:
        what, value = action
        if what == "set" and value:
            self.save(site, value)
        elif what == "forget":
            self.forget(site)

    # --- changing the store (Options ▸ Passwords) ------------------------------
    def apply_options(self, new_backend: str, new_vault_file: str,
                      sites: Optional[List[Dict]] = None) -> None:
        old_backend, old_vault = self.backend, self.vault_path()
        self.settings["vault_file"] = new_vault_file
        if self.vault_path() != old_vault and self._vault is not None:
            self._vault.lock()
            self._vault = None
        new_backend = normalize_backend(new_backend)
        if new_backend != old_backend:
            sites = load_sites() if sites is None else sites
            if self.switch_backend(old_backend, new_backend, old_vault, sites):
                self.settings["password_backend"] = new_backend
        self._save_settings()

    def switch_backend(self, old: str, new: str, old_vault: str, sites: List[Dict]) -> bool:
        """Move or delete saved passwords when the store changes. Returns
        False if the change was cancelled (the old store stays in use)."""
        saved = [s for s in sites if s.get("save_password")]
        if old == BACKEND_NONE or not saved:
            return True
        if new == BACKEND_NONE:
            if not self.confirm("Delete %d saved password(s)?" % len(saved),
                                "They are stored in the %s. Cancel keeps them there "
                                "in case you switch back." % BACKEND_LABELS[old].lower(),
                                "Delete"):
                return True
            src = self.open_store(old, vault_path=old_vault)
            for s in saved:
                try:
                    if src:
                        src.delete(s["id"])
                except VaultError:
                    pass
                s["save_password"] = False
            save_sites(sites)
            self.status("Deleted %d saved password(s)." % len(saved))
            return True
        if not self.confirm("Move %d saved password(s)?" % len(saved),
                            "From the %s to the %s." % (BACKEND_LABELS[old].lower(),
                                                        BACKEND_LABELS[new].lower()),
                            "Move"):
            return False
        src = self.open_store(old, vault_path=old_vault)
        dst = self.open_store(new, create=True)
        if src is None or dst is None:
            self.error("Passwords not moved",
                       "Both the old and new password stores must be available.")
            return False
        moved = 0
        for s in saved:
            try:
                pw = src.get(s["id"])
                if pw is None:
                    continue
                dst.set(s["id"], pw, keyring_label(s))
                src.delete(s["id"])
                moved += 1
            except VaultError as e:
                self.error("Could not move the password for %s" % (s.get("name") or s.get("host")),
                           str(e))
                return False
        self.status("Moved %d saved password(s)." % moved)
        return True

    # --- first run after upgrading from plain-text sites.json -----------------
    def migrate_plaintext(self, sites: List[Dict], plaintext: Dict[str, str]) -> int:
        """Ask where to keep passwords an older Skiff stored in plain text,
        move them there and rewrite sites.json without them. Keeps asking
        until they are moved or the user chooses not to save them, so no
        plain-text password survives this call. Returns the number moved."""
        if not plaintext:
            return 0
        while True:
            if self.backend != BACKEND_NONE:
                choice = self.backend
            else:
                choice = self.prompt_migration(len(plaintext))
            if choice is None:
                continue
            if choice == BACKEND_NONE:
                drop_plaintext(sites, plaintext)
                save_sites(sites)
                self.status("Removed %d plain-text password(s) from sites.json." % len(plaintext))
                return 0
            store = self.open_store(choice, create=True)
            if store is None:
                if self.backend != BACKEND_NONE:
                    # Configured store unusable right now: let the user pick another.
                    self.settings["password_backend"] = BACKEND_NONE
                continue
            try:
                moved = migrate_plaintext(sites, plaintext, store)
            except VaultError as e:
                self.error("Could not save the password", str(e))
                self.settings["password_backend"] = BACKEND_NONE
                continue
            self.settings["password_backend"] = choice
            save_sites(sites)
            self._save_settings()
            self.status("Moved %d saved password(s) to the %s." % (moved, store_label(choice)))
            return moved
