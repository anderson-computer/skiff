#!/usr/bin/env bash
# Build Skiff SRPM + noarch RPM. Run inside a Rocky Linux 9 or 10 container
# with the source tree mounted at /work. Output goes to /work/out/.
set -euo pipefail
VERSION="1.0.0"
dnf -y -q install rpm-build python3 tar gzip desktop-file-utils
TOP=/root/rpmbuild
mkdir -p ${TOP}/{BUILD,BUILDROOT,RPMS,SOURCES,SPECS,SRPMS}
WORK="${WORK:-/work}"
cd "${WORK}"
tar --exclude=.git --exclude=out --exclude='__pycache__' --exclude='*.pyc' \
    --transform "s,^,skiff-${VERSION}/," \
    -czf ${TOP}/SOURCES/skiff-${VERSION}.tar.gz \
    skiff bin packaging tests README.md HELP.md LICENSE .gitignore build.sh
sed "s/\r$//" packaging/skiff.spec > ${TOP}/SPECS/skiff.spec
rpmbuild -ba --define "_topdir ${TOP}" ${TOP}/SPECS/skiff.spec
mkdir -p "${WORK}/out"
cp -v ${TOP}/RPMS/noarch/skiff-*.rpm ${TOP}/SRPMS/skiff-*.src.rpm ${TOP}/SOURCES/skiff-${VERSION}.tar.gz "${WORK}/out/"
