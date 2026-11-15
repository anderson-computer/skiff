%global debug_package %{nil}

Name:           skiff
Version:        1.2.0
Release:        1%{?dist}
Summary:        WinSCP-style dual-pane SFTP client for Rocky Linux 9 and 10
License:        MIT
URL:            https://andersoncomputer.us
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3
BuildRequires:  desktop-file-utils
# Unit tests in %%check: vault (cryptography) and keychain detection (gi + libsecret).
BuildRequires:  python3-cryptography
BuildRequires:  python3-gobject-base
BuildRequires:  libsecret

Requires:       python3
Requires:       openssh-clients
# AES-256-GCM + scrypt for the encrypted password vault (BaseOS on EL9/EL10).
Requires:       python3-cryptography
# System keychain for saved passwords: libsecret's Secret-1 typelib through
# PyGObject. Both are small and in the stock repos on EL9 and EL10
# (python3-gobject-base: BaseOS, libsecret: AppStream). They are hard
# Requires so the keychain option works on any desktop out of the box; with
# no Secret Service running (headless, over SSH) Skiff greys the option out
# and the encrypted vault is used instead.
Requires:       python3-gobject-base
Requires:       libsecret

# Qt bindings (all from AppStream, no EPEL/CRB needed):
#   EL9  -> PyQt5 (python3-qt5-base)
#   EL10 -> PyQt6 (python3-pyqt6-base); EL10 AppStream has no PyQt5.
%if 0%{?rhel} >= 10
Requires:       python3-pyqt6-base
Recommends:     qt6-qtsvg
Recommends:     qt6-qtwayland
%else
Requires:       python3-qt5-base
Recommends:     qt5-qtsvg
Recommends:     qt5-qtwayland
%endif

# Native SFTP backend. python3-paramiko is in EPEL on both EL9 and EL10.
# Weak dependency: without EPEL, Skiff uses the system OpenSSH ssh/sftp tools.
Recommends:     python3-paramiko

%description
Skiff SFTP is a WinSCP-style dual-pane SFTP client for Rocky Linux 9 and 10.

It uses the Qt Fusion style so the same commander layout (local | remote,
transfer queue, F-keys, site manager) looks and works the same on
KDE Plasma, GNOME, and Cinnamon, including X11 and Wayland.

Features:
 - Site manager with agent, key, and password authentication
 - Dual-pane file manager (copy, move, mkdir, delete, rename, chmod)
 - Drag-and-drop and F5/F6/F7/F8/F9 shortcuts
 - Transfer queue with progress
 - Saved passwords in the system keychain (libsecret) or an encrypted
   vault file (AES-256-GCM, scrypt master password)
 - Optional per-site sudo mode: run the remote sftp-server as root (or
   another user) with passwordless sudo
 - Uses python3-paramiko when installed (EPEL), otherwise system OpenSSH

%prep
%setup -q -n %{name}-%{version}
find . -name '__pycache__' -prune -exec rm -rf {} +
find . -name '*.py[co]' -delete

%build
# pure Python

%install
rm -rf %{buildroot}

install -d %{buildroot}/opt/skiff
cp -a skiff %{buildroot}/opt/skiff/
# SSH_ASKPASS helper run by ssh/sftp.
chmod 0755 %{buildroot}/opt/skiff/skiff/askpass.py

install -d %{buildroot}%{_bindir}
install -m 0755 bin/skiff %{buildroot}%{_bindir}/skiff

install -d %{buildroot}%{_datadir}/applications
install -m 0644 packaging/skiff.desktop %{buildroot}%{_datadir}/applications/skiff.desktop

install -d %{buildroot}%{_datadir}/icons/hicolor/scalable/apps
install -m 0644 skiff/icons/skiff.svg %{buildroot}%{_datadir}/icons/hicolor/scalable/apps/skiff.svg

install -d %{buildroot}%{_datadir}/pixmaps
install -m 0644 skiff/icons/skiff.svg %{buildroot}%{_datadir}/pixmaps/skiff.svg

%check
desktop-file-validate %{buildroot}%{_datadir}/applications/skiff.desktop
PYTHONDONTWRITEBYTECODE=1 python3 -m unittest discover -s tests -v
find . -name '__pycache__' -prune -exec rm -rf {} +

%post
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q %{_datadir}/applications || true
fi
if [ -x /usr/bin/gtk-update-icon-cache ]; then
    gtk-update-icon-cache -q %{_datadir}/icons/hicolor 2>/dev/null || true
fi

%postun
if [ -x /usr/bin/update-desktop-database ]; then
    update-desktop-database -q %{_datadir}/applications || true
fi

%files
%license LICENSE
%doc README.md HELP.md
/opt/skiff/
%{_bindir}/skiff
%{_datadir}/applications/skiff.desktop
%{_datadir}/icons/hicolor/scalable/apps/skiff.svg
%{_datadir}/pixmaps/skiff.svg

%changelog
* Sat Nov 14 2026 Mike Anderson <mike@andersoncomputer.us> - 1.2.0-1
- Site Manager: "Connect with sudo (run SFTP server as root)" with an
  optional sudo user (default root) and sftp-server path (default:
  auto-detect /usr/libexec/openssh, /usr/lib/openssh, /usr/lib/ssh)
- paramiko backend: SFTP over a session channel running
  "sudo -n -u USER sftp-server"; OpenSSH backend: sftp -s with the same
  command, and listings / folder deletes through the SFTP server
- Clear error with a sample NOPASSWD sudoers line when sudo wants a
  password; sudo passwords are never asked for or stored
- Red "sudo: USER" status badge and title suffix; confirm once per
  connection before the first remote upload, move, delete, rename or chmod
- Help: "Connecting with sudo", "Setting up sudoers" and troubleshooting

* Sat Nov 14 2026 Mike Anderson <mike@andersoncomputer.us> - 1.1.0-1
- Saved passwords with the same options as MultiSSH Manager 2.2.0:
  Options > Passwords to choose "Don't save passwords", the system keychain
  (GNOME Keyring / Secret Service via libsecret) or an encrypted vault file
  (AES-256-GCM, scrypt-derived master password), vault file location,
  Change Master Password, Options > Lock Password Vault, and moving or
  deleting saved passwords when the store changes
- Site Manager: "Save password" per site (untick to forget); deleting a site
  deletes its saved password; duplicates don't copy it
- Passwords that 1.0 kept in plain text in sites.json are moved into the
  chosen store on first start; sites.json never holds passwords now
- OpenSSH backend: passwords and key passphrases go to ssh through
  SSH_ASKPASS and a private 0600 Unix socket (peer uid + one-time token)
  instead of a temporary script; one password try per connection
- Fix OpenSSH backend password logins for transfers: sftp's -b forced
  BatchMode=yes, so password sites could list but not upload/download
- Config files are written atomically with mode 0600 from the start
- Requires python3-gobject-base and libsecret (stock BaseOS/AppStream)

* Sat Nov 14 2026 Mike Anderson <mike@andersoncomputer.us> - 1.0.0-1
- Initial release as Skiff SFTP for Rocky Linux 9 (PyQt5) and 10 (PyQt6)
- Use system python3-paramiko (EPEL) instead of a vendored copy
- Add --help and --version command-line options
- Add Help > Skiff Help (F1) and Help > About Skiff pages; F10 quits
- Fix PyQt6 (Rocky 10) crash on startup (QFrame.NoFrame scoped enum)
- Fix OpenSSH backend port option for sftp (-P) on non-22 ports
- Fix OpenSSH backend remote commands (quote arguments for the remote shell)
- Fix askpass helper treating the password as a printf format
