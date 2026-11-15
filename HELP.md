# Skiff SFTP — Help

_This file mirrors the in-app Help page (F1)._

## Overview

Skiff SFTP is a two-pane file manager for SFTP. Your computer is on the left, the server is on the right, and a transfer queue runs along the bottom. It looks and works the same on KDE Plasma, GNOME and Cinnamon, on X11 or Wayland.

Quick start
  1. Press Ctrl+S to open the Site Manager, click New, and fill in the host name, user name and authentication.
  2. Click Save, then Login. The right pane lists your remote home folder (or the Remote directory you set).
  3. Select files in one pane and press F5 to copy them to the folder shown in the other pane. Progress shows in the queue at the bottom.
  4. Sites save to ~/.config/skiff/sites.json (mode 600).

## Keyboard shortcuts

| Shortcut | Action |
|---|---|
| F1 | This help |
| Ctrl+S | Site Manager |
| Ctrl+N | New session (opens the Site Manager) |
| Ctrl+R | Refresh both panes |
| F2 | Rename the selected item |
| F5 | Copy: upload or download, depending on the focused pane |
| F6 | Move: copy, then delete the source |
| F7 | New folder |
| F8 | Delete (asks first if Options > Confirm deletes is on) |
| F9 | Properties; on the remote pane you can change permissions (chmod) |
| F10 / Alt+F4 | Quit |
| Backspace | Go to the parent folder |
| Enter / double-click | Open a folder, or open a file |

## Connecting to a server

Open Session > Site Manager (Ctrl+S). Click New, then fill in:
  • Name: a label for the list.
  • Host name and Port (22 by default).
  • User name.
  • Authentication: see "Password and key authentication".
  • Remote directory (optional): the folder to open after login. If it is empty, Skiff opens your remote home folder.
  • Local directory (optional): the folder the left pane jumps to on login.
  • Timeout (s): how long to wait for the server, 5 to 120 seconds.
Click Save to store the site, or Login to save and connect. Duplicate copies a site; Delete removes it. Session > Disconnect closes the connection.

Skiff uses python3-paramiko when it is installed (EPEL). Otherwise it drives the system OpenSSH tools (ssh and sftp), so your ~/.ssh/config, ssh-agent and keys are used as usual. With the OpenSSH backend, the server needs python3 to list folders.

## Host keys

"Verify host key against ~/.ssh/known_hosts" is on by default for new sites.
  • With paramiko, a host that is not in ~/.ssh/known_hosts is refused, and a key that changed is reported as a host key mismatch.
  • With OpenSSH, ssh runs with StrictHostKeyChecking=yes.
To trust a new server, connect once from a terminal (ssh -p PORT user@host) and accept the key after you check its fingerprint. If you untick the box, Skiff accepts new keys: OpenSSH saves them (accept-new) and paramiko accepts them for that session only.
If the key changed on purpose (the server was rebuilt), remove the old line with ssh-keygen -R host (or -R '[host]:port') and connect again.

## Password and key authentication

Authentication has three choices:
  • SSH agent / default keys: uses ssh-agent and the keys in ~/.ssh. This is the closest match to WinSCP with Pageant.
  • Private key file: pick the key with the … button. If the key has a passphrase, put it in the "Password / key passphrase" field.
  • Password: type the password. Tick "Remember password" to store it in ~/.config/skiff/sites.json (mode 600). If you leave it unticked, the password is not written to disk and you type it again next time.
Password login works best with paramiko. Without it, Skiff hands the password to ssh through a temporary SSH_ASKPASS helper that is deleted on disconnect.

## Browsing files

Each pane has a path box, plus Parent, Home, Root and Refresh buttons. Type a path and press Enter to jump there. Click a column header to sort. Folders are listed in bold.
Double-click or press Enter on a folder to open it; Backspace goes up a level.
Double-click a local file to open it with your desktop's default app. Double-click a remote file to download it to /tmp/skiff-open-<name> and open that copy. Changes to that copy are not uploaded back.
Mark > Show hidden files shows dot files in both panes.

## Uploading and downloading

Click in the pane you want to copy from, select one or more files or folders, and press F5 (Copy) or F6 (Move). Files go to the folder shown in the other pane, and folders are copied with everything in them.
  • Local pane focused: upload to the remote folder.
  • Remote pane focused: download to the local folder.
Move copies first and deletes the source only after the copy succeeds.
Drag and drop also works. Drop files from the local pane or your file manager onto the remote pane to upload. Drag selected remote files onto the local pane to download.

## Transfer queue

Every copy, move, drop and remote open becomes a row in the queue at the bottom of the window. The row shows the direction, the source, the destination and the progress. Jobs run one at a time, in order. When the queue is empty, both panes refresh. A failed job shows its error in the queue and the next job starts.

## Other file operations

  • F7 New folder: creates a folder in the focused pane.
  • F8 Delete: deletes the selection. Folders are deleted with everything in them. Options > Confirm deletes (on by default) asks first.
  • F2 Rename: renames the selected item.
  • F9 Properties: shows name, path, type, size, date, permissions, owner and group. On the remote pane you can enter a new octal mode (e.g. 644) to chmod the file.

## Settings and config files

Skiff keeps its files in ~/.config/skiff/ ($XDG_CONFIG_HOME/skiff if that is set). The folder is mode 700 and the files are mode 600.
  • sites.json: saved sites. Passwords are stored only for sites with "Remember password" ticked.
  • settings.json: window size, queue height, show hidden files and confirm deletes.
To start fresh, quit Skiff and delete ~/.config/skiff/. To move your sites to another computer, copy sites.json.

## Troubleshooting

  • "Host key mismatch" or "not found in known_hosts": see Host keys.
  • "Authentication failed": check the user name and auth type. For key auth, check that the key file exists and the server has the public key in ~/.ssh/authorized_keys. For agent auth, run ssh-add -l to see loaded keys.
  • "Could not connect … timed out": check the host, the port, and that sshd is running and the firewall allows it.
  • Password login fails without paramiko: install python3-paramiko from EPEL (sudo dnf install epel-release, then sudo dnf install python3-paramiko).
  • Remote folders do not list with the OpenSSH backend: the server needs python3, or install python3-paramiko on this computer.
  • Window looks wrong on Wayland: try QT_QPA_PLATFORM=xcb skiff.
  • Command-line: skiff --help and skiff --version.
