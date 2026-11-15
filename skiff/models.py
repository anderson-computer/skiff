"""Shared file-entry model used by local and remote panels."""

from __future__ import annotations

import os
import stat
from dataclasses import dataclass
from datetime import datetime
from typing import List, Optional


@dataclass
class FileEntry:
    name: str
    path: str
    size: int
    mtime: float
    mode: int
    is_dir: bool
    is_link: bool = False
    owner: str = ""
    group: str = ""

    @property
    def is_parent(self) -> bool:
        return self.name == ".."

    def type_label(self) -> str:
        if self.is_parent:
            return "Parent"
        if self.is_dir:
            return "Folder"
        if self.is_link:
            return "Link"
        _, ext = os.path.splitext(self.name)
        return (ext[1:].upper() + " file") if ext else "File"

    def size_label(self) -> str:
        if self.is_dir and not self.is_parent:
            return "<DIR>"
        if self.is_parent:
            return ""
        return format_size(self.size)

    def mtime_label(self) -> str:
        if self.is_parent or not self.mtime:
            return ""
        try:
            return datetime.fromtimestamp(self.mtime).strftime("%Y-%m-%d %H:%M")
        except (OverflowError, OSError, ValueError):
            return ""

    def perms_label(self) -> str:
        if self.is_parent:
            return ""
        return format_mode(self.mode)


def format_size(num: int) -> str:
    value = float(num)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024.0 or unit == "TB":
            if unit == "B":
                return "%d B" % int(value)
            return "%.1f %s" % (value, unit)
        value /= 1024.0
    return "%d B" % num


def format_mode(mode: int) -> str:
    if not mode:
        return ""
    chars = ["d" if stat.S_ISDIR(mode) else ("l" if stat.S_ISLNK(mode) else "-")]
    bits = (
        (stat.S_IRUSR, "r"), (stat.S_IWUSR, "w"), (stat.S_IXUSR, "x"),
        (stat.S_IRGRP, "r"), (stat.S_IWGRP, "w"), (stat.S_IXGRP, "x"),
        (stat.S_IROTH, "r"), (stat.S_IWOTH, "w"), (stat.S_IXOTH, "x"),
    )
    for bit, ch in bits:
        chars.append(ch if mode & bit else "-")
    return "".join(chars)


def local_listdir(path: str, show_hidden: bool) -> List[FileEntry]:
    path = os.path.abspath(path)
    entries: List[FileEntry] = []
    parent = os.path.dirname(path)
    if parent != path:
        entries.append(
            FileEntry(
                name="..",
                path=parent,
                size=0,
                mtime=0,
                mode=stat.S_IFDIR,
                is_dir=True,
            )
        )
    try:
        names = os.listdir(path)
    except OSError as exc:
        raise OSError("Cannot read %s: %s" % (path, exc)) from exc
    for name in names:
        if not show_hidden and name.startswith("."):
            continue
        full = os.path.join(path, name)
        try:
            st = os.lstat(full)
        except OSError:
            continue
        entries.append(
            FileEntry(
                name=name,
                path=full,
                size=int(st.st_size),
                mtime=float(st.st_mtime),
                mode=int(st.st_mode),
                is_dir=stat.S_ISDIR(st.st_mode),
                is_link=stat.S_ISLNK(st.st_mode),
                owner=str(st.st_uid),
                group=str(st.st_gid),
            )
        )
    entries.sort(key=lambda e: (not e.is_parent, not e.is_dir, e.name.lower()))
    return entries


def posix_join(base: str, name: str) -> str:
    if not base or base == "/":
        return "/" + name.lstrip("/")
    return base.rstrip("/") + "/" + name


def posix_parent(path: str) -> Optional[str]:
    if not path or path == "/":
        return None
    parent = path.rstrip("/").rsplit("/", 1)[0]
    return parent or "/"
