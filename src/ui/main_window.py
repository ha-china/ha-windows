"""
Floating Microphone Button Module
A floating button for voice assistant activation
Press and hold to talk, release to stop.
"""

import logging
from pathlib import Path
from typing import Optional, Callable
import tkinter as tk

from PIL import Image, ImageTk, ImageDraw

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()

# Mic icon path
MIC_ICON_PATH = Path(__file__).parent.parent / "voice" / "mic.png"


class FloatingMicButton(tk.Tk):
    """Floating microphone button (push-to-talk)"""

    def __init__(self, on_mic_press: Optional[Callable] = None, on_mic_release: Optional[Callable] = None):
        super().__init__()

        self._button_size = 70

        # Calculate position (bottom-right, above taskbar)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        margin = 20
        taskbar_height = 50

        x = screen_width - self._button_size - margin
        y = screen_height - self._button_size - margin - taskbar_height

        # Window setup
        self.title("")
        self.geometry(f"{self._button_size}x{self._button_size}+{x}+{y}")
        self.resizable(False, False)
        self.overrideredirect(True)
        self.wm_attributes("-topmost", True)
        self.wm_attributes("-toolwindow", True)
        self.wm_attributes("-alpha", 0.9)

        # Dark background
        self.config(bg="#1a1a1a")

        # State
        self._on_mic_press = on_mic_press
        self._on_mic_release = on_mic_release
        self._is_listening = False
        self._is_pressed = False
        self._is_dragging = False
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_threshold = 15

        # Load icons
        self._mic_photo = None
        self._mic_photo_active = None
        self._load_icons()

        # Create UI
        self._create_widgets()

        logger.info("Floating mic button created")

    def _load_icons(self):
        """Load mic icons with circular dark background"""
        try:
            size = self._button_size
            bg_color = (26, 26, 26, 255)  # #1a1a1a
            bg_color_active = (139, 0, 0, 255)  # Dark red

            if MIC_ICON_PATH.exists():
                # Load icon
                icon = Image.open(MIC_ICON_PATH).convert("RGBA")
                icon_size = int(size * 0.7)
                icon = icon.resize((icon_size, icon_size), Image.Resampling.LANCZOS)

                # Create circular background - normal
                bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                draw = ImageDraw.Draw(bg)
                draw.ellipse([0, 0, size - 1, size - 1], fill=bg_color)

                # Paste icon centered
                offset = (size - icon_size) // 2
                bg.paste(icon, (offset, offset), icon)
                self._mic_photo = ImageTk.PhotoImage(bg)

                # Create circular background - active (red)
                bg_active = Image.new("RGBA", (size, size), (0, 0, 0, 0))
                draw_active = ImageDraw.Draw(bg_active)
                draw_active.ellipse([0, 0, size - 1, size - 1], fill=bg_color_active)
                bg_active.paste(icon, (offset, offset), icon)
                self._mic_photo_active = ImageTk.PhotoImage(bg_active)

                logger.info(f"Loaded mic icon: {MIC_ICON_PATH}")
            else:
                logger.warning(f"Mic icon not found: {MIC_ICON_PATH}")
                self._create_fallback_icons()
        except Exception as e:
            logger.error(f"Failed to load mic icon: {e}")
            self._create_fallback_icons()

    def _create_fallback_icons(self):
        """Create fallback icons without external file"""
        size = self._button_size

        # Normal - dark circle
        bg = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(bg)
        draw.ellipse([0, 0, size - 1, size - 1], fill=(26, 26, 26, 255))
        self._mic_photo = ImageTk.PhotoImage(bg)

        # Active - red circle
        bg_active = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw_active = ImageDraw.Draw(bg_active)
        draw_active.ellipse([0, 0, size - 1, size - 1], fill=(139, 0, 0, 255))
        self._mic_photo_active = ImageTk.PhotoImage(bg_active)

    def _create_widgets(self):
        """Create UI"""
        self.label = tk.Label(
            self,
            image=self._mic_photo,
            bg="#1a1a1a",
            bd=0,
            highlightthickness=0
        )
        self.label.pack(fill="both", expand=True)

        # Bind events
        self.label.bind("<ButtonPress-1>", self._on_button_press)
        self.label.bind("<ButtonRelease-1>", self._on_button_release)
        self.label.bind("<B1-Motion>", self._on_drag_motion)
        self.label.bind("<Enter>", self._on_enter)
        self.label.bind("<Leave>", self._on_leave)

    def _on_enter(self, event):
        """Mouse enter - full opacity"""
        if not self._is_listening:
            self.wm_attributes("-alpha", 1.0)

    def _on_leave(self, event):
        """Mouse leave - slight transparency"""
        if not self._is_listening and not self._is_pressed:
            self.wm_attributes("-alpha", 0.7)

    def _on_button_press(self, event):
        """Button pressed"""
        self._drag_start_x = event.x_root
        self._drag_start_y = event.y_root
        self._is_dragging = False
        self._is_pressed = True

        logger.info("Mic pressed - start listening")
        self.set_listening_state(True)

        if self._on_mic_press:
            try:
                self._on_mic_press()
            except Exception as e:
                logger.error(f"Mic press error: {e}")

    def _on_button_release(self, event):
        """Button released"""
        self._is_pressed = False

        if self._is_dragging:
            self._is_dragging = False
            self.set_listening_state(False)
            return

        logger.info("Mic released - stop listening")
        self.set_listening_state(False)

        if self._on_mic_release:
            try:
                self._on_mic_release()
            except Exception as e:
                logger.error(f"Mic release error: {e}")

    def _on_drag_motion(self, event):
        """Handle drag"""
        dx = abs(event.x_root - self._drag_start_x)
        dy = abs(event.y_root - self._drag_start_y)

        if dx > self._drag_threshold or dy > self._drag_threshold:
            self._is_dragging = True
            if self._is_listening:
                self.set_listening_state(False)

            x = self.winfo_x() + (event.x_root - self._drag_start_x)
            y = self.winfo_y() + (event.y_root - self._drag_start_y)
            self.geometry(f"+{x}+{y}")
            self._drag_start_x = event.x_root
            self._drag_start_y = event.y_root

    def set_mic_callback(self, callback: Callable):
        """Set callback (backward compatibility)"""
        self._on_mic_press = callback

    def set_callbacks(self, on_press: Callable = None, on_release: Callable = None):
        """Set callbacks"""
        if on_press:
            self._on_mic_press = on_press
        if on_release:
            self._on_mic_release = on_release

    def set_listening_state(self, is_listening: bool):
        """Update listening state"""
        self._is_listening = is_listening
        if self._mic_photo and self._mic_photo_active:
            self.label.config(image=self._mic_photo_active if is_listening else self._mic_photo)
        self.wm_attributes("-alpha", 1.0 if is_listening else 0.7)

    def show(self):
        self.deiconify()

    def hide(self):
        self.withdraw()


# Alias
MainWindow = FloatingMicButton


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    def on_press():
        print("Listening...")

    def on_release():
        print("Stopped.")

    button = FloatingMicButton(on_mic_press=on_press, on_mic_release=on_release)
    button.mainloop()
