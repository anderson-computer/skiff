#!/usr/bin/env bash
# Build Skiff SFTP RPMs.
#   ./build.sh            on Rocky/RHEL 9 or 10: native rpmbuild for this release
#   ./build.sh 9 10       anywhere with podman or docker: build in Rocky 9 and 10 containers
# Output: out/skiff-<ver>-1.elN.noarch.rpm, out/skiff-<ver>-1.elN.src.rpm, out/skiff-<ver>.tar.gz
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")"
VERSION="$(sed -n 's/^__version__ = "\(.*\)"/\1/p' skiff/__init__.py)"

if [ $# -gt 0 ]; then
    exec bash packaging/build-rpm.sh "$@"
fi

command -v rpmbuild >/dev/null 2>&1 || {
    echo "rpmbuild not found. Install it:  sudo dnf install -y rpm-build python3 desktop-file-utils" >&2
    echo "Or build in containers:          ./build.sh 9 10" >&2
    exit 1
}
TOP="$(mktemp -d)"
trap 'rm -rf "${TOP}"' EXIT
mkdir -p "${TOP}"/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS} out
tar --exclude=.git --exclude=out --exclude='__pycache__' --exclude='*.pyc' \
    --transform "s,^,skiff-${VERSION}/," \
    -czf "${TOP}/SOURCES/skiff-${VERSION}.tar.gz" \
    skiff bin packaging tests README.md HELP.md LICENSE .gitignore build.sh
cp "${TOP}/SOURCES/skiff-${VERSION}.tar.gz" out/
rpmbuild -ba --define "_topdir ${TOP}" packaging/skiff.spec
cp -v "${TOP}"/RPMS/noarch/skiff-*.rpm "${TOP}"/SRPMS/skiff-*.src.rpm out/
