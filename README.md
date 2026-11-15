# Skiff SFTP

WinSCP-style dual-pane SFTP client for **Rocky Linux 9 and 10**.

Local files on the left, the server on the right, a transfer queue along the
bottom, and the F-key commands you know from WinSCP. Skiff uses the Qt
**Fusion** style, so it looks and works the same on KDE Plasma, GNOME and
Cinnamon, on X11 or Wayland.

| WinSCP habit | Skiff SFTP |
|---|---|
| Site Manager | `Ctrl+S`: save host, user, port, key or password |
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

```bash
# Rocky Linux 9  (PyQt5 from AppStream)
sudo dnf install -y ./skiff-1.0.0-1.el9.noarch.rpm

# Rocky Linux 10 (PyQt6 from AppStream)
sudo dnf install -y ./skiff-1.0.0-1.el10.noarch.rpm
```

All hard dependencies come from BaseOS and AppStream, so **EPEL and CRB are
not required**.

| | Rocky 9 | Rocky 10 |
|---|---|---|
| Python | python3 (3.9) | python3 (3.12) |
| Qt bindings | python3-qt5-base | python3-pyqt6-base |
| Crypto | python3-cryptography | python3-cryptography |
| SSH tools | openssh-clients | openssh-clients |
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
Agent and key auth still work, and password auth goes through a temporary
SSH_ASKPASS helper. Remote listings need `python3` on the server for the
OpenSSH backend.

## Use

Launch **Skiff SFTP** from the application menu (Network / File Transfer) or:

```bash
skiff            # start the GUI
skiff --help     # command-line help
skiff --version
```

Press `F1` in the app for the full help page. The same text is in
[HELP.md](HELP.md).

## Keyboard

| Key | Action |
|---|---|
| `F1` | Help |
| `Ctrl+S` | Site Manager |
| `Ctrl+N` | New session |
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

Sites are stored in `~/.config/skiff/sites.json` (mode 600). Passwords are
saved only if you tick **Remember password**. Window and view settings are in
`~/.config/skiff/settings.json`.

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
sudo dnf install -y rpm-build python3 desktop-file-utils
./build.sh

# For both releases, using podman or docker
./build.sh 9 10
```

Output goes to `out/`: `skiff-1.0.0-1.el9.noarch.rpm`,
`skiff-1.0.0-1.el10.noarch.rpm`, the matching `.src.rpm` files and
`skiff-1.0.0.tar.gz`. You can also rebuild from a source RPM with
`rpmbuild --rebuild skiff-1.0.0-1.el9.src.rpm`.

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
