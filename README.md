# Skiff SFTP

WinSCP-style dual-pane SFTP client for **Rocky Linux 9 and 10**.

Local files on the left, the server on the right, a transfer queue along the
bottom, and the F-key commands you know from WinSCP. Skiff uses the Qt
**Fusion** style, so it looks and works the same on KDE Plasma, GNOME and
Cinnamon, on X11 or Wayland.

| WinSCP habit | Skiff SFTP |
|---|---|
| Site Manager | `Ctrl+S`: save host, user, port, key or password |
| Saved passwords | System keychain or an encrypted vault (Options ▸ Passwords) |
| Login prompt | Asks for a missing user name / password; 3 tries; shows new host keys |
| Quick Connect | `Ctrl+K` or `skiff --host H --user U --port P` / `skiff sftp://user@host:port` |
| Local \| Remote panes | Same commander layout |
| F5 Copy / F6 Move | Upload or download, depending on the focused pane |
| F7 New folder | Local or remote |
| F8 Delete | With optional confirm |
| F2 Rename / F9 Properties | Remote chmod from Properties |
| Transfer queue | Bottom pane with progress |
| Pageant / keys | ssh-agent and `~/.ssh` keys, or a key file |
| Drag and drop | Drop local files onto the remote pane to upload |
| Help | `F1` opens Help > Skiff Help; Help > About Skiff |

## Install

Two dist-tagged noarch RPMs are provided. Use the one that matches your release.

Download the RPMs from the [latest release](https://github.com/mike0615/skiff/releases/latest), or install directly:

```
# Rocky Linux 9
sudo dnf install https://github.com/mike0615/skiff/releases/download/v1.3.0/skiff-1.3.0-1.el9.noarch.rpm
# Rocky Linux 10
sudo dnf install https://github.com/mike0615/skiff/releases/download/v1.3.0/skiff-1.3.0-1.el10.noarch.rpm
```

Building from source is only needed for development.

```bash
# Rocky Linux 9  (PyQt5 from AppStream)
sudo dnf install -y ./skiff-1.3.0-1.el9.noarch.rpm

# Rocky Linux 10 (PyQt6 from AppStream)
sudo dnf install -y ./skiff-1.3.0-1.el10.noarch.rpm
```

All hard dependencies come from BaseOS and AppStream, so **EPEL and CRB are
not required**.

| | Rocky 9 | Rocky 10 |
|---|---|---|
| Python | python3 (3.9) | python3 (3.12) |
| Qt bindings | python3-qt5-base | python3-pyqt6-base |
| Crypto | python3-cryptography | python3-cryptography |
| SSH tools | openssh-clients | openssh-clients |
| Keychain (saved passwords) | python3-gobject-base, libsecret | python3-gobject-base, libsecret |
| Recommended (AppStream) | qt5-qtsvg, qt5-qtwayland | qt6-qtsvg, qt6-qtwayland |
| Recommended (EPEL) | python3-paramiko | python3-paramiko |

### Optional: paramiko backend (EPEL)

Skiff prefers paramiko for SFTP. It handles password and key logins without
spawning `ssh`. paramiko is in EPEL on both releases. Enable EPEL (and CRB,
which some EPEL packages need) and install it:

```bash
# Rocky 9 or 10
sudo dnf install -y epel-release dnf-plugins-core
sudo dnf config-manager --set-enabled crb
sudo dnf install -y python3-paramiko
```

If EPEL is already enabled when you install Skiff, dnf pulls in paramiko
automatically as a recommended package.

Without paramiko, Skiff uses the system OpenSSH tools (`ssh` and `sftp`).
Agent and key auth still work, and passwords and key passphrases go to ssh
through SSH_ASKPASS and a private Unix socket (never a file, the command
line or the environment). Remote listings need `python3` on the server for the
OpenSSH backend.

## Use

Launch **Skiff SFTP** from the application menu (Network / File Transfer) or:

```bash
skiff            # start the GUI
skiff --help     # command-line help
skiff --version
skiff --host files.example.com --user mike --port 2222   # open and connect
skiff sftp://mike@files.example.com:2222/var/www         # same, as a URL
skiff --host 10.0.0.5 --user mike --key ~/.ssh/id_ed25519 # log in with a key file
skiff --host 10.0.0.5 --user mike --password-fd 3         # password on fd 3 (from a launcher)
```

`--host` also takes `user@host:port`. Missing user names and passwords are
asked for in the login window. Empty values are accepted, so a launcher can
always pass `--host {host} --user {user} --port {port}`. Unknown options
(e.g. `-platform offscreen`) go to Qt.

There is no option that takes a password on the command line. A program that
starts Skiff (for example Porthole's **Open in Skiff**) can hand over a saved
password with `--password-fd N`: it opens a pipe, passes the read end as fd N,
writes the password (one trailing newline is dropped) and closes the write
end. Skiff reads it once before the window opens, closes the fd, refuses a
terminal, and never saves it. If the server rejects it, the login window asks
for the password. `--key PATH` (a private key file; a password passed on the
fd is used as its passphrase) and `--password-fd` need `--host` or an
`sftp://` URL. An empty pipe is the same as no password.

### Logging in

- No user name saved: the login window asks for the user name and the
  password (for key/agent sites, leave the password blank to try keys first).
- User name but no saved password: it asks for the password only.
- Keys refused by the server: it asks for the password and retries.
- Wrong password: it asks again, up to 3 tries, then shows the server's answer.
- First connection to a server: it shows the host key fingerprint; **Yes**
  adds it to `~/.ssh/known_hosts`.

Tick **Save password** in the login window to keep it for next time
(keychain or vault, see below).

Press `F1` in the app for the full help page. The same text is in
[HELP.md](HELP.md).

## Keyboard

| Key | Action |
|---|---|
| `F1` | Help |
| `Ctrl+S` | Site Manager |
| `Ctrl+N` | New session |
| `Ctrl+K` | Quick Connect |
| `Ctrl+R` | Refresh |
| `F2` | Rename |
| `F5` | Copy (upload or download) |
| `F6` | Move |
| `F7` | New folder |
| `F8` | Delete |
| `F9` | Properties / chmod |
| `F10` | Quit |
| `Backspace` | Parent directory |
| `Enter` | Open folder / open file |

Sites are stored in `~/.config/skiff/sites.json` (mode 600). Window and view
settings are in `~/.config/skiff/settings.json`.

## Saved passwords

Choose where passwords are kept in **Options ▸ Passwords** (the same choices
as MultiSSH Manager):

| Store passwords | What it does |
|---|---|
| Don't save passwords | Type the password at each login (default) |
| System keychain (GNOME Keyring / Secret Service) | Your login keyring via libsecret; unlocked when you log in |
| Encrypted vault file (master password) | `~/.config/skiff/vault.json`, AES-256-GCM with a scrypt-derived key; unlocked once per session |

Tick **Save password** in the Site Manager to store a site's password or key
passphrase; untick it to forget it. **Change Master Password…** is in
Options ▸ Passwords and **Lock Password Vault** is in the Options menu.
Switching stores offers to move (or delete) the saved passwords. The keychain
choice is greyed out when no Secret Service is running (e.g. over SSH); use
the vault there.

`sites.json` never holds passwords. Skiff 1.0 stored remembered passwords in
plain text there; on first start, 1.1 moves them into the store you choose
and rewrites the file without them.

## Run from the source tree

```bash
# Rocky 9
sudo dnf install -y python3-qt5-base
python3 -m skiff

# Rocky 10
sudo dnf install -y python3-pyqt6-base
python3 -m skiff
```

## Build the RPMs

```bash
# Natively on Rocky 9 or 10 (builds for that release)
sudo dnf install -y rpm-build python3 python3-cryptography python3-gobject-base libsecret desktop-file-utils
./build.sh

# For both releases, using podman or docker
./build.sh 9 10
```

Output goes to `out/`: `skiff-1.3.0-1.el9.noarch.rpm`,
`skiff-1.3.0-1.el10.noarch.rpm`, the matching `.src.rpm` files and
`skiff-1.3.0.tar.gz`. You can also rebuild from a source RPM with
`rpmbuild --rebuild skiff-1.3.0-1.el9.src.rpm`.

## Tests

```bash
python3 -m unittest discover -s tests -v       # no display or Qt needed
QT_QPA_PLATFORM=offscreen python3 tests/smoke_offscreen.py   # window, Help and About
```

## Layout

```
/opt/skiff/skiff/                         application
/usr/bin/skiff                            launcher
/usr/share/applications/skiff.desktop
/usr/share/icons/hicolor/scalable/apps/skiff.svg
```

## License

MIT. See [LICENSE](LICENSE). Copyright (c) 2026 Mike Anderson.
