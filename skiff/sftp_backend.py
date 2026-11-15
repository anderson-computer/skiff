"""SFTP backends: paramiko (preferred) and OpenSSH (fallback)."""

from __future__ import annotations

import json
import os
import shlex
import socket
import stat
import subprocess
import time
from typing import Callable, Dict, List, Optional

from . import sudo as sudo_mod
from .models import FileEntry, posix_join, posix_parent

ProgressCb = Optional[Callable[[int, int], None]]


class SftpError(Exception):
    pass


class BaseSftp:
    #: The user the remote SFTP server runs as when the site uses sudo
    #: ("" = the login user, no sudo).
    sudo_user = ""

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

        as_user = ""
        try:
            if sudo_mod.enabled(site):
                sftp, as_user = self._open_sudo_sftp(paramiko, client, site, username, timeout)
            else:
                sftp = client.open_sftp()
        except SftpError:
            client.close()
            raise
        except Exception as exc:
            client.close()
            raise SftpError("SFTP subsystem failed: %s" % exc) from exc

        self.close()
        self._client = client
        self._sftp = sftp
        self.sudo_user = as_user
        try:
            self._home = sftp.normalize(".")
        except Exception:
            self._home = "/"
        return self._home

    @staticmethod
    def _open_sudo_sftp(paramiko, client, site: Dict, username: str, timeout: int):
        """Start sftp-server through ``sudo -n`` on a session channel and speak
        SFTP over it (no subsystem request, no TTY, no password prompt)."""
        try:
            as_user = sudo_mod.sudo_user(site)
            path = sudo_mod.server_path(site)
        except sudo_mod.SudoConfigError as exc:
            raise SftpError(str(exc)) from exc
        if not path:
            _, out, _ = client.exec_command("sh -c %s" % shlex.quote(sudo_mod.detect_script()), timeout=timeout)
            path = sudo_mod.parse_detect(out.read().decode("utf-8", "replace"))
            if not path:
                raise SftpError(sudo_mod.not_found_message())
        chan = client.get_transport().open_session(timeout=timeout)
        chan.settimeout(timeout)
        chan.exec_command(sudo_mod.sudo_command(as_user, path))
        try:
            sftp = paramiko.SFTPClient(chan)
        except Exception as exc:
            err = _drain_stderr(chan)
            try:
                chan.close()
            except Exception:
                pass
            msg = sudo_mod.explain_failure(err, username, as_user, path)
            raise SftpError(msg or "sudo SFTP server did not start (%s): %s" % (path, err.strip() or exc)) from exc
        chan.settimeout(None)
        return sftp, as_user

    def close(self) -> None:
        self.sudo_user = ""
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
        self._askpass_token = None
        self._askpass_env: Dict[str, str] = {}
        self._sudo_cmd = ""
        self._sudo_info = ("", "", "")  # login user, sudo user, sftp-server path

    def connect(self, site: Dict) -> str:
        host = (site.get("host") or "").strip()
        if not host:
            raise SftpError("Host is required")
        username = (site.get("username") or "").strip()
        if not username:
            raise SftpError("Username is required")
        self._cleanup_askpass()
        self._sudo_cmd = ""
        self.sudo_user = ""
        try:
            as_user = sudo_mod.sudo_user(site) if sudo_mod.enabled(site) else ""
            server = sudo_mod.server_path(site) if as_user else ""
        except sudo_mod.SudoConfigError as exc:
            raise SftpError(str(exc)) from exc
        self._site = dict(site)
        secret = site.get("password") or ""
        if secret and site.get("auth") in ("password", "key"):
            # Hand the password / key passphrase to ssh through the private
            # askpass socket (never a file, argv or environment value).
            from .askpass_server import password_handler, shared_server
            srv = shared_server()
            self._askpass_token = srv.register(password_handler(secret))
            self._askpass_env = srv.env_for(self._askpass_token)
        self._site.pop("password", None)
        # Probe + discover home (and, for sudo, the sftp-server path).
        probe = ["pwd"] if not as_user or server else ["sh", "-c", "pwd; " + sudo_mod.detect_script()]
        code, out, err = self._ssh(probe, timeout=int(site.get("timeout") or 20))
        if code != 0:
            self._cleanup_askpass()
            raise SftpError(err.strip() or out.strip() or "SSH connection failed")
        lines = [l for l in out.strip().splitlines() if not l.startswith(sudo_mod.DETECT_MARK)]
        self._home = lines[0].strip() if lines else "/"
        if as_user:
            server = server or sudo_mod.parse_detect(out)
            if not server:
                self._cleanup_askpass()
                raise SftpError(sudo_mod.not_found_message())
            self._sudo_cmd = sudo_mod.sudo_command(as_user, server)
            self._sudo_info = (site.get("username") or "", as_user, server)
            try:
                out = self._sftp_batch(["pwd"], timeout=int(site.get("timeout") or 20) + 10)
            except SftpError:
                self._cleanup_askpass()
                self._sudo_cmd = ""
                raise
            for line in out.splitlines():
                if line.startswith("Remote working directory:"):
                    self._home = line.split(":", 1)[1].strip() or self._home
            self.sudo_user = as_user
        return self._home

    def close(self) -> None:
        self._cleanup_askpass()
        self._site = None
        self._sudo_cmd = ""
        self.sudo_user = ""

    def home(self) -> str:
        return self._home

    def _target(self) -> str:
        site = self._site or {}
        return "%s@%s" % (site.get("username"), site.get("host"))

    def _base_opts(self, sftp: bool = False) -> List[str]:
        # ssh takes the port as -p; sftp uses -P (its -p means "preserve").
        site = self._site or {}
        opts = [
            "-o", "BatchMode=%s" % ("no" if self._askpass_token else "yes"),
            "-o", "StrictHostKeyChecking=%s" % ("yes" if site.get("strict_host", True) else "accept-new"),
            "-o", "ConnectTimeout=%s" % int(site.get("timeout") or 20),
            "-P" if sftp else "-p", str(int(site.get("port") or 22)),
        ]
        if self._askpass_token:
            # One try with the saved password, so a wrong one can't lock the account.
            opts += ["-o", "NumberOfPasswordPrompts=1"]
        if site.get("auth") == "key" and site.get("key_file"):
            opts += ["-i", os.path.expanduser(site["key_file"])]
        return opts

    def _env(self) -> Dict[str, str]:
        env = os.environ.copy()
        for key in ("SSH_ASKPASS", "SSH_ASKPASS_REQUIRE", "SKIFF_ASKPASS_SOCK", "SKIFF_ASKPASS_TOKEN"):
            env.pop(key, None)
        if self._askpass_token:
            env.update(self._askpass_env)
            env["DISPLAY"] = env.get("DISPLAY") or ":0"
        return env

    def _cleanup_askpass(self) -> None:
        if self._askpass_token:
            from .askpass_server import shared_server
            shared_server().unregister(self._askpass_token)
        self._askpass_token = None
        self._askpass_env = {}

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
        # Options go before "-b": sftp turns -b into "-oBatchMode yes" at the
        # point it parses it, and ssh keeps the first value it sees, so our
        # BatchMode=no (needed for the askpass password) must come first.
        cmd = ["sftp"] + self._base_opts(sftp=True)
        if self._sudo_cmd:
            # Start the remote sftp-server through "sudo -n" instead of the
            # sshd sftp subsystem (-s with a "/" runs it as a command).
            cmd += ["-s", self._sudo_cmd]
        cmd += ["-b", "-", self._target()]
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
            if self._sudo_cmd:
                login, as_user, server = self._sudo_info
                msg = sudo_mod.explain_failure(err, login, as_user, server)
                if msg:
                    raise SftpError(msg)
            raise SftpError(err.strip() or out.strip() or "sftp command failed")
        return out

    def listdir(self, path: str, show_hidden: bool) -> List[FileEntry]:
        path = path or self._home
        if self._sudo_cmd:
            return self._listdir_sftp(path, show_hidden)
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
            last = err.strip().splitlines()[-1] if err.strip() else ""
            raise SftpError("Cannot list %s: %s" % (path, last) if last
                            else "Remote listing failed (need python3 on the server)")
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

    def _listdir_sftp(self, path: str, show_hidden: bool) -> List[FileEntry]:
        # sudo mode: list through the (root) sftp-server, because a remote
        # shell command would run as the login user.
        out = self._sftp_batch(["cd %s" % _sftp_quote(path), "ls -la"], timeout=60)
        entries: List[FileEntry] = []
        parent = posix_parent(path)
        if parent is not None:
            entries.append(
                FileEntry(name="..", path=parent, size=0, mtime=0, mode=stat.S_IFDIR, is_dir=True)
            )
        for name, mode, size, mtime, owner, group in sudo_mod.parse_ls(out):
            if not show_hidden and name.startswith("."):
                continue
            entries.append(
                FileEntry(name=name, path=posix_join(path, name), size=size, mtime=mtime, mode=mode,
                          is_dir=stat.S_ISDIR(mode), is_link=stat.S_ISLNK(mode), owner=owner, group=group)
            )
        entries.sort(key=lambda e: (not e.is_parent, not e.is_dir, e.name.lower()))
        return entries

    def _rmtree_lines(self, path: str) -> List[str]:
        lines: List[str] = []
        for entry in self._listdir_sftp(path, True):
            if entry.is_parent:
                continue
            if entry.is_dir and not entry.is_link:
                lines += self._rmtree_lines(entry.path)
            else:
                lines.append("rm %s" % _sftp_quote(entry.path))
        lines.append("rmdir %s" % _sftp_quote(path))
        return lines

    def mkdir(self, path: str) -> None:
        self._sftp_batch(["-mkdir %s" % _sftp_quote(path)])

    def remove(self, path: str, is_dir: bool) -> None:
        if is_dir and self._sudo_cmd:
            self._sftp_batch(self._rmtree_lines(path))
        elif is_dir:
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


def _drain_stderr(chan, wait: float = 3.0) -> str:
    """Collect what the remote command wrote to stderr before it exited."""
    deadline = time.time() + wait
    chunks = []
    while time.time() < deadline:
        got = False
        while chan.recv_stderr_ready():
            data = chan.recv_stderr(4096)
            if not data:
                break
            chunks.append(data)
            got = True
        if chan.exit_status_ready() and not chan.recv_stderr_ready():
            break
        if not got:
            time.sleep(0.05)
    return b"".join(chunks).decode("utf-8", "replace")
