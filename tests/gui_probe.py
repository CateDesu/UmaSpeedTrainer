"""Exercise the controls on an isolated display and control file."""

import os
from pathlib import Path
import sys
import tempfile

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

with tempfile.TemporaryDirectory(prefix="uma-gui-test-") as temp:
    os.environ["HOME"] = temp
    os.environ["XDG_CONFIG_HOME"] = temp
    os.environ["XDG_CACHE_HOME"] = temp
    os.environ["UMA_HOOK_CTRL"] = str(Path(temp) / "ctrl")
    from PyQt6.QtWidgets import QApplication
    from gui import UmaWindow

    app = QApplication([])
    window = UmaWindow()
    window.show()
    app.processEvents()
    assert "no hook" in window.status.text()
    window.spin.setValue(4.25)
    window.on_btn.click()
    assert Path(os.environ["UMA_HOOK_CTRL"]).read_text() == "4.25"
    assert "4.25" in window.status.text()
    window.off_btn.click()
    assert float(Path(os.environ["UMA_HOOK_CTRL"]).read_text()) == 1.0
    for invalid in ("nan", "inf", "-1", "0", "1001", "3" + " " * 64,
                    "1_0", "３", "\u00a03\u00a0", "3\x00junk"):
        Path(os.environ["UMA_HOOK_CTRL"]).write_text(invalid)
        window._refresh()
        assert "no hook" in window.status.text(), invalid
    Path(os.environ["UMA_HOOK_CTRL"]).write_bytes(b"\xff")
    window._refresh()
    assert "no hook" in window.status.text()
    os.unlink(os.environ["UMA_HOOK_CTRL"])
    victim = Path(temp) / "keep.txt"
    victim.write_text("do not change")
    Path(os.environ["UMA_HOOK_CTRL"]).symlink_to(victim)
    window.on_btn.click()
    assert victim.read_text() == "do not change"
    assert Path(os.environ["UMA_HOOK_CTRL"]).is_symlink()
    assert window._error
    os.unlink(os.environ["UMA_HOOK_CTRL"])
    window._error = None
    os.mkfifo(os.environ["UMA_HOOK_CTRL"])
    window._refresh()
    assert "no hook" in window.status.text()
    os.unlink(os.environ["UMA_HOOK_CTRL"])
    os.mkdir(os.environ["UMA_HOOK_CTRL"])
    window.on_btn.click()
    assert "directory" in window.status.text().lower()
    window._refresh()
    assert "directory" in window.status.text().lower()
    os.rmdir(os.environ["UMA_HOOK_CTRL"])
    window.off_btn.click()
    assert float(Path(os.environ["UMA_HOOK_CTRL"]).read_text()) == 1.0
    assert "OFF" in window.status.text()
    window._refresh()
    assert "OFF" in window.status.text()
    window.close()
    app.processEvents()
    print("GUI controls and write errors passed")
