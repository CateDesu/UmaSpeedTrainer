#!/usr/bin/env python3
"""uma_hook GUI. Runtime ON/OFF for the Uma Musume speedhack.

Writes the chosen speed (default 3.0) to the same ctrl file that
libuma_hook.so polls. The hook picks up the change within ~100 ms.

Run:
    python3 gui.py
"""

from pathlib import Path
import sys
import runtime
import updater
from PyQt6.QtCore import Qt, QThread, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QDoubleSpinBox, QMessageBox,
    QVBoxLayout, QHBoxLayout,
)

def read_speed():
    try:
        return runtime.read_speed()
    except (OSError, ValueError, UnicodeError):
        return None


def write_speed(value):
    try:
        runtime.write_speed(value)
        return None
    except (OSError, ValueError) as e:
        return str(e)


class UpdateTask(QThread):
    def __init__(self, parent, operation, *args):
        super().__init__(parent)
        self.operation = operation
        self.args = args
        self.result = None
        self.error = None

    def run(self):
        try:
            self.result = self.operation(*self.args)
        except Exception as error:
            self.error = str(error)


class UmaWindow(QWidget):
    def __init__(self, program=None):
        super().__init__()
        self.setWindowTitle("Uma Speed Trainer")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
        self._error = None

        root = QVBoxLayout(self)
        root.setSpacing(10)

        self.status = QLabel("...")
        self.status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        sf = self.status.font()
        sf.setPointSize(sf.pointSize() + 6)
        sf.setBold(True)
        self.status.setFont(sf)
        root.addWidget(self.status)

        row = QHBoxLayout()
        row.addWidget(QLabel("Speed:"))
        self.spin = QDoubleSpinBox()
        self.spin.setRange(1.0, 5.0)
        self.spin.setSingleStep(0.25)
        self.spin.setDecimals(2)
        self.spin.setValue(3.0)
        row.addWidget(self.spin, stretch=1)
        root.addLayout(row)

        btns = QHBoxLayout()
        self.on_btn = QPushButton("Set")
        self.off_btn = QPushButton("OFF")
        for b, css in (
            (self.on_btn,  "background: #2e7d32; color: white;"),
            (self.off_btn, "background: #555; color: white;"),
        ):
            b.setMinimumHeight(56)
            bf = b.font(); bf.setPointSize(bf.pointSize() + 4); bf.setBold(True)
            b.setFont(bf)
            b.setStyleSheet(f"QPushButton {{ {css} border-radius: 6px; }}")
        self.on_btn.clicked.connect(self._on)
        self.off_btn.clicked.connect(self._off)
        btns.addWidget(self.on_btn)
        btns.addWidget(self.off_btn)
        root.addLayout(btns)

        self._source = program is None
        self._update_target = Path(__file__).resolve().parent if self._source else program
        self._update_task = None
        if program is not None or (self._update_target / ".git").exists():
            self.update_btn = QPushButton("Update")
            self.update_btn.clicked.connect(self._check_update)
            root.addWidget(self.update_btn)
            self.update_status = QLabel()
            self.update_status.setTextFormat(Qt.TextFormat.PlainText)
            self.update_status.setWordWrap(True)
            self.update_status.hide()
            root.addWidget(self.update_status)

        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(300)
        self._refresh()

        self.resize(280, 180)

    def _refresh(self):
        if self._error:
            self.status.setText(self._error)
            self.status.setStyleSheet("color: #e57373;")
            return
        v = read_speed()
        if v is None:
            self.status.setText("· no hook ·")
            self.status.setStyleSheet("color: #888;")
        elif abs(v - 1.0) < 0.001:
            self.status.setText("OFF  (1.0×)")
            self.status.setStyleSheet("color: #aaa;")
        else:
            self.status.setText(f"ON   ({v:g}×)")
            self.status.setStyleSheet("color: #4caf50;")

    def _on(self):
        self._error = write_speed(self.spin.value())
        self._refresh()

    def _off(self):
        self._error = write_speed(1.0)
        self._refresh()

    def _start_update_task(self, message, finished, operation, *args):
        self.update_btn.setEnabled(False)
        self.update_status.setText(message)
        self.update_status.show()
        self._update_task = UpdateTask(self, operation, self._update_target, *args)
        self._update_task.finished.connect(finished)
        self._update_task.start()

    def _take_update_task(self):
        task = self._update_task
        self._update_task = None
        task.deleteLater()
        if task.error is not None:
            self.update_status.setText(f"Update failed. {task.error}")
            self.update_btn.setEnabled(True)
        return task

    def _check_update(self):
        if self._source:
            self._start_update_task("Checking upstream…", self._update_checked, updater.check_source_update)
        else:
            self._start_update_task("Checking GitHub…", self._update_checked, updater.check_for_update)

    def _update_checked(self):
        task = self._take_update_task()
        if task.error is not None:
            return
        release = task.result
        if release is None:
            self.update_status.setText("Your checkout includes the latest upstream changes."
                                       if self._source else "You already have the latest release.")
            self.update_btn.setEnabled(True)
            return
        if self._source:
            if release.head == release.commit:
                prompt = f"Finish the interrupted update by rebuilding the hooks for {release.commit[:12]}?"
            else:
                prompt = f"Update this checkout to {release.commit[:12]} and rebuild the trainer?"
        else:
            prompt = (f"Replace this executable with the official release {release.tag}?\n\n"
                      "This release may be older than your current build.")
        answer = QMessageBox.question(
            self, "Update Uma Speed Trainer",
            f"{prompt}\n\n"
            "You can keep playing. The game will use the new hook the next time you launch it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer == QMessageBox.StandardButton.Yes:
            if self._source:
                self._start_update_task("Building the update…", self._update_installed,
                                        updater.install_source_update, release)
            else:
                self._start_update_task(f"Downloading {release.tag}…", self._update_installed,
                                        updater.install_update, release)
        else:
            self.update_status.hide()
            self.update_btn.setEnabled(True)

    def _update_installed(self):
        if self._take_update_task().error is None:
            self.update_status.setText("Update installed. Reopen the trainer to use it.")

    def closeEvent(self, event):
        if self._update_task is not None:
            event.ignore()
        else:
            super().closeEvent(event)


def main(program=None):
    app = QApplication(sys.argv)
    w = UmaWindow(program)
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
