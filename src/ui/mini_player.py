"""
Mini player: borderless always-on-top popup showing the track currently
streamed from Music Assistant, with play/pause/prev/next/stop buttons and
a volume slider. Commands are forwarded upstream via Sendspin.
"""

import logging
import queue
import threading
import tkinter as tk
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_MARGIN = 16        # distance from screen edges
_TASKBAR = 48       # approximate taskbar height
_WIDTH = 380
_ALPHA = 0.92

_BG = "#1F2430"
_BG_HOVER = "#2A3140"
_FG = "#F3F4F6"
_FG_DIM = "#9CA3AF"
_ACCENT = "#818CF8"

# Commands sent to the handler: "previous" | "play_pause" | "next" | "stop"
CommandHandler = Callable[[str], None]
VolumeHandler = Callable[[int], None]


class _MiniPlayerManager:
    """Single hidden tk root in a background thread; renders the mini player."""

    def __init__(self):
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._queue: "queue.Queue[tuple]" = queue.Queue()

        self._win: Optional[tk.Toplevel] = None
        self._title_label: Optional[tk.Label] = None
        self._artist_label: Optional[tk.Label] = None
        self._play_button: Optional[tk.Button] = None

        self._visible = False
        self._playing = False
        self._title = ""
        self._artist = ""

        self._on_command: Optional[CommandHandler] = None
        self._on_volume: Optional[VolumeHandler] = None

        self._drag_x = 0
        self._drag_y = 0
        self._position: Optional[tuple] = None  # user-dragged position (x, y)

    # ---------- lifecycle ----------

    def _run(self) -> None:
        root = tk.Tk()
        root.withdraw()
        self._root = root

        win = tk.Toplevel(root)
        win.overrideredirect(True)   # borderless
        win.attributes("-topmost", True)
        win.attributes("-alpha", _ALPHA)
        win.configure(bg=_BG)
        win.withdraw()
        win.protocol("WM_DELETE_WINDOW", self.hide)
        self._win = win

        # --- drag handle / title row ---
        title_row = tk.Frame(win, bg=_BG, cursor="fleur")
        title_row.pack(fill="x", padx=14, pady=(10, 2))

        icon = tk.Label(title_row, text="♪", bg=_BG, fg=_ACCENT,
                        font=("Segoe UI Symbol", 12, "bold"))
        icon.pack(side="left")

        self._title_label = tk.Label(
            title_row, text="", bg=_BG, fg=_FG, anchor="w", justify="left",
            wraplength=_WIDTH - 110, font=("Microsoft YaHei UI", 12, "bold"),
        )
        self._title_label.pack(side="left", fill="x", expand=True, padx=(6, 8))

        close_btn = tk.Label(title_row, text="✕", bg=_BG, fg=_FG_DIM,
                             font=("Segoe UI", 11), padx=6, cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self.hide())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg="#F87171"))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg=_FG_DIM))

        for widget in (title_row, icon, self._title_label):
            widget.bind("<Button-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)

        # --- artist row ---
        self._artist_label = tk.Label(
            win, text="", bg=_BG, fg=_FG_DIM, anchor="w", justify="left",
            wraplength=_WIDTH - 28, font=("Microsoft YaHei UI", 10),
        )
        self._artist_label.pack(fill="x", padx=14, pady=(0, 8))

        # --- controls row ---
        controls = tk.Frame(win, bg=_BG)
        controls.pack(fill="x", padx=14, pady=(0, 4))

        def flat_button(text: str, cmd: str, width: int = 4) -> tk.Button:
            btn = tk.Button(
                controls, text=text, command=lambda: self._fire_command(cmd),
                bg=_BG, fg=_FG, activebackground=_BG_HOVER, activeforeground=_FG,
                relief="flat", bd=0, width=width, font=("Segoe UI Symbol", 11),
                cursor="hand2", highlightthickness=0,
            )
            return btn

        prev = flat_button("⏮", "previous")
        self._play_button = flat_button("▶", "play_pause", width=5)
        nxt = flat_button("⏭", "next")
        stop = flat_button("⏹", "stop")

        prev.pack(side="left", padx=(0, 4))
        self._play_button.pack(side="left", padx=4)
        nxt.pack(side="left", padx=4)
        stop.pack(side="left", padx=4)

        # --- volume row ---
        vol_row = tk.Frame(win, bg=_BG)
        vol_row.pack(fill="x", padx=14, pady=(2, 12))

        vol_icon = tk.Label(vol_row, text="🔊", bg=_BG, fg=_FG_DIM,
                            font=("Segoe UI Symbol", 10))
        vol_icon.pack(side="left", padx=(0, 6))

        slider = tk.Scale(
            vol_row, from_=0, to=100, orient="horizontal", showvalue=False,
            bg=_BG, fg=_FG, troughcolor="#374151", highlightthickness=0,
            activebackground=_ACCENT, length=_WIDTH - 90, sliderrelief="flat",
            command=lambda v: self._fire_volume(int(v)),
        )
        slider.pack(side="left", fill="x", expand=True)
        self._slider = slider

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

    # ---------- dragging ----------

    def _on_drag_start(self, event) -> None:
        self._drag_x, self._drag_y = event.x, event.y

    def _on_drag_motion(self, event) -> None:
        try:
            x = self._win.winfo_x() + event.x - self._drag_x
            y = self._win.winfo_y() + event.y - self._drag_y
            self._position = (x, y)
            self._win.geometry(f"+{x}+{y}")
        except tk.TclError:
            pass

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
        self._root.after(80, self._poll)

    # ---------- state application (tk thread) ----------

    def _apply_show(self) -> None:
        if self._win is None:
            return
        self._apply_track(self._title, self._artist)
        self._apply_playing(self._playing)
        try:
            self._win.update_idletasks()
            if self._position is not None:
                x, y = self._position
            else:
                h = 150  # approx window height
                sw = self._win.winfo_screenwidth()
                sh = self._win.winfo_screenheight()
                x = sw - _WIDTH - _MARGIN
                y = sh - h - _MARGIN - _TASKBAR
                self._position = (x, y)
            self._win.geometry(f"+{x}+{y}")
            self._win.deiconify()
            self._win.attributes("-topmost", True)
            self._win.lift()
            self._visible = True
        except tk.TclError as e:
            logger.debug(f"Mini player show failed: {e}")

    def _apply_hide(self) -> None:
        self._visible = False
        try:
            if self._win is not None:
                self._win.withdraw()
        except tk.TclError:
            pass

    def _apply_track(self, title: str, artist: str) -> None:
        self._title = title or "—"
        self._artist = artist or ""
        try:
            if self._title_label is not None:
                self._title_label.configure(text=self._title)
            if self._artist_label is not None:
                self._artist_label.configure(text=self._artist)
        except tk.TclError:
            pass

    def _apply_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        try:
            if self._play_button is not None:
                self._play_button.configure(text="⏸" if self._playing else "▶")
        except tk.TclError:
            pass

    def _apply_volume(self, volume: int) -> None:
        try:
            self._slider.set(int(volume))
        except (tk.TclError, AttributeError):
            pass

    # ---------- command firing (tk thread) ----------

    def _fire_command(self, cmd: str) -> None:
        if self._on_command:
            try:
                self._on_command(cmd)
            except Exception as e:
                logger.debug(f"Mini player command error: {e}")

    def _fire_volume(self, volume: int) -> None:
        if self._on_volume:
            try:
                self._on_volume(volume)
            except Exception as e:
                logger.debug(f"Mini player volume error: {e}")

    # ---------- public API (any thread) ----------

    def set_command_handler(self, handler: CommandHandler) -> None:
        self._on_command = handler

    def set_volume_handler(self, handler: VolumeHandler) -> None:
        self._on_volume = handler

    def show(self) -> bool:
        if not self.ensure():
            return False
        self._queue.put(("show",))
        return True

    def hide(self) -> None:
        if self._root is None:
            return
        self._queue.put(("hide",))

    def is_visible(self) -> bool:
        return self._visible

    def update_track(self, title: str, artist: str) -> None:
        # cache first so values survive a window that is not yet created
        self._title = title or "—"
        self._artist = artist or ""
        if self._root is not None:
            self._queue.put(("track", self._title, self._artist))

    def set_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        if self._root is not None:
            self._queue.put(("playing", self._playing))

    def set_volume(self, volume: int) -> None:
        if self._root is not None:
            self._queue.put(("volume", int(volume)))


_mgr = _MiniPlayerManager()
_enabled = True


def set_enabled(enabled: bool) -> None:
    """Enable/disable the mini player (tray toggle)."""
    global _enabled
    _enabled = bool(enabled)
    if not _enabled:
        _mgr.hide()


def is_enabled() -> bool:
    return _enabled


def show() -> None:
    if _enabled:
        _mgr.show()


def hide() -> None:
    _mgr.hide()


def update_track(title: str, artist: str) -> None:
    if _enabled:
        _mgr.update_track(title, artist)


def set_playing(playing: bool) -> None:
    if _enabled:
        _mgr.set_playing(playing)


def set_volume(volume: int) -> None:
    _mgr.set_volume(volume)


def set_command_handler(handler: CommandHandler) -> None:
    _mgr.set_command_handler(handler)


def set_volume_handler(handler: VolumeHandler) -> None:
    _mgr.set_volume_handler(handler)
