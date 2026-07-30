"""
PySide6 Native Dialogs for Status and About
"""

import logging
import threading
from typing import Optional

from PySide6.QtCore import Qt, QObject, Signal
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QApplication, QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QWidget, QFrame,
)

logger = logging.getLogger(__name__)

APP_NAME = "Home Assistant Windows"
REPO_URL = "https://github.com/ha-china/ha-windows"


class _DialogProxy(QObject):
    """Receiver object that lives on the Qt thread for cross-thread dialog dispatch."""

    _show_requested = Signal(str, str, str, str, str)  # type, name, ip, port, version

    def __init__(self):
        super().__init__()
        self._show_requested.connect(self._on_show_requested, Qt.QueuedConnection)

    def request_show_status(self, name: str, ip: str, port: str, version: str):
        self._show_requested.emit("status", name, ip, port, version)

    def request_show_about(self, version: str):
        self._show_requested.emit("about", "", "", "", version)

    def _on_show_requested(self, dtype: str, name: str, ip: str, port: str, version: str):
        if dtype == "status":
            dialog = _StatusDialog(name, ip, port, version)
        else:
            dialog = _AboutDialog(version)
        dialog.setAttribute(Qt.WA_DeleteOnClose)
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()


class _DialogManager:
    """Manages a hidden QApplication + dialog lifecycle in a dedicated thread."""

    def __init__(self):
        self._app: Optional[QApplication] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._proxy: Optional[_DialogProxy] = None

    def _run(self):
        self._app = QApplication([])
        self._app.setStyle("Fusion")
        self._proxy = _DialogProxy()
        self._ready.set()
        self._app.exec()

    def _ensure_app(self):
        if self._app is not None:
            return True
        if self._thread and self._thread.is_alive():
            return self._ready.wait(timeout=3)
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self._ready.wait(timeout=3)

    def show_status(self, name: str, ip: str, port: str, version: str):
        if not self._ensure_app():
            logger.error("Failed to start Qt app")
            return
        if self._proxy:
            self._proxy.request_show_status(name, ip, port, version)

    def show_about(self, version: str):
        if not self._ensure_app():
            logger.error("Failed to start Qt app")
            return
        if self._proxy:
            self._proxy.request_show_about(version)


class _StatusDialog(QDialog):
    def __init__(self, name: str, ip: str, port: str, version: str):
        super().__init__()
        self.setWindowTitle("Device Status")
        self.setFixedSize(400, 260)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setSpacing(0)

        title = QLabel("Device Status")
        title.setFont(QFont("Segoe UI", 16, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(20)

        rows = [
            ("Device", name),
            ("IP", ip),
            ("Port", port),
            ("Version", version),
            ("Status", "Running"),
        ]
        for label, value in rows:
            row = QWidget()
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(0, 10, 0, 10)
            lbl = QLabel(label)
            lbl.setFont(QFont("Segoe UI", 10))
            lbl.setStyleSheet("color: #888;")
            val = QLabel(value)
            val.setFont(QFont("Segoe UI", 10, QFont.Bold))
            val.setStyleSheet("color: #4fc3f7;")
            val.setAlignment(Qt.AlignRight)
            row_layout.addWidget(lbl)
            row_layout.addStretch()
            row_layout.addWidget(val)
            layout.addWidget(row)
            if label != "Status":
                line = QFrame()
                line.setFrameShape(QFrame.HLine)
                line.setStyleSheet("color: #333;")
                layout.addWidget(line)

        layout.addStretch()
        btn = QPushButton("Close")
        btn.setFixedWidth(120)
        btn.clicked.connect(self.close)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog { background: #1e1e2e; }
            QLabel { color: #e0e0e0; }
            QPushButton {
                background: #3a3a5c; color: #e0e0e0; border: none;
                border-radius: 6px; padding: 8px 24px; font-size: 13px;
            }
            QPushButton:hover { background: #4a4a6c; }
        """)


class _AboutDialog(QDialog):
    def __init__(self, version: str):
        super().__init__()
        self.setWindowTitle("About")
        self.setFixedSize(400, 320)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowContextHelpButtonHint)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 24)
        layout.setAlignment(Qt.AlignCenter)

        title = QLabel(APP_NAME)
        title.setFont(QFont("Segoe UI", 18, QFont.Bold))
        title.setAlignment(Qt.AlignCenter)
        layout.addWidget(title)
        layout.addSpacing(6)

        ver = QLabel(f"v{version}")
        ver.setFont(QFont("Segoe UI", 12))
        ver.setStyleSheet("color: #4fc3f7;")
        ver.setAlignment(Qt.AlignCenter)
        layout.addWidget(ver)
        layout.addSpacing(16)

        desc = QLabel(
            "Windows native client that emulates an ESPHome device\n"
            "for seamless Home Assistant integration."
        )
        desc.setFont(QFont("Segoe UI", 10))
        desc.setStyleSheet("color: #888;")
        desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(desc)
        layout.addSpacing(20)

        repo_link = QLabel(f'<a href="{REPO_URL}" style="color: #4fc3f7;">{REPO_URL}</a>')
        repo_link.setFont(QFont("Segoe UI", 10))
        repo_link.setOpenExternalLinks(True)
        repo_link.setAlignment(Qt.AlignCenter)
        layout.addWidget(repo_link)
        layout.addSpacing(20)

        copyright = QLabel("© 2024 ha-china")
        copyright.setFont(QFont("Segoe UI", 9))
        copyright.setStyleSheet("color: #555;")
        copyright.setAlignment(Qt.AlignCenter)
        layout.addWidget(copyright)

        layout.addStretch()
        btn = QPushButton("Close")
        btn.setFixedWidth(120)
        btn.clicked.connect(self.close)
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_layout.addWidget(btn)
        layout.addLayout(btn_layout)

        self.setStyleSheet("""
            QDialog { background: #1e1e2e; }
            QLabel { color: #e0e0e0; }
            QPushButton {
                background: #3a3a5c; color: #e0e0e0; border: none;
                border-radius: 6px; padding: 8px 24px; font-size: 13px;
            }
            QPushButton:hover { background: #4a4a6c; }
        """)


_dialog_mgr = _DialogManager()


def show_status_dialog(name: str, ip: str, port: str, version: str) -> None:
    """Show device status dialog (non-blocking)"""
    _dialog_mgr.show_status(name, ip, port, version)


def show_about_dialog(version: str) -> None:
    """Show about dialog (non-blocking)"""
    _dialog_mgr.show_about(version)