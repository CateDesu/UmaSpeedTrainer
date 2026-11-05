"""Entry point for the portable Linux executable."""

import os
from pathlib import Path
import shlex
import sys


def main():
    args = sys.argv[1:]
    if args == ["--steam-options"]:
        print(f"{shlex.quote(os.path.realpath(sys.executable))} --steam-launch %command%")
        return
    if args and args[0] == "--steam-launch":
        if len(args) == 1:
            sys.exit("--steam-launch requires Steam's %command%")
        bundle = Path(__file__).resolve().parent
        env = sys._uma_launch_environment.copy()
        # Keep bundled libraries and Qt plugins out of Proton.
        original = env.pop("LD_LIBRARY_PATH_ORIG", None)
        env.pop("LD_LIBRARY_PATH", None)
        if original is not None:
            env["LD_LIBRARY_PATH"] = original
        for key in list(env):
            if key.startswith("_PYI_"):
                env.pop(key)
        os.environ.clear()
        os.environ.update(env)
        from launcher import launch
        # The bootloader keeps its extracted files until the game exits.
        try:
            launch(args[1:], bundle)
        except (OSError, ValueError) as error:
            sys.exit(f"uma_hook: {error}")
    if args in (["--help"], ["-h"]):
        print("Run without arguments for the GUI.\n"
              "--steam-options       Print the Steam Launch Options line\n"
              "--steam-launch CMD    Run Steam's game command with the hook")
        return
    if args:
        sys.exit("Unknown arguments. Use --help for usage.")
    os.environ.setdefault("QT_QPA_PLATFORM", "xcb")
    from gui import main as gui_main
    gui_main()


if __name__ == "__main__":
    main()
