"""Static text shown in Help > Skiff Help (F1). Mirrored in HELP.md."""

from __future__ import annotations

from typing import List, Tuple

OVERVIEW = """\
Skiff SFTP is a two-pane file manager for SFTP. Your computer is on the left, \
the server is on the right, and a transfer queue runs along the bottom. It \
looks and works the same on KDE Plasma, GNOME and Cinnamon, on X11 or Wayland.

Quick start
  1. Press Ctrl+S to open the Site Manager, click New, and fill in the host \
name, user name and authentication.
  2. Click Save, then Login. The right pane lists your remote home folder \
(or the Remote directory you set).
  3. Select files in one pane and press F5 to copy them to the folder shown \
in the other pane. Progress shows in the queue at the bottom.
  4. Sites save to ~/.config/skiff/sites.json (mode 600).
"""

SHORTCUTS: List[Tuple[str, str]] = [
    ("F1", "This help"),
    ("Ctrl+S", "Site Manager"),
    ("Ctrl+N", "New session (opens the Site Manager)"),
    ("Ctrl+K", "Quick Connect: type a host (or user@host:port) and connect"),
    ("Ctrl+R", "Refresh both panes"),
    ("F2", "Rename the selected item"),
    ("F5", "Copy: upload or download, depending on the focused pane"),
    ("F6", "Move: copy, then delete the source"),
    ("F7", "New folder"),
    ("F8", "Delete (asks first if Options > Confirm deletes is on)"),
    ("F9", "Properties; on the remote pane you can change permissions (chmod)"),
    ("F10 / Alt+F4", "Quit"),
    ("Backspace", "Go to the parent folder"),
    ("Enter / double-click", "Open a folder, or open a file"),
]

HELP_TOPICS: List[Tuple[str, str]] = [
    ("Connecting to a server", """\
Open Session > Site Manager (Ctrl+S). Click New, then fill in:
  • Name: a label for the list.
  • Host name and Port (22 by default).
  • User name.
  • Authentication: see "Password and key authentication".
  • Remote directory (optional): the folder to open after login. If it is \
empty, Skiff opens your remote home folder.
  • Local directory (optional): the folder the left pane jumps to on login.
  • Timeout (s): how long to wait for the server, 5 to 120 seconds.
Click Save to store the site, or Login to save and connect. Duplicate copies \
a site; Delete removes it. Session > Disconnect closes the connection.
Session > Quick Connect (Ctrl+K) connects without a saved site: type a host, \
user@host:port or sftp://user@host:port. If a saved site has the same host \
and port, its settings and saved password are used.

Skiff uses python3-paramiko when it is installed (EPEL). Otherwise it drives \
the system OpenSSH tools (ssh and sftp), so your ~/.ssh/config, ssh-agent and \
keys are used as usual. With the OpenSSH backend, the server needs python3 to \
list folders."""),
    ("Logging in", """\
Skiff asks for whatever is missing when you connect:
  • No user name saved: a login window asks for the user name and password. \
For SSH agent / key sites you can leave the password blank to try your keys \
first.
  • User name but no password (password sites, or nothing saved in the \
keychain or vault): the login window asks for the password only.
  • Key or agent site that the server refuses: Skiff asks for the password \
and tries again.
  • Wrong password: Skiff asks again, up to 3 tries, then shows the server's \
answer.
Tick "Save password" in the login window to keep the password (and the user \
name) for next time, in the store chosen in Options ▸ Passwords. If saving \
was off, Skiff uses the system keychain when one is running, otherwise the \
encrypted vault.
Passwords are never put on the command line, in the environment or in a \
file, and Skiff never reads a terminal, so a login can't hang waiting for \
input you can't see."""),
    ("Opening a host from the command line", """\
  skiff --host HOST [--user USER] [--port PORT] [--key PATH] [--password-fd N]
  skiff sftp://[user@]host[:port][/path]
Skiff opens and connects right away, asking for a missing user name or \
password in the login window. --host also accepts user@host:port. Empty \
values (e.g. --user with nothing after it) are allowed, so launchers can \
pass --host {host} --user {user} --port {port} as is. Other options (such as \
-platform offscreen) go to Qt. --key logs in with that private key file. \
There is no password option on purpose: a program that starts Skiff (such as \
Porthole's Open in Skiff) can pass the password through an inherited pipe \
with --password-fd N, which Skiff reads once and closes; it is never saved."""),
    ("Host keys", """\
"Verify host key against ~/.ssh/known_hosts" is on by default for new sites.
The first time you connect to a server, Skiff shows its host key \
fingerprint (SHA256, the same as ssh shows). Click Yes to trust it: Skiff \
adds it to ~/.ssh/known_hosts and connects. A key that later changes is \
refused as a host key mismatch. If you untick the box, Skiff accepts new \
keys without asking: OpenSSH saves them (accept-new) and paramiko accepts \
them for that session only.
If the key changed on purpose (the server was rebuilt), remove the old line \
with ssh-keygen -R host (or -R '[host]:port') and connect again."""),
    ("Password and key authentication", """\
Authentication has three choices:
  • SSH agent / default keys: uses ssh-agent and the keys in ~/.ssh. This is \
the closest match to WinSCP with Pageant.
  • Private key file: pick the key with the … button. If the key has a \
passphrase, put it in the "Password / key passphrase" field.
  • Password: type the password, or leave it empty to be asked at login \
(see "Logging in"). Tick "Save password" to keep it in the system keychain \
or the encrypted vault (see "Saved passwords").
Typing a password on an SSH agent / default keys site switches it to \
Password.
With paramiko the password goes straight to paramiko. Without it, Skiff \
hands it to ssh/sftp through SSH_ASKPASS and a private socket readable only \
by you; it never appears in a file, the command line or the environment, \
and ssh gets one try with it so a wrong password can't lock the account."""),
    ("Saved passwords", """\
Choose where passwords are kept in Options ▸ Passwords:
  • Don't save passwords: you type the password each time you log in.
  • System keychain: your login keyring (GNOME Keyring / KWallet, through \
the Secret Service). Unlocked when you log in; no extra password.
  • Encrypted vault: a file encrypted with AES-256-GCM using a key derived \
from a master password (scrypt). Works on any machine, including headless \
or airgapped ones. You enter the master password once per session; \
Options ▸ Lock Password Vault locks it again. The vault file defaults to \
~/.config/skiff/vault.json; change it in Options ▸ Passwords.
To save a password, type it in the site's Password field in the Site \
Manager with "Save password" ticked (typing ticks it for you), then click \
Save or Login. The field then shows "Saved — type to replace". Untick Save \
password to forget it. Deleting a site deletes its saved password; \
Duplicate does not copy it. The same field holds a key passphrase for \
"Private key file" sites.
Change Master Password… (Options ▸ Passwords) re-encrypts the vault with a \
new master password. A forgotten master password cannot be recovered: \
delete the vault file and save the passwords again.
Switching storage in Options offers to move your saved passwords to the \
new store. Switching to "Don't save passwords" offers to delete them; \
Cancel keeps them where they are in case you switch back.
If the keychain isn't available (no Secret Service running, for example \
over SSH or on a server without a desktop), the keychain choice is greyed \
out with the reason; use the encrypted vault. If a saved password can't be \
read at login (keychain locked or the unlock was cancelled), Skiff asks \
for the password instead.
Upgrading from Skiff 1.0: passwords that 1.0 kept in plain text in \
sites.json are moved on first start into the store you pick (keychain \
or vault), or deleted if you choose not to save them. sites.json never \
holds a password after that."""),
    ("Browsing files", """\
Each pane has a path box, plus Parent, Home, Root and Refresh buttons. Type a \
path and press Enter to jump there. Click a column header to sort. Folders \
are listed in bold.
Double-click or press Enter on a folder to open it; Backspace goes up a level.
Double-click a local file to open it with your desktop's default app. \
Double-click a remote file to download it to /tmp/skiff-open-<name> and open \
that copy. Changes to that copy are not uploaded back.
Mark > Show hidden files shows dot files in both panes."""),
    ("Uploading and downloading", """\
Click in the pane you want to copy from, select one or more files or folders, \
and press F5 (Copy) or F6 (Move). Files go to the folder shown in the other \
pane, and folders are copied with everything in them.
  • Local pane focused: upload to the remote folder.
  • Remote pane focused: download to the local folder.
Move copies first and deletes the source only after the copy succeeds.
Drag and drop also works. Drop files from the local pane or your file \
manager onto the remote pane to upload. Drag selected remote files onto the \
local pane to download."""),
    ("Transfer queue", """\
Every copy, move, drop and remote open becomes a row in the queue at the \
bottom of the window. The row shows the direction, the source, the \
destination and the progress. Jobs run one at a time, in order. When the \
queue is empty, both panes refresh. A failed job shows its error in the \
queue and the next job starts."""),
    ("Other file operations", """\
  • F7 New folder: creates a folder in the focused pane.
  • F8 Delete: deletes the selection. Folders are deleted with everything in \
them. Options > Confirm deletes (on by default) asks first.
  • F2 Rename: renames the selected item.
  • F9 Properties: shows name, path, type, size, date, permissions, owner and \
group. On the remote pane you can enter a new octal mode (e.g. 644) to chmod \
the file."""),
    ("Settings and config files", """\
Skiff keeps its files in ~/.config/skiff/ ($XDG_CONFIG_HOME/skiff if that \
is set). The folder is mode 700 and the files are mode 600.
  • sites.json: saved sites. It never contains passwords; sites with \
"Save password" ticked have theirs in the keychain or the vault.
  • vault.json: the encrypted password vault, if you use one.
  • settings.json: window size, queue height, show hidden files, confirm \
deletes, and where passwords are kept.
To start fresh, quit Skiff and delete ~/.config/skiff/. To move your sites \
to another computer, copy sites.json."""),
    ("Troubleshooting", """\
  • Could not log in on a new computer: Skiff 1.2 and older refused servers \
that weren't in ~/.ssh/known_hosts yet and did not ask for a missing \
password. 1.3 shows the host key and asks for the user name and password.
  • "Host key mismatch": see Host keys.
  • "Login failed … rejected the password 3 times": check the user name, \
Caps Lock, and that the server allows password logins \
(PasswordAuthentication or KbdInteractiveAuthentication in sshd_config).
  • "The server is delaying new logins … retrying" or "Connection closed" / \
"Error reading SSH protocol banner" right after failed logins: newer OpenSSH \
servers (Rocky 9.6+ and 10) refuse new connections from an address for a \
while after failed logins (PerSourcePenalties). Skiff waits and retries for \
up to a minute; if it still fails, wait a few minutes and try again.
  • "Authentication failed": check the user name and auth type. For key \
auth, check that the key file exists and the server has the public key in \
~/.ssh/authorized_keys. For agent auth, run ssh-add -l to see loaded keys.
  • "Could not connect … timed out": check the host, the port, and that \
sshd is running and the firewall allows it.
  • "Wrong master password (or the vault file was modified)": the vault \
could not be decrypted. Try again; if the master password is lost, delete \
the vault file and save the passwords again.
  • "System keychain not available": no Secret Service is running in this \
session (common over SSH or without a desktop). Start GNOME Keyring or \
KWallet, or switch to the encrypted vault in Options ▸ Passwords.
  • Keyboard-interactive or one-time-code logins: install python3-paramiko \
from EPEL, or use key or agent auth.
  • Remote folders do not list with the OpenSSH backend: the server needs \
python3, or install python3-paramiko on this computer.
  • Window looks wrong on Wayland: try QT_QPA_PLATFORM=xcb skiff.
  • Command-line: skiff --help and skiff --version."""),
]


def as_markdown() -> str:
    """Render the help text as Markdown (used to regenerate HELP.md)."""
    out = ["# Skiff SFTP — Help", "", "_This file mirrors the in-app Help page (F1)._", "",
           "## Overview", "", OVERVIEW.rstrip(), "", "## Keyboard shortcuts", "",
           "| Shortcut | Action |", "|---|---|"]
    out += ["| %s | %s |" % (k, d) for k, d in SHORTCUTS]
    for heading, body in HELP_TOPICS:
        out += ["", "## " + heading, "", body.rstrip()]
    return "\n".join(out) + "\n"


if __name__ == "__main__":
    import sys
    sys.stdout.write(as_markdown())
