"""SFTP backends: paramiko (preferred) and OpenSSH (fallback)."""

from __future__ import annotations

import json
import os
import shlex
import socket
import stat
import subprocess
import tempfile
import time
from typing import Callable, Dict, List, Optional

from .models import FileEntry, posix_join, posix_parent

ProgressCb = Optional[Callable[[int, int], None]]


class SftpError(Exception):
    pass


class BaseSftp:
    def connect(self, site: Dict) -> str:
        raise NotImplementedError

    def close(self) -> None:
        raise NotImplementedError

    def listdir(self, path: str, show_hidden: bool) -> List[FileEntry]:
        raise NotImplementedError

    def mkdir(self, path: str) -> None:
        raise NotImplementedError

    def remove(self, path: str, is_dir: bool) -> None:
        raise NotImplementedError

    def rename(self, src: str, dst: str) -> None:
        raise NotImplementedError

    def chmod(self, path: str, mode: int) -> None:
        raise NotImplementedError

    def download(self, remote: str, local: str, progress: ProgressCb = None) -> None:
        raise NotImplementedError

    def upload(self, local: str, remote: str, progress: ProgressCb = None) -> None:
        raise NotImplementedError

    def download_tree(self, remote: str, local: str, progress: ProgressCb = None) -> None:
        raise NotImplementedError

    def upload_tree(self, local: str, remote: str, progress: ProgressCb = None) -> None:
        raise NotImplementedError

    def home(self) -> str:
        return "/"

    def normalize(self, path: str) -> str:
        return path or "/"


def create_backend():
    try:
        import paramiko  # noqa: F401
        return ParamikoBackend()
    except ImportError:
        return OpenSSHBackend()


class ParamikoBackend(BaseSftp):
    def __init__(self):
        self._client = None
        self._sftp = None
        self._home = "/"

    def connect(self, site: Dict) -> str:
        import paramiko

        host = (site.get("host") or "").strip()
        if not host:
            raise SftpError("Host is required")
        port = int(site.get("port") or 22)
        username = (site.get("username") or "").strip()
        if not username:
            raise SftpError("Username is required")
        timeout = int(site.get("timeout") or 20)
        auth = site.get("auth") or "agent"

        client = paramiko.SSHClient()
        known = os.path.expanduser("~/.ssh/known_hosts")
        if os.path.isfile(known):
            client.load_host_keys(known)
        if site.get("strict_host", True):
            client.set_missing_host_key_policy(paramiko.RejectPolicy())
        else:
            client.set_missing_host_key_policy(paramiko.AutoAddPolicy())

        kwargs = {
            "hostname": host,
            "port": port,
            "username": username,
            "timeout": timeout,
            "allow_agent": auth in ("agent", "key"),
            "look_for_keys": auth == "agent",
        }
        if auth == "password":
            kwargs["password"] = site.get("password") or ""
            kwargs["allow_agent"] = False
            kwargs["look_for_keys"] = False
        elif auth == "key":
            key_file = os.path.expanduser(site.get("key_file") or "")
            if not key_file or not os.path.isfile(key_file):
                raise SftpError("Private key file is missing")
            kwargs["key_filename"] = key_file
            if site.get("password"):
                kwargs["passphrase"] = site.get("password")

        try:
            client.connect(**kwargs)
        except paramiko.ssh_exception.BadHostKeyException as exc:
            raise SftpError(
                "Host key mismatch for %s. Remove the old key from ~/.ssh/known_hosts if this is expected."
                % host
            ) from exc
        except paramiko.AuthenticationException as exc:
            raise SftpError("Authentication failed for %s@%s" % (username, host)) from exc
        except (paramiko.SSHException, socket.error, OSError) as exc:
            raise SftpError("Could not connect to %s:%s — %s" % (host, port, exc)) from exc

        try:
            sftp = client.open_sftp()
        except Exception as exc:
            client.close()
            raise SftpError("SFTP subsystem failed: %s" % exc) from exc

        self.close()
        self._client = client
        self._sftp = sftp
        try:
            self._home = sftp.normalize(".")
        except Exception:
            self._home = "/"
        return self._home

    def close(self) -> None:
        if self._sftp is not None:
            try:
                self._sftp.close()
            except Exception:
                pass
            self._sftp = None
        if self._client is not None:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None

    def _need(self):
        if self._sftp is None:
            raise SftpError("Not connected")
        return self._sftp

    def home(self) -> str:
        return self._home

    def normalize(self, path: str) -> str:
        sftp = self._need()
        try:
            return sftp.normalize(path or ".")
        except Exception:
            return path or "/"

    def listdir(self, path: str, show_hidden: bool) -> List[FileEntry]:
        sftp = self._need()
        path = path or self._home
        entries: List[FileEntry] = []
        parent = posix_parent(path)
        if parent is not None:
            entries.append(
                FileEntry(name="..", path=parent, size=0, mtime=0, mode=stat.S_IFDIR, is_dir=True)
            )
        try:
            raw = sftp.listdir_attr(path)
        except IOError as exc:
            raise SftpError("Cannot list %s: %s" % (path, exc)) from exc
        for attr in raw:
            name = attr.filename
            if name in (".", ".."):
                continue
            if not show_hidden and name.startswith("."):
                continue
            mode = int(getattr(attr, "st_mode", 0) or 0)
            is_dir = stat.S_ISDIR(mode) if mode else False
            is_link = stat.S_ISLNK(mode) if mode else False
            # Follow links that point at directories so double-click works.
            if is_link:
                try:
                    target = sftp.stat(posix_join(path, name))
                    tmode = int(getattr(target, "st_mode", 0) or 0)
                    if stat.S_ISDIR(tmode):
                        is_dir = True
                except Exception:
                    pass
            entries.append(
                FileEntry(
                    name=name,
                    path=posix_join(path, name),
                    size=int(getattr(attr, "st_size", 0) or 0),
                    mtime=float(getattr(attr, "st_mtime", 0) or 0),
                    mode=mode,
                    is_dir=is_dir,
                    is_link=is_link,
                    owner=str(getattr(attr, "st_uid", "")),
                    group=str(getattr(attr, "st_gid", "")),
                )
            )
        entries.sort(key=lambda e: (not e.is_parent, not e.is_dir, e.name.lower()))
        return entries

    def mkdir(self, path: str) -> None:
        try:
            self._need().mkdir(path)
        except IOError as exc:
            raise SftpError("mkdir failed: %s" % exc) from exc

    def remove(self, path: str, is_dir: bool) -> None:
        sftp = self._need()
        try:
            if is_dir:
                self._rmtree(sftp, path)
            else:
                sftp.remove(path)
        except IOError as exc:
            raise SftpError("Delete failed: %s" % exc) from exc

    def _rmtree(self, sftp, path: str) -> None:
        for attr in sftp.listdir_attr(path):
            name = attr.filename
            if name in (".", ".."):
                continue
            child = posix_join(path, name)
            mode = int(getattr(attr, "st_mode", 0) or 0)
            if stat.S_ISDIR(mode):
                self._rmtree(sftp, child)
            else:
                sftp.remove(child)
        sftp.rmdir(path)

    def rename(self, src: str, dst: str) -> None:
        try:
            self._need().posix_rename(src, dst) if hasattr(self._need(), "posix_rename") else self._need().rename(src, dst)
        except IOError as exc:
            raise SftpError("Rename failed: %s" % exc) from exc

    def chmod(self, path: str, mode: int) -> None:
        try:
            self._need().chmod(path, mode)
        except IOError as exc:
            raise SftpError("chmod failed: %s" % exc) from exc

    def download(self, remote: str, local: str, progress: ProgressCb = None) -> None:
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)

        def cb(done, total):
            if progress:
                progress(int(done), int(total or 0))

        try:
            self._need().get(remote, local, callback=cb)
        except IOError as exc:
            raise SftpError("Download failed: %s" % exc) from exc

    def upload(self, local: str, remote: str, progress: ProgressCb = None) -> None:
        def cb(done, total):
            if progress:
                progress(int(done), int(total or 0))

        try:
            self._need().put(local, remote, callback=cb)
        except IOError as exc:
            raise SftpError("Upload failed: %s" % exc) from exc

    def download_tree(self, remote: str, local: str, progress: ProgressCb = None) -> None:
        os.makedirs(local, exist_ok=True)
        for entry in self.listdir(remote, show_hidden=True):
            if entry.is_parent:
                continue
            dest = os.path.join(local, entry.name)
            if entry.is_dir:
                self.download_tree(entry.path, dest, progress)
            else:
                self.download(entry.path, dest, progress)

    def upload_tree(self, local: str, remote: str, progress: ProgressCb = None) -> None:
        try:
            self._need().stat(remote)
        except IOError:
            self.mkdir(remote)
        for name in os.listdir(local):
            src = os.path.join(local, name)
            dest = posix_join(remote, name)
            if os.path.isdir(src):
                self.upload_tree(src, dest, progress)
            else:
                self.upload(src, dest, progress)


class OpenSSHBackend(BaseSftp):
    """Fallback using system OpenSSH (keys, ssh-agent, ~/.ssh/config)."""

    def __init__(self):
        self._site = None
        self._home = "/"
        self._askpass = None

    def connect(self, site: Dict) -> str:
        host = (site.get("host") or "").strip()
        if not host:
            raise SftpError("Host is required")
        username = (site.get("username") or "").strip()
        if not username:
            raise SftpError("Username is required")
        self._cleanup_askpass()
        self._site = dict(site)
        if site.get("auth") == "password" and site.get("password"):
            self._askpass = self._write_askpass(site["password"])
        # Probe + discover home.
        code, out, err = self._ssh(["pwd"], timeout=int(site.get("timeout") or 20))
        if code != 0:
            raise SftpError(err.strip() or out.strip() or "SSH connection failed")
        self._home = out.strip().splitlines()[-1] if out.strip() else "/"
        return self._home

    def close(self) -> None:
        self._cleanup_askpass()
        self._site = None

    def home(self) -> str:
        return self._home

    def _target(self) -> str:
        site = self._site or {}
        return "%s@%s" % (site.get("username"), site.get("host"))

    def _base_opts(self, sftp: bool = False) -> List[str]:
        # ssh takes the port as -p; sftp uses -P (its -p means "preserve").
        site = self._site or {}
        opts = [
            "-o", "BatchMode=%s" % ("no" if site.get("auth") == "password" else "yes"),
            "-o", "StrictHostKeyChecking=%s" % ("yes" if site.get("strict_host", True) else "accept-new"),
            "-o", "ConnectTimeout=%s" % int(site.get("timeout") or 20),
            "-P" if sftp else "-p", str(int(site.get("port") or 22)),
        ]
        if site.get("auth") == "key" and site.get("key_file"):
            opts += ["-i", os.path.expanduser(site["key_file"])]
        return opts

    def _env(self) -> Dict[str, str]:
        env = os.environ.copy()
        if self._askpass:
            env["SSH_ASKPASS"] = self._askpass
            env["SSH_ASKPASS_REQUIRE"] = "force"
            env["DISPLAY"] = env.get("DISPLAY") or ":0"
        return env

    def _write_askpass(self, password: str) -> str:
        fd, path = tempfile.mkstemp(prefix="skiff-askpass-", suffix=".sh")
        os.close(fd)
        with open(path, "w", encoding="utf-8") as fh:
            # Pass the password as an argument, not as the printf format,
            # so passwords containing % or backslashes are sent verbatim.
            fh.write("#!/bin/sh\nprintf '%%s\\n' '%s'\n" % password.replace("'", "'\\''"))
        os.chmod(path, 0o700)
        return path

    def _cleanup_askpass(self) -> None:
        if self._askpass and os.path.isfile(self._askpass):
            try:
                os.remove(self._askpass)
            except OSError:
                pass
        self._askpass = None

    def _ssh(self, remote_cmd: List[str], timeout: int = 60):
        if not self._site:
            raise SftpError("Not connected")
        # ssh joins the remote arguments with spaces and hands them to the
        # remote shell, so quote each one (keeps multi-line scripts and paths
        # with spaces intact).
        remote = " ".join(shlex.quote(arg) for arg in remote_cmd)
        cmd = ["ssh"] + self._base_opts() + [self._target(), "--", remote]
        try:
            proc = subprocess.run(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._env(),
                timeout=timeout,
                check=False,
                start_new_session=True,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SftpError("ssh failed: %s" % exc) from exc
        out = proc.stdout.decode("utf-8", "replace")
        err = proc.stderr.decode("utf-8", "replace")
        return proc.returncode, out, err

    def _sftp_batch(self, lines: List[str], timeout: int = 3600):
        if not self._site:
            raise SftpError("Not connected")
        body = "\n".join(lines) + "\n"
        cmd = ["sftp", "-b", "-"] + self._base_opts(sftp=True) + [self._target()]
        try:
            proc = subprocess.run(
                cmd,
                input=body.encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env=self._env(),
                timeout=timeout,
                check=False,
                start_new_session=True,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise SftpError("sftp failed: %s" % exc) from exc
        err = proc.stderr.decode("utf-8", "replace")
        out = proc.stdout.decode("utf-8", "replace")
        if proc.returncode != 0:
            raise SftpError(err.strip() or out.strip() or "sftp command failed")
        return out

    def listdir(self, path: str, show_hidden: bool) -> List[FileEntry]:
        path = path or self._home
        script = (
            "import json,os,stat,sys\n"
            "p=sys.argv[1]\n"
            "out=[]\n"
            "for n in os.listdir(p):\n"
            "    fp=os.path.join(p,n)\n"
            "    try: st=os.lstat(fp)\n"
            "    except OSError: continue\n"
            "    out.append({'name':n,'size':st.st_size,'mtime':st.st_mtime,"
            "'mode':st.st_mode,'isdir':stat.S_ISDIR(st.st_mode),"
            "'islink':stat.S_ISLNK(st.st_mode),'uid':st.st_uid,'gid':st.st_gid})\n"
            "print(json.dumps(out))\n"
        )
        code, out, err = self._ssh(["python3", "-c", script, path], timeout=30)
        if code != 0:
            raise SftpError(err.strip() or "Remote listing failed (need python3 on the server)")
        try:
            raw = json.loads(out.strip().splitlines()[-1])
        except (json.JSONDecodeError, IndexError) as exc:
            raise SftpError("Could not parse remote listing") from exc
        entries: List[FileEntry] = []
        parent = posix_parent(path)
        if parent is not None:
            entries.append(
                FileEntry(name="..", path=parent, size=0, mtime=0, mode=stat.S_IFDIR, is_dir=True)
            )
        for item in raw:
            name = item["name"]
            if not show_hidden and name.startswith("."):
                continue
            entries.append(
                FileEntry(
                    name=name,
                    path=posix_join(path, name),
                    size=int(item.get("size") or 0),
                    mtime=float(item.get("mtime") or 0),
                    mode=int(item.get("mode") or 0),
                    is_dir=bool(item.get("isdir")),
                    is_link=bool(item.get("islink")),
                    owner=str(item.get("uid", "")),
                    group=str(item.get("gid", "")),
                )
            )
        entries.sort(key=lambda e: (not e.is_parent, not e.is_dir, e.name.lower()))
        return entries

    def mkdir(self, path: str) -> None:
        self._sftp_batch(["-mkdir %s" % _sftp_quote(path)])

    def remove(self, path: str, is_dir: bool) -> None:
        if is_dir:
            code, _, err = self._ssh(["rm", "-rf", "--", path])
            if code != 0:
                raise SftpError(err.strip() or "rm -rf failed")
        else:
            self._sftp_batch(["-rm %s" % _sftp_quote(path)])

    def rename(self, src: str, dst: str) -> None:
        self._sftp_batch(["-rename %s %s" % (_sftp_quote(src), _sftp_quote(dst))])

    def chmod(self, path: str, mode: int) -> None:
        self._sftp_batch(["-chmod %o %s" % (mode & 0o777, _sftp_quote(path))])

    def download(self, remote: str, local: str, progress: ProgressCb = None) -> None:
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        self._sftp_batch(["-get %s %s" % (_sftp_quote(remote), _sftp_quote(local))])
        if progress:
            try:
                progress(os.path.getsize(local), os.path.getsize(local))
            except OSError:
                pass

    def upload(self, local: str, remote: str, progress: ProgressCb = None) -> None:
        self._sftp_batch(["-put %s %s" % (_sftp_quote(local), _sftp_quote(remote))])
        if progress:
            try:
                progress(os.path.getsize(local), os.path.getsize(local))
            except OSError:
                pass

    def download_tree(self, remote: str, local: str, progress: ProgressCb = None) -> None:
        os.makedirs(os.path.dirname(local) or ".", exist_ok=True)
        self._sftp_batch(["-get -r %s %s" % (_sftp_quote(remote), _sftp_quote(local))])

    def upload_tree(self, local: str, remote: str, progress: ProgressCb = None) -> None:
        self._sftp_batch(["-put -r %s %s" % (_sftp_quote(local), _sftp_quote(remote))])


def _sftp_quote(path: str) -> str:
    return "'" + path.replace("'", r"'\''") + "'"
