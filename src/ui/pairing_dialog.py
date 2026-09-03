"""
Pairing dialogs for Sendspin: a styled popup that shows the pairing PIN,
and a re-pair confirmation dialog when a PSK mismatch is detected.

Runs on its own hidden tk root in a background thread (same pattern as the
mini player) so it never blocks the asyncio event loop.
"""
import logging
import queue
import threading
import tkinter as tk
from typing import Callable, Optional

from src.i18n import t

logger = logging.getLogger(__name__)

_WIDTH = 420
_HEIGHT = 250
_ALPHA = 0.96

_MARGIN = 16        # distance from screen edges (matches mini player)
_TASKBAR = 48       # approximate taskbar height

# Palette (matches the mini player)
_BG = "#1A1F2E"
_BG_CARD = "#2A3350"
_FG = "#F7F8FA"
_FG_DIM = "#A6ADBD"
_ACCENT = "#8B93FF"
_ACCENT_DIM = "#5B62C9"
_WARN = "#F87171"
_BTN_FILL = "#2E3442"
_BTN_FILL_HOVER = "#3C4456"


class _PairingDialogManager:
    """Single hidden tk root in a background thread; renders pairing dialogs."""

    def __init__(self):
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._queue: "queue.Queue[tuple]" = queue.Queue()
        self._win: Optional[tk.Toplevel] = None
        self._pin = ""
        self._prompt_label = None
        self._pin_label = None
        self._after_hide = None  # job id for auto-hide
        self._on_yes: Optional[Callable] = None

    # ---------- lifecycle ----------

    def _run(self) -> None:
        root = tk.Tk()
        root.withdraw()
        self._root = root
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

    # ---------- event pump ----------

    def _poll(self) -> None:
        try:
            while True:
                kind, *args = self._queue.get_nowait()
                handler = getattr(self, f"_apply_{kind}", None)
                if handler:
                    handler(*args)
        except queue.Empty:
            pass
        self._root.after(100, self._poll)

    # ---------- PIN popup ----------

    def _apply_show_pin(self, pin: str) -> None:
        self._destroy_win()
        win = self._build_win("Sendspin 配对")
        self._win = win
        self._pin = str(pin)

        tk.Label(win, text=f"\U0001F50A  {t('sendspin_pairing_title')}",
                 font=("Microsoft YaHei UI", 14, "bold"),
                 fg=_FG, bg=_BG, anchor="center").place(x=0, y=22, width=_WIDTH)

        # Large, eye-catching PIN on a tinted card; click to copy to clipboard
        card = tk.Frame(win, bg=_BG_CARD, highlightthickness=0)
        card.place(x=60, y=72, width=_WIDTH - 120, height=110)
        pin_label = tk.Label(card, text=pin, font=("Segoe UI", 54, "bold"),
                             fg=_ACCENT, bg=_BG_CARD, anchor="center",
                             cursor="hand2")
        pin_label.pack(fill="both", expand=True)
        pin_label.bind("<Button-1>", lambda e: self._copy_pin())
        self._pin_label = pin_label

        self._prompt_label = tk.Label(
            win, text=t('sendspin_pairing_pin_prompt'), font=("Microsoft YaHei UI", 10),
            fg=_FG_DIM, bg=_BG, anchor="center")
        self._prompt_label.place(x=0, y=208, width=_WIDTH)

        self._center_and_show(win)

    def _copy_pin(self) -> None:
        """Copy the PIN to the clipboard and show confirmation."""
        if self._root is not None:
            try:
                self._root.clipboard_clear()
                self._root.clipboard_append(self._pin)
                self._root.update()
            except tk.TclError:
                pass
        if self._prompt_label is not None:
            try:
                self._prompt_label.configure(text=t('sendspin_pairing_pin_copied'))
            except tk.TclError:
                pass

    def _apply_hide_pin(self) -> None:
        self._destroy_win()

    # ---------- mismatch dialog ----------

    def _apply_show_mismatch(self) -> None:
        self._destroy_win()
        win = self._build_win(t('sendspin_pairing_mismatch_title'))
        self._win = win

        tk.Label(win, text=f"\u26A0  {t('sendspin_pairing_mismatch_title')}",
                 font=("Microsoft YaHei UI", 14, "bold"),
                 fg=_WARN, bg=_BG, anchor="center").place(x=0, y=32, width=_WIDTH)

        tk.Label(win, text=t('sendspin_pairing_mismatch_msg'), font=("Microsoft YaHei UI", 11),
                 fg=_FG, bg=_BG, anchor="center", justify="center").place(
                 x=30, y=90, width=_WIDTH - 60)

        self._make_button(win, t('sendspin_pairing_repair'), _ACCENT, _ACCENT_DIM, _FG,
                          90, 178, self._on_yes_clicked)
        self._make_button(win, t('sendspin_pairing_cancel'), _BTN_FILL, _BTN_FILL_HOVER, _FG,
                          240, 178, self._on_no_clicked)

        self._center_and_show(win)

    def _on_yes_clicked(self) -> None:
        self._destroy_win()
        cb = self._on_yes
        self._on_yes = None
        if cb:
            try:
                cb()
            except Exception as e:
                logger.debug(f"Re-pair callback error: {e}")

    def _on_no_clicked(self) -> None:
        self._destroy_win()
        self._on_yes = None

    # ---------- helpers ----------

    def _build_win(self, title: str) -> tk.Toplevel:
        win = tk.Toplevel(self._root)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", _ALPHA)
        win.configure(bg=_BG)
        win.title(title)
        win.geometry(f"{_WIDTH}x{_HEIGHT}")
        win.withdraw()
        return win

    def _center_and_show(self, win: tk.Toplevel) -> None:
        win.update_idletasks()
        sw = win.winfo_screenwidth()
        sh = win.winfo_screenheight()
        # Same bottom-right placement as the mini player
        x = sw - _WIDTH - _MARGIN
        y = sh - _HEIGHT - _MARGIN - _TASKBAR
        win.geometry(f"+{x}+{y}")
        win.deiconify()
        win.lift()
        win.focus_force()

    def _make_button(self, win, text, fill, hover, fg, x, y, command) -> None:
        btn = tk.Label(win, text=text, font=("Microsoft YaHei UI", 10, "bold"),
                       fg=fg, bg=fill, anchor="center", cursor="hand2")
        btn.place(x=x, y=y, width=90, height=32)
        btn.bind("<Button-1>", lambda e: command())
        btn.bind("<Enter>", lambda e: btn.configure(bg=hover))
        btn.bind("<Leave>", lambda e: btn.configure(bg=fill))

    def _destroy_win(self) -> None:
        if self._win is not None:
            try:
                self._win.withdraw()
                self._win.destroy()
            except tk.TclError:
                pass
            self._win = None

    # ---------- public API (any thread) ----------

    def show_pin(self, pin: str) -> bool:
        if not self.ensure():
            return False
        self._queue.put(("show_pin", str(pin)))
        return True

    def hide_pin(self) -> None:
        if self._root is None:
            return
        self._queue.put(("hide_pin",))

    def show_mismatch(self, on_yes: Callable) -> bool:
        if not self.ensure():
            return False
        self._on_yes = on_yes
        self._queue.put(("show_mismatch",))
        return True


_mgr = _PairingDialogManager()


def show_pin(pin: str) -> bool:
    """Show the pairing PIN popup (replaces any existing dialog)."""
    return _mgr.show_pin(pin)


def hide_pin() -> None:
    """Hide the pairing PIN popup (pairing complete / cleared)."""
    _mgr.hide_pin()


def show_mismatch(on_yes: Callable) -> bool:
    """Show the PSK-mismatch re-pair dialog. on_yes() is called if the user
    confirms."""
    return _mgr.show_mismatch(on_yes)
