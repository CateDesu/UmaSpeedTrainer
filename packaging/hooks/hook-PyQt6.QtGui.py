"""Keep the portable GUI on X11 without optional desktop integrations."""

from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [
    (source, target) for source, target in binaries
    if "platformthemes" not in target
    and (not target.endswith("/platforms")
         or Path(source).name in {"libqxcb.so", "libqoffscreen.so", "libqminimal.so"})
]
