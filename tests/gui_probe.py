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
    from PyQt6.QtWidgets import QApplication, QMessageBox
    import gui
    from unittest.mock import patch
    from PyQt6.QtTest import QTest

    app = QApplication([])
    clone = Path(temp) / "clone"
    (clone / ".git").mkdir(parents=True)
    with patch.object(gui, "__file__", str(clone / "gui.py")):
        window = gui.UmaWindow()
    window.show()
    app.processEvents()
    assert window.update_btn.isVisible()
    with patch.object(gui.updater, "check_source_update", return_value=None) as check:
        window.update_btn.click()
        for _ in range(200):
            QTest.qWait(10)
            if window.update_btn.isEnabled():
                break
        check.assert_called_once_with(clone)
        assert "latest upstream" in window.update_status.text()
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

    program = Path(temp) / "local artifact"
    window = gui.UmaWindow(program)
    release = gui.updater.Release("v1.0.0", 42, "digest")
    with (patch.object(gui.updater, "check_for_update", return_value=release),
          patch.object(gui.updater, "install_update") as install,
          patch.object(QMessageBox, "question", return_value=QMessageBox.StandardButton.No) as question):
        window.update_btn.click()
        for _ in range(200):
            QTest.qWait(10)
            if window.update_btn.isEnabled():
                break
        assert "may be older than your current build" in question.call_args.args[2]
        assert question.call_args.args[-1] == QMessageBox.StandardButton.No
        install.assert_not_called()
    window.close()
    app.processEvents()
    print("GUI controls and write errors passed")
