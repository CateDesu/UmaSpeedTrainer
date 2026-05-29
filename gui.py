#!/usr/bin/env python3
"""uma_hook GUI — runtime ON/OFF for the Uma Musume speedhack.

Writes the chosen speed (default 3.0) to the same ctrl file that
libuma_hook.so polls. The hook picks up the change within ~100 ms.

Run:
    python3 /home/cate/uma_hook/gui.py
"""

import os
import sys
from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtWidgets import (
    QApplication, QWidget, QPushButton, QLabel, QDoubleSpinBox,
    QVBoxLayout, QHBoxLayout,
)

CTRL = os.environ.get("UMA_HOOK_CTRL", "/tmp/uma-hook.ctrl")


def read_speed():
    try:
        with open(CTRL) as f:
            return float(f.read().strip())
    except (OSError, ValueError):
        return None


def write_speed(value):
    try:
        with open(CTRL, "w") as f:
            f.write(f"{value}")
        return None
    except OSError as e:
        return str(e)


class UmaWindow(QWidget):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("uma_hook")
        self.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)

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
        self.spin.setRange(1.0, 20.0)
        self.spin.setSingleStep(0.5)
        self.spin.setDecimals(2)
        self.spin.setValue(3.0)
        row.addWidget(self.spin, stretch=1)
        root.addLayout(row)

        btns = QHBoxLayout()
        self.on_btn = QPushButton("ON")
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

        timer = QTimer(self)
        timer.timeout.connect(self._refresh)
        timer.start(300)
        self._refresh()

        self.resize(280, 180)

    def _refresh(self):
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
        err = write_speed(self.spin.value())
        if err: self.status.setText(err)
        self._refresh()

    def _off(self):
        err = write_speed(1.0)
        if err: self.status.setText(err)
        self._refresh()


def main():
    app = QApplication(sys.argv)
    w = UmaWindow()
    w.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
