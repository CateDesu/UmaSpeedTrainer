#!/usr/bin/env python3
"""Private Linux runtime files shared by the trainer controls."""

import contextlib
import errno
import fcntl
import math
import os
import re
from pathlib import Path
import shlex
import stat
import subprocess
import sys


def _unsafe(path):
    return PermissionError(errno.EPERM, "runtime path must be private and owned by you", path)


def _ancestor(fd, path):
    info = os.fstat(fd)
    if info.st_uid not in (0, os.geteuid()):
        raise _unsafe(path)
    if info.st_mode & 0o022 and not info.st_mode & stat.S_ISVTX:
        raise _unsafe(path)


def _directory(path):
    parts = Path(os.path.abspath(path)).parts
    if ".." in Path(path).parts:
        raise ValueError("runtime paths cannot contain '..'")
    fd = os.open("/", os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        _ancestor(fd, path)
        for part in parts[1:]:
            next_fd = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=fd)
            os.close(fd)
            fd = next_fd
            _ancestor(fd, path)
        return fd
    except BaseException:
        os.close(fd)
        raise


def _private(fd, path):
    info = os.fstat(fd)
    if info.st_uid != os.geteuid() or info.st_mode & 0o077:
        raise _unsafe(path)


def runtime_path(kind):
    override = os.environ.get(f"UMA_HOOK_{kind.upper()}")
    if override:
        return override
    base = os.environ.get("XDG_RUNTIME_DIR")
    name = "uma-hook" if base else f"uma-hook-{os.geteuid()}"
    base = base or "/tmp"
    base_fd = _directory(base)
    try:
        if os.environ.get("XDG_RUNTIME_DIR"):
            _private(base_fd, base)
        try:
            os.mkdir(name, 0o700, dir_fd=base_fd)
        except FileExistsError:
            pass
        fd = os.open(name, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=base_fd)
        try:
            _private(fd, os.path.join(base, name))
        finally:
            os.close(fd)
    finally:
        os.close(base_fd)
    return os.path.join(base, name, "control" if kind == "ctrl" else "hook.log")


@contextlib.contextmanager
def open_runtime(path, flags):
    parent, name = os.path.split(path)
    if not name or name in (".", ".."):
        raise ValueError("runtime path must name a file")
    parent_fd = _directory(parent or ".")
    fd = None
    try:
        _private(parent_fd, parent or ".")
        fd = os.open(name, flags | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                     0o600, dir_fd=parent_fd)
        info = os.fstat(fd)
        if not stat.S_ISREG(info.st_mode) or info.st_nlink != 1:
            raise _unsafe(path)
        _private(fd, path)
        yield fd
    finally:
        if fd is not None:
            os.close(fd)
        os.close(parent_fd)


def read_speed():
    with open_runtime(runtime_path("ctrl"), os.O_RDONLY) as fd:
        fcntl.flock(fd, fcntl.LOCK_SH | fcntl.LOCK_NB)
        text = os.read(fd, 64)
        if len(text) >= 64 or not re.fullmatch(
            rb"[ \t\r\n]*[+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][+-]?[0-9]+)?[ \t\r\n]*",
            text,
        ):
            raise ValueError("invalid speed")
        value = float(text)
    if not math.isfinite(value) or not 0 < value <= 1000:
        raise ValueError("speed must be > 0 and <= 1000")
    return value


def write_speed(value):
    value = float(value)
    if not math.isfinite(value) or not 0 < value <= 1000:
        raise ValueError("speed must be > 0 and <= 1000")
    with open_runtime(runtime_path("ctrl"), os.O_WRONLY | os.O_CREAT) as fd:
        fcntl.flock(fd, fcntl.LOCK_EX)
        os.ftruncate(fd, 0)
        os.write(fd, f"{value:g}".encode("ascii"))


def main(args):
    command = args[0]
    if command == "path":
        print(runtime_path(args[1]))
    elif command == "speed":
        if len(args) == 1:
            print(f"current: {read_speed():g}x")
        else:
            value = 1 if args[1] in ("off", "reset") else args[1]
            write_speed(value)
            print(f"speed: {float(value):g}x")
    elif command == "initialize":
        write_speed(1)
        with open_runtime(runtime_path("log"), os.O_WRONLY | os.O_CREAT) as fd:
            os.ftruncate(fd, 0)
            lines = (f"[launch.sh] speed=1 filter={os.environ.get('UMA_HOOK_FILTER', '')}\n"
                     f"[launch.sh] LD_PRELOAD={args[1]}\n"
                     f"[launch.sh] argv: {shlex.join(args[2:])}\n\n")
            os.write(fd, lines.encode())
    elif command == "watch":
        path = runtime_path("log")
        with open_runtime(path, os.O_RDONLY) as fd:
            print(f"Tailing {path}  (Ctrl-C to stop)", flush=True)
            return subprocess.call(["tail", "--follow=descriptor", f"/proc/self/fd/{fd}"], pass_fds=(fd,))
    else:
        raise ValueError("unknown runtime command")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except (OSError, ValueError, UnicodeError) as error:
        print(f"uma_hook: {error}", file=sys.stderr)
        sys.exit(1)
