"""
Mini player: borderless always-on-top popup showing the track currently
streamed from Music Assistant, with album artwork, track title/artist,
a synced lyric line, play/pause/prev/next/stop buttons and a volume
slider. Commands are forwarded upstream via Sendspin.

Visual design ("ambient glass"): the album artwork is blown up, blurred and
dimmed into the window background (iOS lock-screen style); controls are drawn
on a single canvas with rounded corners cut out via -transparentcolor.
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
_WIDTH = 424
_HEIGHT = 212
_ALPHA = 0.93

# Magic color used to punch rounded corners out of the window.
_MAGIC = "#010203"
_MAGIC_RGB = (0x01, 0x02, 0x03)

# Layout metrics
_PAD = 20                 # outer padding
_ART_SIZE = 96            # artwork thumbnail size
_ART_RADIUS = 14
_RADIUS = 22              # window corner radius
_TITLE_Y = 38
_ARTIST_Y = 64
_LYRIC_Y = 88
_BAR_Y = 126              # progress bar centerline (below the artwork)
_CTRL_CY = 178            # control buttons centerline
_VOL_CY = _CTRL_CY

# Palette
_SCRIM = 88               # 0-255 black scrim over the blurred art
_PANEL_FALLBACK_TOP = "#232937"
_PANEL_FALLBACK_BOT = "#141822"
_FG = "#F7F8FA"
_FG_DIM = "#A6ADBD"
_ACCENT = "#8B93FF"
_ACCENT_DIM = "#5B62C9"
_TEXT_SHADOW = "#0B0D13"


def _mix(a, b, t):
    """Blend two RGB tuples; t=0 -> a, t=1 -> b."""
    return tuple(int(round(x * (1 - t) + y * t)) for x, y in zip(a, b))


def _rgb_to_hex(rgb):
    return "#{:02X}{:02X}{:02X}".format(*rgb)


# UI chrome colors derived from the current backdrop so buttons/tracks
# harmonize with whatever the album art is (fallback: neutral slate).
_THEME = {
    "btn_fill": "#2E3442",
    "btn_fill_hover": "#3C4456",
    "btn_outline": "#454D61",
    "track": "#39404F",
    "accent": "#8B93FF",
    "accent_dim": "#5B62C9",
}

_FALLBACK_AVG = (0x24, 0x2A, 0x38)


def _derive_theme(avg_rgb):
    """Recompute chrome colors from the blurred backdrop's average color.

    The accent ALWAYS derives from the artwork - every track recolors the
    player, no fixed fallback. Even near-gray covers produce a tinted
    accent: their slight channel imbalance decides the hue, and the clamped
    saturation keeps it subtle.
    """
    import colorsys

    orig_rgb = avg_rgb  # accent hue must come from the UNLIFTED color
    r, g, b = avg_rgb
    lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
    if lum < 46:  # very dark art: lift so controls stay visible
        avg_rgb = _mix(avg_rgb, (120, 120, 135), 0.45)
    _THEME["btn_fill"] = _rgb_to_hex(_mix(avg_rgb, (0, 0, 0), 0.28))
    _THEME["btn_fill_hover"] = _rgb_to_hex(_mix(avg_rgb, (255, 255, 255), 0.12))
    _THEME["btn_outline"] = _rgb_to_hex(_mix(avg_rgb, (255, 255, 255), 0.24))
    _THEME["track"] = _rgb_to_hex(_mix(avg_rgb, (0, 0, 0), 0.18))

    # Accent (play button / progress fill / lyric): lift the art's hue to a
    # bright, visible tint against the dark backdrop.
    h, l, s = colorsys.rgb_to_hls(*[c / 255 for c in orig_rgb])
    l = min(max(l, 0.58), 0.72)
    s = min(max(s, 0.38), 0.75)
    ar, ag, ab = (int(round(c * 255)) for c in colorsys.hls_to_rgb(h, l, s))
    _THEME["accent"] = _rgb_to_hex((ar, ag, ab))
    dr, dg, db = (int(round(c * 255)) for c in colorsys.hls_to_rgb(h, l - 0.10, s))
    _THEME["accent_dim"] = _rgb_to_hex((dr, dg, db))


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


def _rounded_mask(size: int, radius: int):
    """PIL 'L' mask with rounded corners."""
    from PIL import Image, ImageDraw

    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=radius, fill=255
    )
    return mask


def _window_mask():
    """Rounded-rectangle mask matching the window outline."""
    from PIL import Image, ImageDraw

    mask = Image.new("L", (_WIDTH, _HEIGHT), 0)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, _WIDTH - 1, _HEIGHT - 1), radius=_RADIUS, fill=255
    )
    return mask


_SS = 4  # supersampling factor for anti-aliased shapes


def _aa_ellipse(diameter: int, fill: str, outline: str = None, outline_w: int = 0):
    """Anti-aliased circle as an RGBA PIL image (drawn at 4x, downscaled)."""
    from PIL import Image, ImageDraw

    size = diameter * _SS
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.ellipse(
        (outline_w * _SS, outline_w * _SS, size - outline_w * _SS - 1, size - outline_w * _SS - 1),
        fill=fill,
        outline=outline,
        width=outline_w * _SS,
    )
    return img.resize((diameter, diameter), Image.LANCZOS)


def _compose_background(art_bytes: Optional[bytes]):
    """Build the ambient background image: blurred artwork + dark scrim,
    static slider tracks and a hairline card outline, with rounded corners
    filled in the magic transparent color. Rendered at 2x for smooth edges."""
    from PIL import Image, ImageDraw, ImageFilter

    S = 2  # background supersample
    W, H = _WIDTH * S, _HEIGHT * S

    base = Image.new("RGB", (W, H))

    if art_bytes:
        try:
            src = Image.open(io.BytesIO(art_bytes)).convert("RGB")
            # Cover-fit scale, then heavy blur for the ambient backdrop
            scale = max(W / src.width, H / src.height) * 1.25
            back = src.resize((int(src.width * scale) + 1, int(src.height * scale) + 1))
            back = back.crop((
                (back.width - W) // 2,
                (back.height - H) // 2,
                (back.width - W) // 2 + W,
                (back.height - H) // 2 + H,
            ))
            back = back.filter(ImageFilter.GaussianBlur(26 * S))
            # Dim so white text stays readable over any artwork
            back = Image.eval(back, lambda v: v * (255 - _SCRIM) // 255)
            base.paste(back, (0, 0))
        except Exception as e:
            logger.debug(f"Ambient backdrop failed: {e}")
            art_bytes = None
    if not art_bytes:
        # Fallback: quiet vertical gradient
        top = (_PANEL_FALLBACK_TOP[1:3], _PANEL_FALLBACK_TOP[3:5], _PANEL_FALLBACK_TOP[5:7])
        bot = (_PANEL_FALLBACK_BOT[1:3], _PANEL_FALLBACK_BOT[3:5], _PANEL_FALLBACK_BOT[5:7])
        for y in range(H):
            t = y / max(1, H - 1)
            col = tuple(int(int(a, 16) * (1 - t) + int(b, 16) * t) for a, b in zip(top, bot))
            ImageDraw.Draw(base).line([(0, y), (W, y)], fill=col)

    # Derive chrome colors (buttons/tracks) from this backdrop
    if art_bytes:
        import numpy as np

        avg = tuple(int(c) for c in np.asarray(base).reshape(-1, 3).mean(axis=0))
        _derive_theme(avg)
    else:
        _derive_theme(_FALLBACK_AVG)

    d = ImageDraw.Draw(base)

    # Static slider tracks (progress + volume), pill shaped
    bar_x0, bar_x1 = _PAD + 46, _WIDTH - _PAD - 46
    d.rounded_rectangle(
        (bar_x0 * S, (_BAR_Y - 3) * S, (bar_x1 + 3) * S, (_BAR_Y + 3) * S),
        radius=3 * S, fill=_THEME["track"],
    )
    d.rounded_rectangle(
        ((_WIDTH - 148) * S, (_VOL_CY - 2) * S, (_WIDTH - _PAD) * S, (_VOL_CY + 2) * S),
        radius=2 * S, fill=_THEME["track"],
    )

    base = base.resize((_WIDTH, _HEIGHT), Image.LANCZOS)

    # Punch rounded corners: binary cut against a 4x-supersampled mask, so
    # the edge follows the ideal curve as closely as whole pixels allow.
    # Chroma-key transparency cannot do per-pixel alpha; any dithering or
    # blending at the edge reads as dots/fringe, so a clean cut wins.
    import numpy as np

    ss = 4
    big = Image.new("L", (_WIDTH * ss, _HEIGHT * ss), 0)
    ImageDraw.Draw(big).rounded_rectangle(
        (0, 0, _WIDTH * ss - 1, _HEIGHT * ss - 1), radius=_RADIUS * ss, fill=255
    )
    coverage = np.asarray(
        big.resize((_WIDTH, _HEIGHT), Image.BILINEAR), dtype=np.float32
    ) / 255.0
    arr = np.asarray(base).copy()
    arr[coverage < 0.5] = _MAGIC_RGB
    base = Image.fromarray(arr, "RGB")

    from PIL import ImageTk

    return ImageTk.PhotoImage(base)


class _MiniPlayerManager:
    """Single hidden tk root in a background thread; renders the mini player."""

    def __init__(self):
        self._root: Optional[tk.Tk] = None
        self._thread: Optional[threading.Thread] = None
        self._ready = threading.Event()
        self._queue: "queue.Queue[tuple]" = queue.Queue()

        self._win: Optional[tk.Toplevel] = None
        self._canvas: Optional[tk.Canvas] = None

        # canvas item ids
        self._bg_id = None
        self._art_id = None
        self._art_photo = None         # keep refs so tk doesn't GC them
        self._thumb_photo = None
        self._photo_refs: list = []    # all PhotoImages handed to the canvas
        self._title_id = None
        self._artist_id = None
        self._lyric_id = None
        self._elapsed_id = None
        self._total_id = None
        self._sync_id = None
        self._bar_fill_id = None
        self._bar_right_cap_id = None
        self._knob_id = None
        self._play_glyph_id = None
        self._vol_icon_id = None
        self._vol_knob_id = None
        self._btn_ids: dict = {}
        self._button_images: dict = {}   # id(item) -> (normal, hover, is_play)
        self._button_specs: list = []    # (item, cmd, is_play, r, cx, cy)
        self._play_pt = 15

        self._visible = False
        self._playing = False
        self._muted = False
        self._title = ""
        self._artist = ""
        self._position: Optional[tuple] = None
        self._art_data: Optional[bytes] = None
        self._volume_cache: Optional[int] = None

        # geometry cache for the progress bar / volume slider
        self._bar_x0, self._bar_x1 = _PAD + 46, _WIDTH - _PAD - 46
        self._vol_x0, self._vol_x1 = _WIDTH - 148, _WIDTH - _PAD

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
        try:
            win.attributes("-transparentcolor", _MAGIC)
        except tk.TclError:
            pass
        win.configure(bg=_MAGIC)
        win.geometry(f"{_WIDTH}x{_HEIGHT}")
        win.withdraw()
        self._win = win

        canvas = tk.Canvas(
            win, width=_WIDTH, height=_HEIGHT, bg=_MAGIC,
            highlightthickness=0, bd=0,
        )
        canvas.pack(fill="both", expand=True)
        self._canvas = canvas

        self._build_items(canvas)

        self._ready.set()
        self._poll()
        root.mainloop()

    # ---------- canvas construction ----------

    def _build_items(self, canvas: tk.Canvas) -> None:
        import tkinter.font as tkfont

        self._fonts = {
            "title": tkfont.Font(family="Microsoft YaHei UI", size=13, weight="bold"),
            "text": tkfont.Font(family="Microsoft YaHei UI", size=10),
        }
        self._bg_photo = _compose_background(None)
        self._bg_id = canvas.create_image(0, 0, image=self._bg_photo, anchor="nw")

        self._thumb_photo = self._make_thumb(None)
        self._art_id = canvas.create_image(
            _PAD, _PAD, image=self._thumb_photo, anchor="nw"
        )

        self._title_id = canvas.create_text(
            _PAD + _ART_SIZE + 18, _TITLE_Y, text="", anchor="w",
            fill=_FG, font=("Microsoft YaHei UI", 13, "bold"),
        )
        self._artist_id = canvas.create_text(
            _PAD + _ART_SIZE + 18, _ARTIST_Y, text="", anchor="w",
            fill=_FG_DIM, font=("Microsoft YaHei UI", 10),
        )
        self._lyric_id = canvas.create_text(
            _PAD + _ART_SIZE + 18, _LYRIC_Y, text="", anchor="w",
            fill=_THEME["accent"], font=("Microsoft YaHei UI", 10),
        )

        # close button (top-right): glyph only, red hover
        canvas.create_text(
            _WIDTH - 29, 25, text="\u2715", fill=_FG_DIM,
            font=("Segoe UI", 10), tags=("close",),
        )
        canvas.tag_bind("close", "<Button-1>", lambda e: self._request_close())
        canvas.tag_bind("close", "<Enter>", lambda e: canvas.itemconfigure("close", fill="#F87171"))
        canvas.tag_bind("close", "<Leave>", lambda e: canvas.itemconfigure("close", fill=_FG_DIM))

        # --- progress bar: track is baked into the background; fill is a
        # round-cap line, knob an anti-aliased image ---
        self._bar_fill_id = canvas.create_line(
            self._bar_x0 + 3, _BAR_Y, self._bar_x0 + 3, _BAR_Y,
            fill=_THEME["accent"], width=6, capstyle="round",
        )
        self._knob_photo = self._to_photo(_aa_ellipse(13, "#FFFFFF"))
        self._knob_id = canvas.create_image(
            self._bar_x0 + 3, _BAR_Y, image=self._knob_photo, anchor="center",
        )
        canvas.addtag_all("dragsurface")

        self._elapsed_id = canvas.create_text(
            self._bar_x0, _BAR_Y + 14, text="0:00", anchor="nw",
            fill=_FG_DIM, font=("Segoe UI", 8),
        )
        self._total_id = canvas.create_text(
            self._bar_x1 + 3, _BAR_Y + 14, text="0:00", anchor="ne",
            fill=_FG_DIM, font=("Segoe UI", 8),
        )
        # Playback clock skew vs the Sendspin server, between the time labels.
        self._sync_id = canvas.create_text(
            (self._bar_x0 + self._bar_x1 + 3) / 2, _BAR_Y + 14, text="",
            anchor="center", fill=_FG_DIM, font=("Segoe UI", 8),
        )

        # --- transport buttons: anti-aliased circles with hover variants ---
        cy = _CTRL_CY
        self._glyph_centers: list = []
        self._button_specs: list = []
        for cx, cmd, glyph, is_play in (
            (_PAD + 22, "previous", "\u23EE", False),
            (_PAD + 66, "play_pause", "\u25B6", True),
            (_PAD + 110, "next", "\u23ED", False),
            (_PAD + 148, "stop", "\u23F9", False),
        ):
            r = 44 if is_play else 32  # image diameter (2x visual radius)
            pt = 15 if is_play else (10 if glyph == "\u23F9" else 11)
            item = canvas.create_image(cx, cy, anchor="center")
            glyph_item = canvas.create_text(
                cx, cy, text=glyph,
                fill="#FFFFFF" if is_play else _FG,
                font=("Segoe UI Symbol", pt),
            )
            self._btn_ids[cmd] = item
            if is_play:
                self._play_glyph_id = glyph_item
                self._play_pt = pt
            self._glyph_centers.append((glyph_item, cx, cy, pt))
            self._button_specs.append((item, cmd, is_play, r, cx, cy))
        self._refresh_button_theme(canvas)

        def _make_enter(item):
            def on_enter(e):
                hover = self._button_images[id(item)][1]
                canvas.itemconfigure(item, image=hover)
            return on_enter

        def _make_leave(item):
            def on_leave(e):
                normal = self._button_images[id(item)][0]
                canvas.itemconfigure(item, image=normal)
            return on_leave

        for item, cmd, is_play, r, cx, cy in self._button_specs:
            glyph_item = next(g for g, gx, gy, _p in self._glyph_centers if (gx, gy) == (cx, cy))
            canvas.tag_bind(item, "<Button-1>", lambda e, c=cmd: self._fire_command(c))
            canvas.tag_bind(glyph_item, "<Button-1>", lambda e, c=cmd: self._fire_command(c))
            canvas.tag_bind(item, "<Enter>", _make_enter(item))
            canvas.tag_bind(item, "<Leave>", _make_leave(item))
            canvas.tag_bind(glyph_item, "<Enter>", _make_enter(item))
            canvas.tag_bind(glyph_item, "<Leave>", _make_leave(item))

        # --- volume ---
        self._vol_icon_id = canvas.create_text(
            self._vol_x0 - 22, _VOL_CY, text="\U0001F50A",
            fill=_FG_DIM, font=("Segoe UI Symbol", 12),
        )
        canvas.tag_bind(self._vol_icon_id, "<Button-1>", lambda e: self._fire_command("mute"))
        canvas.tag_bind(self._vol_icon_id, "<Enter>",
                        lambda e: canvas.itemconfigure(self._vol_icon_id, fill=_FG))
        canvas.tag_bind(self._vol_icon_id, "<Leave>",
                        lambda e: canvas.itemconfigure(self._vol_icon_id, fill=_FG_DIM))

        self._vol_knob_photo = self._to_photo(_aa_ellipse(11, "#FFFFFF"))
        self._vol_knob_id = canvas.create_image(
            self._vol_x0, _VOL_CY, image=self._vol_knob_photo, anchor="center",
        )
        hit = canvas.create_rectangle(
            self._vol_x0 - 8, _VOL_CY - 10, self._vol_x1 + 8, _VOL_CY + 10,
            fill="", outline="", tags=("volslider",),
        )
        canvas.tag_bind("volslider", "<Button-1>", self._on_volume_click)
        canvas.tag_bind("volslider", "<B1-Motion>", self._on_volume_drag)

        # dragging the window: any press that is not a control
        for tag in ("dragsurface",):
            canvas.tag_bind(tag, "<Button-1>", self._on_drag_start)
            canvas.tag_bind(tag, "<B1-Motion>", self._on_drag_motion)

        # Center glyphs once font metrics are available
        canvas.after_idle(self._center_glyphs)

    def _glyph_ink_offset(self, glyph: str, pt: int):
        """Offset that moves a text anchor so the glyph INK (not the font line
        box) is centered. Measured with the same TrueType font tk renders."""
        try:
            from PIL import ImageFont

            px = max(8, round(self._root.winfo_fpixels("1i") / 72 * pt))
            font = ImageFont.truetype("seguisym.ttf", px)
            x0, y0, x1, y1 = font.getbbox(glyph)
            ascent, descent = font.getmetrics()
            advance = font.getlength(glyph)
            dx = -((x0 + x1) / 2 - advance / 2)
            dy = -((y0 + y1) / 2 - (ascent + descent) / 2)
            return dx, dy
        except Exception:
            return 0.0, 0.0

    def _center_glyphs(self) -> None:
        """Position each button glyph by its real ink bounding box."""
        try:
            canvas = self._canvas
            for item, cx, cy, pt in self._glyph_centers:
                dx, dy = self._glyph_ink_offset(canvas.itemcget(item, "text"), pt)
                canvas.coords(item, cx + dx, cy + dy)
        except (tk.TclError, AttributeError):
            pass

    def _to_photo(self, pil_image):
        """Convert an RGBA PIL image to a canvas-ready PhotoImage (cached ref)."""
        from PIL import ImageTk

        photo = ImageTk.PhotoImage(pil_image)
        self._photo_refs.append(photo)
        return photo

    def _refresh_button_theme(self, canvas: tk.Canvas) -> None:
        """(Re)render button circle images from the current theme colors."""
        for item, _cmd, is_play, r, _cx, _cy in self._button_specs:
            if is_play:
                normal = _aa_ellipse(r, _THEME["accent"])
                hover = _aa_ellipse(r, _THEME["accent_dim"])
            else:
                normal = _aa_ellipse(r, _THEME["btn_fill"], _THEME["btn_outline"], 1)
                hover = _aa_ellipse(r, _THEME["btn_fill_hover"], _THEME["btn_outline"], 1)
            img_normal = self._to_photo(normal)
            img_hover = self._to_photo(hover)
            self._button_images[id(item)] = (img_normal, img_hover, is_play)
            canvas.itemconfigure(item, image=img_normal)
        # accent-colored items follow the theme too
        try:
            canvas.itemconfigure(self._bar_fill_id, fill=_THEME["accent"])
            canvas.itemconfigure(self._lyric_id, fill=_THEME["accent"])
        except (tk.TclError, AttributeError):
            pass

    def _make_thumb(self, data: Optional[bytes]):
        """Rounded artwork thumbnail with truly transparent corners
        (RGBA alpha), so no dark corners show over the ambient backdrop."""
        from PIL import Image, ImageDraw, ImageFont, ImageTk

        size = (_ART_SIZE, _ART_SIZE)
        mask = _rounded_mask(_ART_SIZE, _ART_RADIUS)
        if data:
            try:
                img = Image.open(io.BytesIO(data)).convert("RGBA").resize(size)
                img.putalpha(mask)
                return ImageTk.PhotoImage(img)
            except Exception as e:
                logger.debug(f"Artwork render failed: {e}")
        ph = Image.new("RGBA", size, (26, 32, 48, 255))
        d = ImageDraw.Draw(ph)
        d.rounded_rectangle((0, 0, _ART_SIZE - 1, _ART_SIZE - 1), _ART_RADIUS,
                            outline=(70, 80, 104, 255))
        try:
            glyph_font = ImageFont.truetype("seguisym.ttf", 44)
            bbox = d.textbbox((0, 0), "\u266A", font=glyph_font)
            w = bbox[2] - bbox[0]
            h = bbox[3] - bbox[1]
            d.text(((_ART_SIZE - w) / 2 - bbox[0], (_ART_SIZE - h) / 2 - bbox[1]),
                   "\u266A", font=glyph_font, fill=(139, 147, 255, 255))
        except OSError:
            pass
        ph.putalpha(mask)
        return ImageTk.PhotoImage(ph)

    def ensure(self) -> bool:
        # The thread may have died (mainloop crashed) while _root is still
        # set; without checking liveness, show() silently no-ops forever.
        if self._root is not None and self._thread and self._thread.is_alive():
            return True
        if self._thread and not self._thread.is_alive():
            self._root = None  # crashed: start fresh next time
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

    # ---------- volume interaction ----------

    def _volume_from_event(self, event) -> int:
        x = min(max(event.x, self._vol_x0), self._vol_x1)
        ratio = (x - self._vol_x0) / max(1, self._vol_x1 - self._vol_x0)
        return int(round(ratio * 100))

    def _on_volume_click(self, event) -> None:
        self._handle_user_volume(self._volume_from_event(event))

    def _on_volume_drag(self, event) -> None:
        self._handle_user_volume(self._volume_from_event(event))

    def _handle_user_volume(self, volume: int) -> None:
        if volume == self._last_user_volume:
            return
        self._last_user_volume = volume
        self._draw_volume(volume)
        if self._volume_debounce_job is not None:
            try:
                self._root.after_cancel(self._volume_debounce_job)
            except tk.TclError:
                pass
        self._volume_debounce_job = self._root.after(250, self._fire_volume, volume)

    def _draw_volume(self, volume: int) -> None:
        try:
            span = self._vol_x1 - self._vol_x0
            x = self._vol_x0 + int(span * max(0, min(100, volume)) / 100)
            self._canvas.coords(self._vol_knob_id, x, _VOL_CY)
        except (tk.TclError, AttributeError):
            pass

    # ---------- event pump ----------

    def _poll(self) -> None:
        # Drain the message queue, then refresh lyrics/progress. Any exception
        # must NOT break the after-loop: a single broken tick would silently
        # kill the whole tk thread, leaving ensure() reporting "alive" via
        # _root (set before mainloop) while no one consumes the queue.
        try:
            while True:
                kind, *args = self._queue.get_nowait()
                handler = getattr(self, f"_apply_{kind}", None)
                if handler:
                    handler(*args)
        except queue.Empty:
            pass
        except Exception as e:
            logger.debug(f"Mini player poll queue error: {e}")
        try:
            self._update_lyric_line()
        except Exception as e:
            logger.debug(f"Mini player lyric update error: {e}")
        try:
            self._update_progress_bar()
        except Exception as e:
            logger.debug(f"Mini player progress update error: {e}")
        try:
            self._root.after(_LYRIC_POLL_MS, self._poll)
        except Exception as e:
            # Root was destroyed; this thread is done. Mark dead so ensure()
            # starts a new one on the next show().
            logger.debug(f"Mini player poll loop terminated: {e}")
            self._root = None

    # ---------- state application (tk thread) ----------

    def _apply_show(self) -> None:
        if self._win is None:
            return
        self._apply_track(self._title, self._artist)
        self._apply_playing(self._playing)
        # Messages queued before the window existed were dropped; re-apply
        # the full cached state so nothing is stale on first paint.
        self._apply_duration(self._duration_ms)
        self._apply_muted(self._muted)
        if self._volume_cache is not None:
            self._draw_volume(self._volume_cache)
        if self._art_data:
            self._apply_artwork(self._art_data)
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

    @staticmethod
    def _truncate(font, text: str, max_width: int) -> str:
        """Clip text with an ellipsis so it fits max_width pixels."""
        if not text:
            return ""
        full = text
        while text and font.measure(text) > max_width:
            text = text[:-1]
        if len(text) < len(full):
            while text and font.measure(text + "\u2026") > max_width:
                text = text[:-1]
            text += "\u2026"
        return text

    def _apply_clear_track(self) -> None:
        try:
            self._canvas.itemconfigure(self._title_id, text="")
            self._canvas.itemconfigure(self._artist_id, text="")
            self._canvas.itemconfigure(self._lyric_id, text="")
            self._canvas.itemconfigure(self._elapsed_id, text=_fmt_time(0))
            self._canvas.itemconfigure(self._total_id, text=_fmt_time(0))
            self._draw_progress(0)
        except (tk.TclError, AttributeError):
            pass

    def _apply_track(self, title: str, artist: str) -> None:
        self._title = title or "\u2014"
        self._artist = artist or ""
        # new track: reset progress display (duration arrives separately)
        self._progress_ms = 0
        self._progress_ts = time.monotonic()
        self._speed = 0.0
        try:
            canvas = self._canvas
            max_w = _WIDTH - (_PAD + _ART_SIZE + 18) - 48
            canvas.itemconfigure(
                self._title_id,
                text=self._truncate(self._fonts["title"], self._title, max_w),
            )
            canvas.itemconfigure(
                self._artist_id,
                text=self._truncate(self._fonts["text"], self._artist, max_w),
            )
            canvas.itemconfigure(self._lyric_id, text="")
            canvas.itemconfigure(self._elapsed_id, text=_fmt_time(0))
            self._draw_progress(0)
        except tk.TclError:
            pass

    def _apply_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        try:
            if self._play_glyph_id is not None:
                glyph = "\u23F8" if self._playing else "\u25B6"
                canvas = self._canvas
                canvas.itemconfigure(self._play_glyph_id, text=glyph)
                # the new glyph has a different ink box: re-center it
                cx, cy = self._play_center
                canvas.after_idle(
                    lambda: self._center_glyph_item(
                        self._play_glyph_id, glyph, self._play_pt, cx, cy
                    )
                )
        except (tk.TclError, AttributeError):
            pass

    def _center_glyph_item(self, item, glyph: str, pt: int, cx, cy) -> None:
        try:
            dx, dy = self._glyph_ink_offset(glyph, pt)
            self._canvas.coords(item, cx + dx, cy + dy)
        except (tk.TclError, AttributeError):
            pass

    def _apply_volume(self, volume: int) -> None:
        """Set the slider programmatically without triggering the user handler."""
        try:
            self._slider_suppress = True
            self._last_user_volume = int(volume)
            self._draw_volume(int(volume))
        finally:
            self._slider_suppress = False

    def _apply_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        try:
            glyph = "\U0001F507" if self._muted else "\U0001F50A"
            self._canvas.itemconfigure(self._vol_icon_id, text=glyph)
        except (tk.TclError, AttributeError):
            pass

    def _apply_artwork(self, data: bytes) -> None:
        if not data:
            return
        self._art_data = bytes(data)
        # Independent try blocks: a failure in one step (e.g. thumbnail
        # decode) must not leave the others stuck on the previous track.
        try:
            # _compose_background also derives the chrome theme from the art
            self._bg_photo = _compose_background(self._art_data)
            self._canvas.itemconfigure(self._bg_id, image=self._bg_photo)
        except Exception as e:
            logger.debug(f"Artwork background failed: {e}")
        try:
            self._thumb_photo = self._make_thumb(self._art_data)
            self._canvas.itemconfigure(self._art_id, image=self._thumb_photo)
        except Exception as e:
            logger.debug(f"Artwork thumbnail failed: {e}")
        try:
            self._refresh_button_theme(self._canvas)
        except Exception as e:
            logger.debug(f"Artwork theme refresh failed: {e}")

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
            self._canvas.itemconfigure(self._total_id, text=_fmt_time(self._duration_ms))
        except (tk.TclError, AttributeError):
            pass

    def _apply_sync(self, offset_ms: int, synchronized: bool) -> None:
        """Show the Sendspin playback clock skew (+ms slow / -ms fast)."""
        try:
            if not synchronized or self._sync_id is None:
                self._canvas.itemconfigure(self._sync_id, text="")
                return
            if offset_ms > 0:
                label = f"+{offset_ms}ms"
            elif offset_ms < 0:
                label = f"{offset_ms}ms"
            else:
                label = "0ms"
            self._canvas.itemconfigure(self._sync_id, text=label)
        except (tk.TclError, AttributeError):
            pass

    def _draw_progress(self, current: int) -> None:
        canvas = self._canvas
        span = self._bar_x1 - self._bar_x0
        if self._duration_ms > 0:
            frac = max(0.0, min(1.0, current / self._duration_ms))
        else:
            frac = 0.0
        x = self._bar_x0 + 3 + int((span - 6) * frac)
        # round-cap line: cap radius (3) extends past the endpoints
        canvas.coords(self._bar_fill_id, self._bar_x0 + 3, _BAR_Y, x, _BAR_Y)
        canvas.coords(self._knob_id, x, _BAR_Y)

    def _update_progress_bar(self) -> None:
        current = self._current_progress()
        if self._duration_ms:
            current = min(current, self._duration_ms)
        try:
            self._canvas.itemconfigure(self._elapsed_id, text=_fmt_time(current))
            self._draw_progress(current)
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
        if not self._lyrics or not self._lyric_id:
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
                max_w = _WIDTH - (_PAD + _ART_SIZE + 18) - 48
                self._canvas.itemconfigure(
                    self._lyric_id,
                    text=self._truncate(self._fonts["text"], text, max_w),
                )
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
        """\u2715 clicked: hide and remember the choice via the close handler."""
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

    def clear_track(self) -> None:
        """Clear the current track display (new stream starting). No lyric fetch."""
        self._title = ""
        self._artist = ""
        self._lyrics = []
        self._lyric_index = -1
        self._progress_ms = 0
        self._progress_ts = 0.0
        self._speed = 0.0
        self._lyric_fetch_id += 1  # invalidate in-flight lyric fetches
        if self._root is not None:
            self._queue.put(("clear_track",))

    def update_track(self, title: str, artist: str, duration_ms: int = 0) -> None:
        changed = (title, artist) != (self._title, self._artist)
        # cache first so values survive a window that is not yet created
        self._title = title or "\u2014"
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
        self._duration_ms = max(0, int(duration_ms))
        if self._root is not None:
            self._queue.put(("duration", self._duration_ms))

    def set_playing(self, playing: bool) -> None:
        self._playing = bool(playing)
        if self._root is not None:
            self._queue.put(("playing", self._playing))

    def set_volume(self, volume: int) -> None:
        self._volume_cache = int(volume)
        if self._root is not None:
            self._queue.put(("volume", int(volume)))

    def set_sync(self, offset_ms: int, synchronized: bool) -> None:
        if self._root is not None:
            self._queue.put(("sync", int(offset_ms), bool(synchronized)))

    def set_muted(self, muted: bool) -> None:
        self._muted = bool(muted)
        if self._root is not None:
            self._queue.put(("muted", self._muted))

    def set_artwork(self, data: bytes) -> None:
        if not data:
            return
        self._art_data = bytes(data)
        if self._root is not None:
            self._queue.put(("artwork", self._art_data))


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


def is_visible() -> bool:
    return _mgr.is_visible()


def set_command_handler(handler: CommandHandler) -> None:
    _mgr.set_command_handler(handler)


def set_volume_handler(handler: VolumeHandler) -> None:
    _mgr.set_volume_handler(handler)


def set_close_handler(handler: CloseHandler) -> None:
    _mgr.set_close_handler(handler)


def clear_track() -> None:
    _mgr.clear_track()


def update_track(title: str, artist: str, duration_ms: int = 0) -> None:
    _mgr.update_track(title, artist, duration_ms)


def update_duration(duration_ms: int) -> None:
    _mgr.update_duration(duration_ms)


def update_progress(progress_ms: int, speed: float) -> None:
    _mgr.update_progress(progress_ms, speed)


def set_playing(playing: bool) -> None:
    _mgr.set_playing(playing)


def set_volume(volume: int) -> None:
    _mgr.set_volume(volume)


def set_sync(offset_ms: int, synchronized: bool) -> None:
    _mgr.set_sync(offset_ms, synchronized)


def set_muted(muted: bool) -> None:
    _mgr.set_muted(muted)


def set_artwork(data: bytes) -> None:
    _mgr.set_artwork(data)
