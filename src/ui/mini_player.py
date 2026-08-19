"""
Mini player: borderless always-on-top popup showing the track currently
streamed from Music Assistant, with album artwork, track title/artist,
a synced lyric line, play/pause/prev/next/stop buttons and a volume
slider. Commands are forwarded upstream via Sendspin.
"""

import io
import logging
import queue
import re
import threading
import time
import tkinter as tk
import urllib.parse
import urllib.request
from typing import Callable, Optional

logger = logging.getLogger(__name__)

_MARGIN = 16        # distance from screen edges
_TASKBAR = 48       # approximate taskbar height
_WIDTH = 400
_HEIGHT = 176
_ALPHA = 0.95
_ART_SIZE = 84      # artwork thumbnail size in pixels

_BG = "#1F2430"
_BG_HOVER = "#2A3140"
_FG = "#F3F4F6"
_FG_DIM = "#9CA3AF"
_ACCENT = "#818CF8"

_LYRIC_POLL_MS = 200    # lyric/progress refresh interval
_LRC_LINE_RE = re.compile(r"\[(\d+):(\d+(?:\.\d+)?)\](.*)$")
_LYRIC_UA = "ha-windows-mini-player"
# Advance lyric timing: the audio stream is buffered (~1s of PCM) before it
# is heard, so lyrics aligned to server-side progress lag behind. Shift the
# timeline forward to compensate.
_LYRIC_ADVANCE_MS = 600


def _fmt_time(ms: int) -> str:
    seconds = max(0, int(ms)) // 1000
    return f"{seconds // 60}:{seconds % 60:02d}"


def _parse_lrc(synced: str) -> Optional[list]:
    """Parse LRC text into sorted [(ms, text)] lines, verbatim."""
    lines = []
    for raw in synced.splitlines():
        m = _LRC_LINE_RE.match(raw.strip())
        if not m:
            continue
        minutes, seconds, text = int(m.group(1)), float(m.group(2)), m.group(3).strip()
        if text:
            lines.append((int((minutes * 60 + seconds) * 1000), text))
    if not lines:
        return None
    lines.sort(key=lambda entry: entry[0])
    return lines

# Commands sent to the handler: "previous" | "play_pause" | "next" | "stop"
CommandHandler = Callable[[str], None]
VolumeHandler = Callable[[int], None]
CloseHandler = Callable[[], None]


def _fetch_synced_lyrics(title: str, artist: str, duration_ms: Optional[int] = None) -> Optional[list]:
    """Look up time-synced lyrics on LRCLIB. Returns [(ms, text)] or None.

    When duration_ms is known, prefer the candidate whose duration matches
    best (same language, any script); fall back to the first result.
    """
    try:
        params = urllib.parse.urlencode(
            {"track_name": title, "artist_name": artist}
        )
        req = urllib.request.Request(
            f"https://lrclib.net/api/search?{params}",
            headers={"User-Agent": _LYRIC_UA},
        )
        with urllib.request.urlopen(req, timeout=5) as resp:
            import json

            results = json.loads(resp.read().decode("utf-8"))

        candidates = []
        for item in results or []:
            synced = item.get("syncedLyrics")
            if not synced:
                continue
            parsed = _parse_lrc(synced)
            if parsed:
                candidates.append((item, parsed))
        if not candidates:
            return None
        if duration_ms and duration_ms > 0:
            def duration_delta(entry):
                item, _lines = entry
                d = item.get("duration") or 0
                return abs(float(d) * 1000 - duration_ms) if d else float("inf")
            candidates.sort(key=duration_delta)
        return candidates[0][1]
    except Exception as e:
        logger.debug(f"Lyrics lookup failed: {e}")
        return None


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
        self._lyric_label: Optional[tk.Label] = None
        self._play_button: Optional[tk.Button] = None
        self._art_label: Optional[tk.Label] = None
        self._art_photo = None          # keep reference so tk doesn't GC it
        self._slider = None

        self._visible = False
        self._playing = False
        self._muted = False
        self._title = ""
        self._artist = ""
        self._position: Optional[tuple] = None

        # lyric state (guarded by the tk thread only)
        self._lyrics: Optional[list] = []
        self._lyric_index = -1
        self._progress_ms = 0
        self._progress_ts = 0.0
        self._speed = 1.0
        self._duration_ms = 0
        self._lyric_fetch_id = 0

        self._on_command: Optional[CommandHandler] = None
        self._on_volume: Optional[VolumeHandler] = None
        self._on_close: Optional[CloseHandler] = None

        self._drag_x = 0
        self._drag_y = 0
        self._slider_suppress = False  # True while setting the slider programmatically
        self._last_user_volume: Optional[int] = None
        self._volume_debounce_job = None  # tk after id for volume debounce

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
        win.geometry(f"{_WIDTH}x{_HEIGHT}")
        win.withdraw()
        self._win = win

        body = tk.Frame(win, bg=_BG)
        body.pack(fill="both", expand=True)

        # --- left: album artwork ---
        art_frame = tk.Frame(body, bg=_BG, width=_ART_SIZE, height=_ART_SIZE)
        art_frame.pack(side="left", padx=(14, 12), pady=12)
        art_frame.pack_propagate(False)
        self._art_label = tk.Label(art_frame, text="♪", bg="#161B26", fg=_ACCENT,
                                   font=("Segoe UI Symbol", 26))
        self._art_label.pack(fill="both", expand=True)

        # --- right: text + controls ---
        right = tk.Frame(body, bg=_BG)
        right.pack(side="left", fill="both", expand=True, pady=(10, 0))

        title_row = tk.Frame(right, bg=_BG, cursor="fleur")
        title_row.pack(fill="x")

        self._title_label = tk.Label(
            title_row, text="", bg=_BG, fg=_FG, anchor="w", justify="left",
            font=("Microsoft YaHei UI", 12, "bold"),
        )
        self._title_label.pack(side="left", fill="x", expand=True, padx=(0, 8))

        close_btn = tk.Label(title_row, text="✕", bg=_BG, fg=_FG_DIM,
                             font=("Segoe UI", 11), padx=6, cursor="hand2")
        close_btn.pack(side="right")
        close_btn.bind("<Button-1>", lambda e: self._request_close())
        close_btn.bind("<Enter>", lambda e: close_btn.configure(fg="#F87171"))
        close_btn.bind("<Leave>", lambda e: close_btn.configure(fg=_FG_DIM))

        for widget in (title_row, self._title_label):
            widget.bind("<Button-1>", self._on_drag_start)
            widget.bind("<B1-Motion>", self._on_drag_motion)

        self._artist_label = tk.Label(
            right, text="", bg=_BG, fg=_FG_DIM, anchor="w", justify="left",
            font=("Microsoft YaHei UI", 10),
        )
        self._artist_label.pack(fill="x")

        self._lyric_label = tk.Label(
            right, text="", bg=_BG, fg=_ACCENT, anchor="w", justify="left",
            wraplength=_WIDTH - _ART_SIZE - 60,
            font=("Microsoft YaHei UI", 10),
        )
        self._lyric_label.pack(fill="x", pady=(4, 2))

        # --- progress bar + time labels ---
        prog_row = tk.Frame(right, bg=_BG)
        prog_row.pack(fill="x", pady=(2, 0))

        self._time_elapsed_label = tk.Label(
            prog_row, text="0:00", bg=_BG, fg=_FG_DIM,
            font=("Microsoft YaHei UI", 9),
        )
        self._time_elapsed_label.pack(side="left")

        bar_frame = tk.Frame(prog_row, bg="#374151", height=4)
        bar_frame.pack(side="left", fill="x", expand=True, padx=6, pady=6)
        bar_frame.pack_propagate(False)
        self._progress_bar = tk.Frame(bar_frame, bg=_ACCENT, width=0)
        self._progress_bar.pack(fill="y", anchor="w")

        self._time_total_label = tk.Label(
            prog_row, text="0:00", bg=_BG, fg=_FG_DIM,
            font=("Microsoft YaHei UI", 9),
        )
        self._time_total_label.pack(side="right")

        # --- controls row ---
        controls = tk.Frame(right, bg=_BG)
        controls.pack(fill="x", pady=(4, 0))

        def flat_button(text: str, cmd: str, width: int = 4) -> tk.Button:
            return tk.Button(
                controls, text=text, command=lambda: self._fire_command(cmd),
                bg=_BG, fg=_FG, activebackground=_BG_HOVER, activeforeground=_FG,
                relief="flat", bd=0, width=width, font=("Segoe UI Symbol", 11),
                cursor="hand2", highlightthickness=0,
            )

        prev = flat_button("⏮", "previous")
        self._play_button = flat_button("▶", "play_pause", width=5)
        nxt = flat_button("⏭", "next")
        stop = flat_button("⏹", "stop")

        prev.pack(side="left", padx=(0, 4))
        self._play_button.pack(side="left", padx=4)
        nxt.pack(side="left", padx=4)
        stop.pack(side="left", padx=4)

        # --- volume row ---
        vol_row = tk.Frame(right, bg=_BG)
        vol_row.pack(fill="x", pady=(2, 10))

        self._vol_icon = tk.Label(
            vol_row, text="🔊", bg=_BG, fg=_FG_DIM,
            font=("Segoe UI Symbol", 14), padx=2, cursor="hand2",
        )
        self._vol_icon.pack(side="left", padx=(0, 6))
        self._vol_icon.bind("<Button-1>", lambda e: self._fire_command("mute"))
        self._vol_icon.bind(
            "<Enter>", lambda e: self._vol_icon.configure(fg=_FG)
        )
        self._vol_icon.bind(
            "<Leave>", lambda e: self._vol_icon.configure(fg=_FG_DIM)
        )

        slider = tk.Scale(
            vol_row, from_=0, to=100, orient="horizontal", showvalue=False,
            bg=_BG, fg=_FG, troughcolor="#374151", highlightthickness=0,
            activebackground=_ACCENT, sliderrelief="flat",
            command=self._on_slider_command,
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
        self._update_lyric_line()
        self._update_progress_bar()
        self._root.after(_LYRIC_POLL_MS, self._poll)

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
                sw = self._win.winfo_screenwidth()
                sh = self._win.winfo_screenheight()
                x = sw - _WIDTH - _MARGIN
                y = sh - _HEIGHT - _MARGIN - _TASKBAR
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
        # new track: reset progress display (duration arrives separately)
        self._progress_ms = 0
        self._progress_ts = time.monotonic()
        self._speed = 0.0
        try:
            self._title_label.configure(text=self._title)
            self._artist_label.configure(text=self._artist)
            self._time_elapsed_label.configure(text=_fmt_time(0))
            self._progress_bar.configure(width=0)
            self._lyric_label.configure(text="")
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
        """Set the slider programmatically without triggering the user handler."""
        try:
            self._slider_suppress = True
            self._slider.set(int(volume))
        except (tk.TclError, AttributeError):
            pass
        finally:
            self._slider_suppress = False

    def _apply_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        try:
            self._vol_icon.configure(text="🔇" if self._muted else "🔊")
        except (tk.TclError, AttributeError):
            pass

    def _on_slider_command(self, value) -> None:
        # tk Scale fires this both for user drags AND programmatic set();
        # only user interaction should be forwarded upstream, debounced.
        if self._slider_suppress:
            return
        volume = int(value)
        if volume == self._last_user_volume:
            return
        self._last_user_volume = volume
        # Debounce: only send once the user stops dragging for 250ms.
        if self._volume_debounce_job is not None:
            try:
                self._root.after_cancel(self._volume_debounce_job)
            except tk.TclError:
                pass
        self._volume_debounce_job = self._root.after(250, self._fire_volume, volume)

    def _apply_artwork(self, data: bytes) -> None:
        try:
            from PIL import Image, ImageTk

            img = Image.open(io.BytesIO(data))
            img.thumbnail((_ART_SIZE, _ART_SIZE))
            self._art_photo = ImageTk.PhotoImage(img)
            self._art_label.configure(image=self._art_photo, text="")
            self._art_label.image = self._art_photo
        except Exception as e:
            logger.debug(f"Artwork render failed: {e}")

    def _apply_lyrics(self, fetch_id: int, lines) -> None:
        if fetch_id != self._lyric_fetch_id:
            return  # stale result for an older track
        self._lyrics = lines or []
        self._lyric_index = -1

    def _apply_progress(self, progress_ms: int, speed: float) -> None:
        self._progress_ms = int(progress_ms)
        self._progress_ts = time.monotonic()
        self._speed = float(speed) if speed else 0.0

    def _current_progress(self) -> int:
        """Progress in ms, extrapolated from the last known server update."""
        if self._speed:
            elapsed = (time.monotonic() - self._progress_ts) * 1000 * self._speed
            return int(self._progress_ms + elapsed)
        return self._progress_ms

    def _apply_duration(self, duration_ms: int) -> None:
        self._duration_ms = max(0, int(duration_ms))
        try:
            self._time_total_label.configure(text=_fmt_time(self._duration_ms))
        except (tk.TclError, AttributeError):
            pass

    def _update_progress_bar(self) -> None:
        current = self._current_progress()
        if self._duration_ms:
            current = min(current, self._duration_ms)
        try:
            self._time_elapsed_label.configure(text=_fmt_time(current))
            if self._duration_ms:
                bar_width = self._progress_bar.master.winfo_width()
                filled = int(bar_width * current / self._duration_ms)
                if filled < 1:
                    filled = 1 if current > 0 else 0
                self._progress_bar.configure(width=min(filled, bar_width))
        except (tk.TclError, AttributeError):
            pass

    # ---------- lyrics ----------

    def _start_lyric_fetch(self, title: str, artist: str) -> None:
        self._lyrics = []
        self._lyric_index = -1
        self._lyric_fetch_id += 1
        fetch_id = self._lyric_fetch_id
        duration = self._duration_ms or None

        def worker():
            lines = _fetch_synced_lyrics(title, artist, duration)
            if self._root is not None:
                self._queue.put(("lyrics", fetch_id, lines))

        threading.Thread(target=worker, daemon=True).start()

    def _update_lyric_line(self) -> None:
        if not self._lyrics or not self._lyric_label:
            return
        # The audio is buffered client-side, so lyrics driven by raw server
        # progress trail the music; advance the lookup to compensate.
        current = self._current_progress() + _LYRIC_ADVANCE_MS
        index = -1
        for i, (ms, _text) in enumerate(self._lyrics):
            if ms <= current:
                index = i
            else:
                break
        if index != self._lyric_index:
            self._lyric_index = index
            text = self._lyrics[index][1] if index >= 0 else ""
            try:
                self._lyric_label.configure(text=text)
            except tk.TclError:
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

    def _request_close(self) -> None:
        """✕ clicked: hide and remember the choice via the close handler."""
        self._apply_hide()
        if self._on_close:
            try:
                self._on_close()
            except Exception as e:
                logger.debug(f"Mini player close handler error: {e}")

    # ---------- public API (any thread) ----------

    def set_command_handler(self, handler: CommandHandler) -> None:
        self._on_command = handler

    def set_volume_handler(self, handler: VolumeHandler) -> None:
        self._on_volume = handler

    def set_close_handler(self, handler: CloseHandler) -> None:
        self._on_close = handler

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

    def update_track(self, title: str, artist: str, duration_ms: int = 0) -> None:
        changed = (title, artist) != (self._title, self._artist)
        # cache first so values survive a window that is not yet created
        self._title = title or "—"
        self._artist = artist or ""
        self._duration_ms = int(duration_ms or 0)
        if self._root is not None:
            self._queue.put(("track", self._title, self._artist))
            self._queue.put(("duration", self._duration_ms))
        if changed and title:
            self._start_lyric_fetch(title, artist)

    def update_progress(self, progress_ms: int, speed: float) -> None:
        if self._root is not None:
            self._queue.put(("progress", int(progress_ms), float(speed)))

    def update_duration(self, duration_ms: int) -> None:
        if self._root is not None:
            self._queue.put(("duration", int(duration_ms)))

    def set_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        if self._root is not None:
            self._queue.put(("playing", self._playing))

    def set_volume(self, volume: int) -> None:
        if self._root is not None:
            self._queue.put(("volume", int(volume)))

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._root is not None:
            self._queue.put(("muted", self._muted))

    def set_artwork(self, data: bytes) -> None:
        if self._root is not None and data:
            self._queue.put(("artwork", data))


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


def update_track(title: str, artist: str, duration_ms: int = 0) -> None:
    if _enabled:
        _mgr.update_track(title, artist, duration_ms)
    else:
        # keep track state fresh even while hidden
        _mgr._title, _mgr._artist = title or "—", artist or ""
        _mgr._duration_ms = int(duration_ms or 0)


def update_progress(progress_ms: int, speed: float) -> None:
    _mgr.update_progress(progress_ms, speed)


def update_duration(duration_ms: int) -> None:
    _mgr.update_duration(duration_ms)


def set_playing(playing: bool) -> None:
    if _enabled:
        _mgr.set_playing(playing)


def set_volume(volume: int) -> None:
    _mgr.set_volume(volume)


def set_muted(muted: bool) -> None:
    _mgr.set_muted(muted)


def set_artwork(data: bytes) -> None:
    if _enabled:
        _mgr.set_artwork(data)


def set_command_handler(handler: CommandHandler) -> None:
    _mgr.set_command_handler(handler)


def set_volume_handler(handler: VolumeHandler) -> None:
    _mgr.set_volume_handler(handler)


def set_close_handler(handler: CloseHandler) -> None:
    _mgr.set_close_handler(handler)
