"""
Native Dialogs using tkinter (built-in, zero extra size)
"""

import logging
import threading
import tkinter as tk
from tkinter import ttk
from typing import Optional

from src.i18n import get_i18n

logger = logging.getLogger(__name__)

_i18n = get_i18n()

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
        win.title(_i18n.t("device_status"))
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
            (_i18n.t("device_label"), name),
            (_i18n.t("ip_label"), ip),
            (_i18n.t("port_label"), port),
            (_i18n.t("version_label"), version),
            (_i18n.t("status_label"), _i18n.t("ready")),
        ]
        for label, value in rows:
            row = ttk.Frame(frame)
            row.pack(fill=tk.X, pady=4)
            ttk.Label(row, text=f"{label}:", font=("", 10)).pack(side=tk.LEFT)
            ttk.Label(row, text=value, font=("", 10, "bold")).pack(side=tk.RIGHT)

        ttk.Button(frame, text=_i18n.t("close"), command=win.destroy).pack(pady=(20, 0))
    except Exception as e:
        logger.error(f"Failed to show status dialog: {e}")


def _show_about(parent, version: str):
    try:
        import webbrowser
        from PIL import Image, ImageDraw

        W, H = 420, 340
        RADIUS = 18
        MAGIC = "#010203"
        BG = "#1A1F2E"
        BORDER = "#2A3350"
        ACCENT = "#8B93FF"
        FG = "#F7F8FA"
        FG_DIM = "#A6ADBD"
        FG_MUTED = "#6B7280"
        BTN_FILL = ACCENT
        BTN_HOVER = "#A5ABFF"

        win = tk.Toplevel(parent)
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        win.attributes("-alpha", 0.97)
        win.attributes("-transparentcolor", MAGIC)
        win.title(_i18n.t("about_title"))

        img = Image.new("RGB", (W, H), MAGIC)
        d = ImageDraw.Draw(img)
        d.rounded_rectangle(
            (0, 0, W - 1, H - 1),
            radius=RADIUS,
            fill=BG,
            outline=BORDER,
            width=1,
        )

        badge_size = 64
        badge = Image.new("RGBA", (badge_size, badge_size), (0, 0, 0, 0))
        bd = ImageDraw.Draw(badge)
        bd.ellipse((0, 0, badge_size - 1, badge_size - 1), fill=ACCENT)
        hm = 16
        bd.polygon(
            [(hm, badge_size // 2), (badge_size // 2, hm), (badge_size - hm, badge_size // 2)],
            fill="#FFFFFF",
        )
        bd.rectangle(
            [(hm + 4, badge_size // 2), (badge_size - hm - 4, badge_size - hm)],
            fill="#FFFFFF",
        )
        img.paste(badge, (W // 2 - badge_size // 2, 24), badge)

        btn_w, btn_h = 110, 34
        btn_x = (W - btn_w) // 2
        btn_y = H - 56
        d.rounded_rectangle(
            (btn_x, btn_y, btn_x + btn_w, btn_y + btn_h),
            radius=btn_h // 2,
            fill=BTN_FILL,
        )

        from PIL import ImageTk

        bg_photo = ImageTk.PhotoImage(img)
        canvas = tk.Canvas(win, width=W, height=H, highlightthickness=0, bd=0)
        canvas.pack()
        canvas.create_image(0, 0, anchor="nw", image=bg_photo)

        font_title = ("Microsoft YaHei UI", 15, "bold")
        font_version = ("Segoe UI", 11, "bold")
        font_body = ("Microsoft YaHei UI", 10)
        font_link = ("Microsoft YaHei UI", 10)
        font_copyright = ("Microsoft YaHei UI", 9)
        font_btn = ("Microsoft YaHei UI", 10, "bold")

        canvas.create_text(
            W // 2,
            102,
            text="Home Assistant Windows",
            font=font_title,
            fill=FG,
        )
        canvas.create_text(
            W // 2,
            128,
            text=f"v{version}",
            font=font_version,
            fill=ACCENT,
        )
        canvas.create_text(
            W // 2,
            168,
            text=_i18n.t("about_description"),
            font=font_body,
            fill=FG_DIM,
            justify="center",
        )
        canvas.create_text(
            W // 2,
            236,
            text=_i18n.t("about_copyright"),
            font=font_copyright,
            fill=FG_MUTED,
        )

        btn_label = tk.Label(
            win,
            text=_i18n.t("close"),
            font=font_btn,
            fg=FG,
            bg=BTN_FILL,
            cursor="hand2",
        )
        btn_label.place(x=btn_x, y=btn_y, width=btn_w, height=btn_h)
        btn_label.bind("<Button-1>", lambda e: win.destroy())
        btn_label.bind("<Enter>", lambda e: btn_label.configure(bg=BTN_HOVER))
        btn_label.bind("<Leave>", lambda e: btn_label.configure(bg=BTN_FILL))

        link_label = tk.Label(
            win,
            text=REPO_URL,
            font=font_link,
            fg=ACCENT,
            bg=BG,
            cursor="hand2",
        )
        link_label.place(x=W // 2 - 160, y=194, width=320, height=20)
        link_label.bind("<Button-1>", lambda e: webbrowser.open(REPO_URL))
        link_label.bind("<Enter>", lambda e: link_label.configure(fg=BTN_HOVER))
        link_label.bind("<Leave>", lambda e: link_label.configure(fg=ACCENT))

        def _start_drag(event):
            win._drag_x = event.x
            win._drag_y = event.y

        def _do_drag(event):
            dx = event.x - win._drag_x
            dy = event.y - win._drag_y
            win.geometry(f"+{win.winfo_x() + dx}+{win.winfo_y() + dy}")

        canvas.bind("<ButtonPress-1>", _start_drag)
        canvas.bind("<B1-Motion>", _do_drag)

        win.bind("<Escape>", lambda e: win.destroy())
        win.geometry(f"{W}x{H}")
        win.update_idletasks()
        x = (win.winfo_screenwidth() - W) // 2
        y = (win.winfo_screenheight() - H) // 2
        win.geometry(f"+{x}+{y}")
        win.lift()
        win.focus_force()
        win._bg_photo = bg_photo
    except Exception as e:
        logger.error(f"Failed to show about dialog: {e}")


def show_status_dialog(name: str, ip: str, port: str, version: str) -> None:
    _dialog_mgr.show_status(name, ip, port, version)


def show_about_dialog(version: str) -> None:
    _dialog_mgr.show_about(version)
