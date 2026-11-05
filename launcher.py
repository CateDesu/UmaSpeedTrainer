"""Shared Steam launcher for source and portable builds."""

import os
from pathlib import Path
import sys
import runtime


def launch(command, directory=None):
    if not command:
        raise ValueError("Usage: launch.sh COMMAND [ARG...]")
    directory = Path(directory or Path(__file__).parent).resolve()
    if ":" in str(directory) or any(c.isspace() for c in str(directory)):
        raise ValueError("The hook directory must not contain whitespace or colons. Set TMPDIR=/tmp.")
    hook = directory / "lib64/libuma_hook.so"
    if not hook.is_file() or not os.access(hook, os.R_OK):
        raise ValueError(f"Missing 64-bit hook: {hook}")
    entries = [entry for entry in os.environ.get("LD_PRELOAD", "").split(":") if entry]
    entries.append(str(hook))
    companion = directory / "lib/libuma_hook.so"
    if companion.is_file() and os.access(companion, os.R_OK):
        entries.append(str(companion))
    preload = ":".join(entries)
    for key, default in (("UMA_SPEED", "1.0"), ("UMA_HOOK_QUIET", "0"),
                         ("UMA_HOOK_FILTER", "UmamusumePrettyDerby.exe")):
        if not os.environ.get(key):
            os.environ[key] = default
    os.environ["UMA_HOOK_CTRL"] = runtime.runtime_path("ctrl")
    os.environ["UMA_HOOK_LOG"] = runtime.runtime_path("log")
    runtime.main(["initialize", preload, *command])
    os.environ["LD_PRELOAD"] = preload
    os.execvpe(command[0], command, os.environ)


if __name__ == "__main__":
    try:
        launch(sys.argv[1:])
    except (OSError, ValueError) as error:
        sys.exit(f"uma_hook: {error}")
