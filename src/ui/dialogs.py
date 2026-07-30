"""
Native Dialogs using tkinter (built-in, zero extra size)
"""

import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

logger = logging.getLogger(__name__)

REPO_URL = "https://github.com/ha-china/ha-windows"


class _DialogManager:
    """Manages a hidden tkinter root + dialog lifecycle in a background thread."""

    def __init__(self):
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()

    def _run(self):
        root = tk.Tk()
        root.withdraw()
        self._root = root
        self._ready.set()
        root.mainloop()

    def ensure(self):
        if self._root is not None:
            return True
        if self._thread and self._thread.is_alive():
            return self._ready.wait(timeout=3)
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self._ready.wait(timeout=3)

    def show_status(self, name: str, ip: str, port: str, version: str):
        if not self.ensure():
            return
        self._root.after(0, lambda: _show_status(self._root, name, ip, port, version))

    def show_about(self, version: str):
        if not self.ensure():
            return
        self._root.after(0, lambda: _show_about(self._root, version))


_dialog_mgr = _DialogManager()


def _show_status(parent, name: str, ip: str, port: str, version: str):
    try:
        win = tk.Toplevel(parent)
        win.title("Device Status")
        win.geometry("380x250")
        win.resizable(False, False)
        win.lift()
        win.focus_force()

        win.update_idletasks()
        x = (win.winfo_screenwidth() - 380) // 2
        y = (win.winfo_screenheight() - 250) // 2
        win.geometry(f"+{x}+{y}")

        frame = ttk.Frame(win, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        rows = [
            ("Device", name),
            ("IP", ip),
            ("Port", port),
            ("Version", version),
            ("Status", "Running"),
        ]
        for label, value in rows:
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=4)
            ttk.Label(row, text=f"{label}:", font=("", 10)).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("", 10, "bold")).pack(side=tk.RIGHT)

        ttk.Button(frame, text="Close", command=win.destroy).pack(pady=(20, 0))
    except Exception as e:
        logger.error(f"Failed to show status dialog: {e}")


def _show_about(parent, version: str):
    try:
        import webbrowser

        win = tk.Toplevel(parent)
        win.title("About")
        win.geometry("380x240")
        win.resizable(False, False)
        win.lift()
        win.focus_force()

        win.update_idletasks()
        x = (win.winfo_screenwidth() - 380) // 2
        y = (win.winfo_screenheight() - 240) // 2
        win.geometry(f"+{x}+{y}")

        frame = ttk.Frame(win, padding="20")
        frame.pack(fill=tk.BOTH, expand=True)

        ttk.Label(frame, text="Home Assistant Windows", font=("", 14, "bold")).pack(pady=(0, 10))
        ttk.Label(frame, text=f"Version {version}", font=("", 10)).pack()
        ttk.Label(
            frame, text="Windows native client for Home Assistant voice assistant.",
            wraplength=320, justify=tk.CENTER,
        ).pack(pady=(10, 5))

        link = ttk.Label(frame, text=REPO_URL, foreground="blue", cursor="hand2")
        link.pack()
        link.bind("<Button-1>", lambda e: webbrowser.open(REPO_URL))

        ttk.Label(frame, text="© 2024 ha-china", foreground="gray").pack(pady=(10, 0))
        ttk.Button(frame, text="Close", command=win.destroy).pack(pady=(10, 0))
    except Exception as e:
        logger.error(f"Failed to show about dialog: {e}")


def show_status_dialog(name: str, ip: str, port: str, version: str) -> None:
    _dialog_mgr.show_status(name, ip, port, version)


def show_about_dialog(version: str) -> None:
    _dialog_mgr.show_about(version)