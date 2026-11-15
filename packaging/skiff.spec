%global debug_package %{nil}

Name:           skiff
Version:        1.0.0
Release:        1%{?dist}
Summary:        WinSCP-style dual-pane SFTP client for Rocky Linux 9 and 10
License:        MIT
URL:            https://andersoncomputer.us
Source0:        %{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3
BuildRequires:  desktop-file-utils

Requires:       python3
Requires:       openssh-clients
Requires:       python3-cryptography

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
* Sat Nov 14 2026 Mike Anderson <mike@andersoncomputer.us> - 1.0.0-1
- Initial release as Skiff SFTP for Rocky Linux 9 (PyQt5) and 10 (PyQt6)
- Use system python3-paramiko (EPEL) instead of a vendored copy
- Add --help and --version command-line options
- Add Help > Skiff Help (F1) and Help > About Skiff pages; F10 quits
- Fix PyQt6 (Rocky 10) crash on startup (QFrame.NoFrame scoped enum)
- Fix OpenSSH backend port option for sftp (-P) on non-22 ports
- Fix OpenSSH backend remote commands (quote arguments for the remote shell)
- Fix askpass helper treating the password as a printf format
