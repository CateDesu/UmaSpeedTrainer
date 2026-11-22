"""Update the Linux trainer from a release or a Git checkout."""

from contextlib import ExitStack, contextmanager, suppress
from dataclasses import dataclass
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, HTTPSHandler, Request, build_opener


REPO = "CateDesu/UmaSpeedTrainer"
ASSET = "UmaSpeedTrainer-linux-x86_64"
RUNNING_PROGRAM = Path("/proc/self/exe")
CHUNK_SIZE = 1024 * 1024


class UpdateError(Exception):
    pass


@dataclass(frozen=True)
class Release:
    tag: str
    size: int
    digest: str


class HTTPSRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        if urlsplit(newurl).scheme != "https":
            raise UpdateError("GitHub redirected the download to an insecure address.")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def _open(url, accept):
    context = ssl.create_default_context()
    # The bundled OpenSSL's default paths may differ from the host's.
    if not os.environ.get("SSL_CERT_FILE"):
        for bundle in ("/etc/ssl/certs/ca-certificates.crt", "/etc/pki/tls/certs/ca-bundle.crt"):
            if os.path.isfile(bundle):
                context.load_verify_locations(bundle)
                break
    request = Request(url, headers={"Accept": accept, "User-Agent": ASSET})
    return build_opener(HTTPSHandler(context=context), HTTPSRedirects()).open(request, timeout=15)


def _check_target(program, running):
    target = program.lstat()
    if not os.path.samestat(target, os.fstat(running.fileno())):
        raise UpdateError("The executable changed on disk. Reopen the trainer and try again.")
    return target


def check_for_update(program):
    try:
        with _open(f"https://api.github.com/repos/{REPO}/releases/latest",
                   "application/vnd.github+json") as response:
            release = json.loads(response.read(2 * CHUNK_SIZE))
    except HTTPError as error:
        if error.code == 404:
            raise UpdateError("No official release is published yet.") from error
        raise
    except ValueError as error:
        raise UpdateError("GitHub returned invalid release information.") from error

    tag = release.get("tag_name") if isinstance(release, dict) else None
    if not isinstance(tag, str) or not re.fullmatch(r"v[\w.-]+", tag, re.ASCII):
        raise UpdateError("GitHub returned an invalid release tag.")
    assets = release.get("assets")
    for asset in assets if isinstance(assets, list) else ():
        if isinstance(asset, dict) and asset.get("name") == ASSET:
            break
    else:
        raise UpdateError(f"{tag} has no portable Linux download.")

    digest = asset.get("digest")
    size = asset.get("size")
    if not isinstance(digest, str) or not re.fullmatch(r"sha256:[a-f0-9]{64}", digest):
        raise UpdateError("GitHub did not provide a valid download checksum.")
    if type(size) is not int or size < 20:
        raise UpdateError("GitHub did not provide a valid download size.")

    with RUNNING_PROGRAM.open("rb") as running:
        target = _check_target(program, running)
        if target.st_size == size:
            current = hashlib.sha256()
            while chunk := running.read(CHUNK_SIZE):
                current.update(chunk)
            if current.hexdigest() == digest[7:]:
                return None
    return Release(tag, size, digest[7:])


def install_update(program, release):
    url = f"https://github.com/{REPO}/releases/download/{release.tag}/{ASSET}"
    with RUNNING_PROGRAM.open("rb") as running:
        # Other GUI instances of this executable share the same inode lock.
        try:
            fcntl.flock(running, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise UpdateError("Another trainer window is installing an update.") from error
        target = _check_target(program, running)
        pending = None
        try:
            with tempfile.NamedTemporaryFile(dir=program.parent, prefix=".uma-update-", delete=False) as file:
                pending = Path(file.name)
                digest = hashlib.sha256()
                size = 0
                with _open(url, "application/octet-stream") as response:
                    while chunk := response.read(CHUNK_SIZE):
                        size += len(chunk)
                        if size > release.size:
                            raise UpdateError("The download exceeded the expected size.")
                        digest.update(chunk)
                        file.write(chunk)
                if size != release.size or digest.hexdigest() != release.digest:
                    raise UpdateError("The download did not match the published checksum and size.")
                file.seek(0)
                header = file.read(20)
                if not header.startswith(b"\x7fELF\x02\x01\x01") or header[18:20] != b"\x3e\x00":
                    raise UpdateError("The download is not a Linux x86_64 executable.")
                os.fchmod(file.fileno(), target.st_mode & 0o777)
                os.fsync(file.fileno())
            _check_target(program, running)
            os.replace(pending, program)
            pending = None
        finally:
            if pending is not None:
                pending.unlink(missing_ok=True)


@dataclass(frozen=True)
class SourceUpdate:
    branch: str
    head: str
    commit: str


def _run(directory, *args):
    result = subprocess.run(args, cwd=directory, stdin=subprocess.DEVNULL,
                            capture_output=True, text=True, errors="replace", timeout=120,
                            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"})
    if result.returncode:
        raise UpdateError(result.stderr.strip() or f"{args[0]} failed.")
    return result.stdout.strip()


def _checkout(directory):
    if _run(directory, "git", "--no-optional-locks", "status", "--porcelain", "--untracked-files=no"):
        raise UpdateError("Commit or stash your local changes before updating.")
    branch = _run(directory, "git", "branch", "--show-current")
    if not branch:
        raise UpdateError("Switch to a branch with an upstream before updating.")
    return branch, _run(directory, "git", "rev-parse", "HEAD")


def _git_path(directory, name):
    return directory / _run(directory, "git", "rev-parse", "--git-path", name)


def check_source_update(directory):
    directory = Path(directory)
    branch, head = _checkout(directory)
    if _git_path(directory, "uma-update-pending").exists():
        return SourceUpdate(branch, head, head)
    ref = f"refs/heads/{branch}"
    tracking = _run(directory, "git", "for-each-ref",
                    "--format=%(upstream:remotename)%00%(upstream:remoteref)%00%(upstream)", ref)
    remote, remote_ref, upstream = tracking.split("\0")
    if not remote or remote == "." or not remote_ref or not upstream:
        raise UpdateError("Set a remote tracking branch before updating.")
    _run(directory, "git", "fetch", "--no-tags", "--", remote, f"+{remote_ref}:{upstream}")
    commit = _run(directory, "git", "rev-parse", upstream)
    ahead, behind = _run(directory, "git", "rev-list", "--left-right", "--count",
                         f"{head}...{commit}").split()
    if behind == "0":
        return None
    if ahead != "0":
        raise UpdateError("Your branch and its upstream have diverged. Reconcile them before updating.")
    return SourceUpdate(branch, head, commit)


def install_source_update(directory, update):
    directory = Path(directory)
    with _git_path(directory, "uma-update.lock").open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as error:
            raise UpdateError("Another trainer window is installing an update.") from error
        pending = _git_path(directory, "uma-update-pending")
        index_lock = Path(f"{_git_path(directory, 'index')}.lock")
        if pending.exists() and index_lock.exists() and pending.samefile(index_lock):
            index_lock.unlink()
        _build_source_update(directory, update, pending, index_lock)


@contextmanager
def _lock_checkout(directory, commit, pending, index_lock):
    # The hard link lets the next updater reclaim its index lock after an interruption.
    try:
        os.link(pending, index_lock)
    except FileExistsError as error:
        raise UpdateError("Git is changing the checkout. Check for updates again.") from error
    try:
        # Git holds HEAD and branch locks until the transaction's input closes.
        # Older Git buffers its replies unless stdout is line-buffered.
        with tempfile.TemporaryFile(mode="w+t") as errors, subprocess.Popen(
            ["stdbuf", "-oL", "git", "-c", "core.hooksPath=/dev/null", "update-ref", "--stdin"],
            cwd=directory, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=errors, text=True,
            start_new_session=True,
        ) as refs:
            try:
                refs.stdin.write(f"start\nverify HEAD {commit}\nprepare\n")
                refs.stdin.flush()
                if refs.stdout.readline() != "start: ok\n" or refs.stdout.readline() != "prepare: ok\n":
                    errors.seek(0)
                    raise UpdateError(errors.read().strip() or "The checkout changed. Check for updates again.")
                yield
            finally:
                refs.stdin.close()
    finally:
        index_lock.unlink()


def _advance_source(directory, update):
    # updateInstead fast-forwards the named branch and its worktree. Protect ignored
    # local files too, including a file that blocks a new directory.
    names = subprocess.check_output(["git", "diff", "--no-renames", "--name-only", "-z",
                                     "--diff-filter=AT", update.head, update.commit, "--"], cwd=directory)
    for name in names.split(b"\0"):
        if not name:
            continue
        path = Path(os.fsdecode(name))
        for part in (*reversed(path.parents), path):
            current = directory / part
            if current.is_symlink() or (current.exists() and (part == path or not current.is_dir())):
                if _run(directory, "git", "--literal-pathspecs", "ls-files", "--others", "--", str(part)):
                    raise UpdateError(f"A local file would be overwritten at {part}.")
                break

    ref = f"refs/heads/{update.branch}"
    # send-pack takes a literal local path, bypassing remote URL rewrite rules.
    receive = ("git -c core.hooksPath=/dev/null -c receive.denyCurrentBranch=updateInstead "
               "-c receive.denyNonFastForwards=true receive-pack")
    _run(directory, "git", "send-pack", f"--receive-pack={receive}",
         f"--force-with-lease={ref}:{update.head}", str(directory.resolve()), f"{update.commit}:{ref}")


def _build_source_update(directory, update, pending, index_lock):
    expected = (update.branch, update.head)
    if _checkout(directory) != expected:
        raise UpdateError("The checkout changed. Check for updates again.")
    hooks = [Path("lib64/libuma_hook.so")]
    if (directory / "lib/libuma_hook.so").exists():
        hooks.append(Path("lib/libuma_hook.so"))

    with tempfile.TemporaryDirectory(prefix="uma-build-") as temp, ExitStack() as staged:
        build = Path(temp) / "checkout"
        _run(directory, "git", "init", "--quiet", str(build))
        _run(build, "git", "fetch", "--no-tags", "--depth=1", "--", str(directory.resolve()), update.commit)
        _run(build, "git", "checkout", "--detach", update.commit)
        if _run(build, "git", "ls-files", "--", *map(str, hooks)):
            raise UpdateError("The update tracks a file at a hook build path.")
        _run(build, "make", *map(str, hooks))

        replacements = []
        for hook in hooks:
            if not (build / hook).is_file():
                raise UpdateError(f"The build did not produce {hook}.")
            target = directory / hook
            target.parent.mkdir(exist_ok=True)
            if target.is_dir():
                raise UpdateError(f"The hook path is a directory: {target}")
            with tempfile.NamedTemporaryFile(prefix=".uma-update-", suffix=".so",
                                             dir=target.parent, delete=False) as file:
                replacement = Path(file.name)
            staged.callback(replacement.unlink, missing_ok=True)
            shutil.copy(build / hook, replacement)
            replacements.append((replacement, target))

        if _checkout(directory) != expected:
            pending.touch()
            raise UpdateError("The checkout changed. Check for updates again.")
        # Keep the marker until all hooks have been replaced for the checked-out commit.
        was_pending = pending.exists()
        pending.touch()
        if update.head != update.commit:
            try:
                _advance_source(directory, update)
            except UpdateError:
                if not was_pending:
                    with suppress(UpdateError, OSError, subprocess.SubprocessError):
                        if _checkout(directory) == expected:
                            pending.unlink()
                raise
        with _lock_checkout(directory, update.commit, pending, index_lock):
            if _checkout(directory) != (update.branch, update.commit):
                raise UpdateError("The checkout changed. Check for updates again.")
            for replacement, target in replacements:
                replacement.replace(target)
        pending.unlink()
