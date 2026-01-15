"""
Main Window UI Module
Build modern interface using CustomTkinter
"""

import asyncio
import logging
import threading
import tkinter as tk
from enum import Enum
from typing import Optional

import customtkinter as ctk

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class ConnectionState(Enum):
    """Connection state enumeration"""
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    ERROR = 3


class MainWindow(ctk.CTk):
    """Main window"""

    def __init__(self, on_mic_click=None):
        """
        Initialize main window
        
        Args:
            on_mic_click: Callback when microphone button is clicked
        """
        super().__init__()

        # Configure window
        self.title(_i18n.t('app_name'))
        self.geometry("800x600")

        # Set theme
        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        # State
        self.connection_state = ConnectionState.DISCONNECTED
        self._on_mic_click = on_mic_click

        # Create UI
        self._create_widgets()

        # Start async event loop
        self._async_loop = asyncio.new_event_loop()
        self._loop_thread = threading.Thread(
            target=self._run_async_loop,
            daemon=True
        )
        self._loop_thread.start()

        logger.info("Main window created")

    def _run_async_loop(self):
        """Run async event loop (in separate thread)"""
        asyncio.set_event_loop(self._async_loop)
        self._async_loop.run_forever()

    def _create_widgets(self):
        """Create UI components"""
        # Top title bar
        title_frame = ctk.CTkFrame(self, height=60)
        title_frame.pack(side="top", fill="x", padx=10, pady=10)

        title_label = ctk.CTkLabel(
            title_frame,
            text=_i18n.t('app_name'),
            font=ctk.CTkFont(size=24, weight="bold")
        )
        title_label.pack(side="left", padx=20)

        # Status indicator
        self.status_label = ctk.CTkLabel(
            title_frame,
            text=f"{_i18n.t('status_label')}: {_i18n.t('status_disconnected')}",
            font=ctk.CTkFont(size=12)
        )
        self.status_label.pack(side="right", padx=20)

        # Main content area
        main_frame = ctk.CTkFrame(self)
        main_frame.pack(side="top", fill="both", expand=True, padx=10, pady=10)

        # Microphone button (large button)
        mic_frame = ctk.CTkFrame(main_frame)
        mic_frame.pack(side="top", fill="x", pady=20)

        self.mic_button = ctk.CTkButton(
            mic_frame,
            text="🎤",
            font=ctk.CTkFont(size=48),
            width=150,
            height=150,
            fg_color=("gray75", "gray30"),
            hover_color=("gray65", "gray25"),
            command=self._on_mic_button_click
        )
        self.mic_button.pack()

        # Control panel
        control_frame = ctk.CTkFrame(main_frame)
        control_frame.pack(side="top", fill="x", pady=20)

        # Volume slider
        volume_label = ctk.CTkLabel(
            control_frame,
            text=_i18n.t('volume'),
            font=ctk.CTkFont(size=14)
        )
        volume_label.pack(side="left", padx=20)

        self.volume_slider = ctk.CTkSlider(
            control_frame,
            from_=0,
            to=100,
            number_of_steps=100,
            width=300
        )
        self.volume_slider.set(50)
        self.volume_slider.pack(side="left", padx=10)

        self.volume_label = ctk.CTkLabel(
            control_frame,
            text="50%",
            font=ctk.CTkFont(size=12)
        )
        self.volume_label.pack(side="left", padx=10)

        # Settings button
        settings_button = ctk.CTkButton(
            control_frame,
            text="⚙️",
            width=50,
            command=self._on_settings_click
        )
        settings_button.pack(side="right", padx=10)

        # Bottom info bar
        info_frame = ctk.CTkFrame(main_frame)
        info_frame.pack(side="bottom", fill="x", pady=10)

        self.info_label = ctk.CTkLabel(
            info_frame,
            text=_i18n.t('ready'),
            font=ctk.CTkFont(size=12)
        )
        self.info_label.pack(side="left", padx=20)

    def _on_mic_button_click(self):
        """Microphone button click event"""
        logger.info("🎤 Microphone button clicked")
        self.info_label.configure(text=_i18n.t('listening'))
        
        # Change button color to indicate listening
        self.mic_button.configure(fg_color=("red", "darkred"))

        # Trigger Voice Assistant callback
        if self._on_mic_click:
            try:
                self._on_mic_click()
            except Exception as e:
                logger.error(f"Mic click callback error: {e}")
                self.info_label.configure(text=f"Error: {e}")
                self.mic_button.configure(fg_color=("gray75", "gray30"))
        
    def set_mic_callback(self, callback):
        """Set microphone button callback"""
        self._on_mic_click = callback
        
    def set_listening_state(self, is_listening: bool):
        """Update UI to show listening state"""
        if is_listening:
            self.mic_button.configure(fg_color=("red", "darkred"))
            self.info_label.configure(text=_i18n.t('listening'))
        else:
            self.mic_button.configure(fg_color=("gray75", "gray30"))
            self.info_label.configure(text=_i18n.t('ready'))

    def _on_settings_click(self):
        """Settings button click event"""
        logger.info("Settings button clicked")

        # TODO: Open settings window

    def update_connection_state(self, state: ConnectionState):
        """
        Update connection state

        Args:
            state: Connection state
        """
        self.connection_state = state

        if state == ConnectionState.CONNECTED:
            status_text = _i18n.t('status_connected')
            color = "green"
        elif state == ConnectionState.DISCONNECTED:
            status_text = _i18n.t('status_disconnected')
            color = "red"
        elif state == ConnectionState.CONNECTING:
            status_text = _i18n.t('status_connecting')
            color = "yellow"
        else:
            status_text = _i18n.t('status_error')
            color = "red"

        self.status_label.configure(text=f"{_i18n.t('status_label')}: {status_text}")

    def update_info(self, message: str):
        """
        Update info bar

        Args:
            message: Info text
        """
        self.info_label.configure(text=message)


class AsyncMainWindow:
    """Async main window wrapper"""

    def __init__(self):
        """Initialize async main window"""
        self.window: Optional[MainWindow] = None
        self._running = False

    def start(self):
        """Start window"""
        self.window = MainWindow()
        self._running = True
        self.window.mainloop()

    def stop(self):
        """Stop window"""
        if self.window:
            self.window.destroy()
        self._running = False

    def update_connection_state(self, state: ConnectionState):
        """Update connection state"""
        if self.window:
            self.window.update_connection_state(state)

    def update_info(self, message: str):
        """Update info"""
        if self.window:
            self.window.update_info(message)


# Convenience function
def create_main_window() -> AsyncMainWindow:
    """
    Create main window (convenience function)

    Returns:
        AsyncMainWindow: Main window instance
    """
    return AsyncMainWindow()


if __name__ == "__main__":
    # Test UI
    logging.basicConfig(level=logging.INFO)

    def test_ui():
        """Test UI"""
        logger.info("Testing main window UI")

        window = create_main_window()
        window.start()

    # Run test
    test_ui()
