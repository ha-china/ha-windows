"""
Conversation bubble: borderless colored popup near the tray showing
STT (user speech) and TTS (assistant reply) with different background colors.
"""

import logging
import queue
import threading
import tkinter as tk
from typing import Optional

from src.i18n import get_i18n

logger = logging.getLogger(__name__)

# Bubble background colors per message type
_BG_COLORS = {
    "stt": "#6B7280",    # gray - what the user said
    "tts": "#6B7280",    # gray - what the assistant replied
    "info": "#374151",   # dark gray - hints (e.g. no speech recognized)
}

_DISPLAY_MS = 5000       # how long the bubble stays on screen
_MARGIN = 16             # distance from screen edges
_TASKBAR = 48            # approximate taskbar height
_WRAPLENGTH = 340
_ALPHA = 0.7             # background transparency


class _BubbleManager:
    """Single hidden tk root in a background thread; renders one bubble at a time."""

    def __init__(self):
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._queue: "queue.Queue[tuple[str, str]]" = queue.Queue()
        self._remaining_ms = 0
        self._label: Optional[tk.Label] = None
        self._win: Optional[tk.Toplevel] = None

    # ---------- lifecycle ----------

    def _run(self) -> None:
        root = tk.Tk()
        root.withdraw()
        self._root = root

        win = tk.Toplevel(root)
        win.overrideredirect(True)   # borderless
        win.attributes("-topmost", True)
        win.attributes("-alpha", _ALPHA)
        win.withdraw()
        self._win = win

        label = tk.Label(
            win,
            text="",
            wraplength=_WRAPLENGTH,
            justify="left",
            font=("Microsoft YaHei UI", 12),
            fg="#FFFFFF",
            padx=18,
            pady=12,
        )
        label.pack(fill="both", expand=True)
        self._label = label

        self._ready.set()
        self._poll()
        root.mainloop()

    def ensure(self) -> bool:
        if self._root is not None:
            return True
        if self._thread and self._thread.is_alive():
            return self._ready.wait(timeout=3)
        self._ready.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        return self._ready.wait(timeout=3)

    # ---------- rendering ----------

    def _poll(self) -> None:
        """Drain pending messages, then manage the hide countdown."""
        try:
            while True:
                msg_type, text = self._queue.get_nowait()
                self._show(msg_type, text)
        except queue.Empty:
            pass

        if self._remaining_ms > 0:
            self._remaining_ms -= 100
            if self._remaining_ms <= 0 and self._win is not None:
                self._win.withdraw()
        self._root.after(100, self._poll)

    def _show(self, msg_type: str, text: str) -> None:
        color = _BG_COLORS.get(msg_type, _BG_COLORS["info"])
        try:
            self._label.configure(text=text, bg=color)
            self._win.configure(bg=color)
            self._win.update_idletasks()

            w = self._win.winfo_reqwidth()
            h = self._win.winfo_reqheight()
            sw = self._win.winfo_screenwidth()
            sh = self._win.winfo_screenheight()
            x = sw - w - _MARGIN
            y = sh - h - _MARGIN - _TASKBAR
            self._win.geometry(f"+{x}+{y}")
            self._win.deiconify()
            self._win.attributes("-topmost", True)  # re-assert above other topmost windows
            self._win.lift()
            self._remaining_ms = _DISPLAY_MS
        except tk.TclError as e:
            logger.debug(f"Bubble render failed: {e}")

    def push(self, msg_type: str, text: str) -> None:
        if not self.ensure():
            return
        self._queue.put((msg_type, text))


_mgr = _BubbleManager()
_enabled = True


def set_enabled(enabled: bool) -> None:
    """Enable/disable bubble display (tray toggle)."""
    global _enabled
    _enabled = bool(enabled)


def show_conversation_bubble(msg_type: str, text: str) -> None:
    """Show a colored bubble near the tray. msg_type: stt / tts / info."""
    if not _enabled:
        return
    try:
        label = {
            "stt": get_i18n().t('conversation_you_said'),
            "tts": get_i18n().t('conversation_assistant'),
        }.get(msg_type)
        display = f"{label}: {text}" if label else text
        _mgr.push(msg_type, display)
    except Exception as e:
        logger.debug(f"Conversation bubble failed: {e}")
