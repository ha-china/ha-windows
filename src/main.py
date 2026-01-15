"""
Home Assistant Windows Client Main Program

Simulates ESPHome device for Home Assistant integration.
Uses Windows native APIs - no external DLL dependencies required.
"""

import sys
import logging
import asyncio
import argparse
import socket
import threading
from pathlib import Path

# PyInstaller path setup
if getattr(sys, 'frozen', False):
    import os
    src_path = os.path.join(sys._MEIPASS, 'src')
    if src_path not in sys.path:
        sys.path.insert(0, src_path)


def check_dependencies():
    """Check if all required dependencies are available."""
    missing = []
    available = []

    # Check required modules
    modules_to_check = [
        ('aioesphomeapi', 'ESPHome protocol'),
        ('aiohttp', 'HTTP server'),
        ('customtkinter', 'UI framework'),
        ('psutil', 'System monitoring'),
        ('zeroconf', 'mDNS discovery'),
        ('soundcard', 'Audio recording'),
        ('numpy', 'Audio processing'),
    ]

    for module_name, description in modules_to_check:
        try:
            __import__(module_name)
            available.append(f"  OK {module_name} ({description})")
        except ImportError:
            missing.append(f"  X  {module_name} ({description})")

    # Print results
    if available:
        logger.info("Available dependencies:")
        for item in available:
            logger.info(item)

    if missing:
        logger.error("")
        logger.error("Missing dependencies:")
        for item in missing:
            logger.error(item)
        logger.error("")
        logger.error("Please install missing dependencies:")
        logger.error("  pip install -r requirements.txt")
        return False

    logger.info("All dependencies OK!")
    return True

from src.i18n import get_i18n, set_language
from src.core.mdns_discovery import MDNSBroadcaster, DeviceInfo
from src.core.esphome_protocol import ESPHomeServer
from src.ui.system_tray_icon import get_tray
from src.ui.main_window import MainWindow
from src.voice.audio_recorder import AudioRecorder

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('ha_windows.log', encoding='utf-8'),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)


def _get_hostname() -> str:
    """Get local hostname (remove domain part)"""
    try:
        hostname = socket.gethostname()
        return hostname.split('.')[0]
    except Exception:
        return "Windows-PC"


class HomeAssistantWindows:
    """
    Home Assistant Windows Client Main Class

    Features:
    1. Start ESPHome API server (listening on port 6053)
    2. Register mDNS service broadcast (let HA discover device)
    3. Wait for Home Assistant connection
    """

    DEFAULT_PORT = 6053

    def __init__(self, device_name: str = None, port: int = None):
        """
        Initialize client

        Args:
            device_name: Device name (None = use hostname)
            port: API service port
        """
        if device_name is None:
            device_name = _get_hostname()

        self.device_name = device_name
        self.port = port or self.DEFAULT_PORT

        # Components
        self.mdns_broadcaster: MDNSBroadcaster = None
        self.api_server: ESPHomeServer = None
        self.tray = get_tray()
        self.main_window: MainWindow = None
        self._local_ip = None  # Save local IP for tray display
        
        # Wake word detection
        self._wake_word_detector = None
        self._audio_recorder: AudioRecorder = None
        self._wake_word_listening = False
        self._event_loop = None  # Event loop reference for callbacks

        self.running = False

    async def run(self):
        """Run main program"""
        try:
            logger.info("=" * 60)
            logger.info(f"Device: {self.device_name}")
            logger.info(f"Version: 1.0.0")
            logger.info("=" * 60)

            # Step 1: Start ESPHome API server
            await self._start_api_server()

            # Step 2: Register mDNS service broadcast
            await self._register_mdns_service()

            # Step 3: Start wake word detection
            await self._start_wake_word_detection()

            # Step 4: Run main loop
            self.running = True
            await self._main_loop()

        except KeyboardInterrupt:
            logger.info("Interrupted by user, exiting...")
        except Exception as e:
            logger.error(f"Main program error: {e}", exc_info=True)
        finally:
            await self._cleanup()

    async def _start_api_server(self):
        """Start ESPHome API server"""
        logger.info("Starting ESPHome API server...")

        self.api_server = ESPHomeServer(
            host="0.0.0.0",
            port=self.port,
            device_name=self.device_name,
        )

        success = await self.api_server.start()

        if not success:
            raise RuntimeError("Failed to start API server")

        # Run server in background
        asyncio.create_task(self.api_server.serve_forever())

    async def _register_mdns_service(self):
        """Register mDNS service broadcast"""
        logger.info("Registering mDNS service broadcast...")

        device_info = DeviceInfo(
            name=self.device_name,
            version="1.0.0",
            platform="Windows",
            board="PC",
        )

        self.mdns_broadcaster = MDNSBroadcaster(device_info)
        success = await self.mdns_broadcaster.register_service(self.port)

        if not success:
            raise RuntimeError("Failed to register mDNS service")

        # Save local IP for tray display
        self._local_ip = self.mdns_broadcaster._get_local_ip()

        # Set up tray callbacks
        self.tray.set_callbacks(
            on_show_floating=self._show_floating_button,
            on_hide_floating=self._hide_floating_button,
            on_quit=self._request_quit
        )

        # Start system tray icon
        display_name = device_info.name if device_info.name else self.device_name
        self.tray.start(
            name=display_name,
            ip=self._local_ip or "Unknown",
            port=self.port
        )
        
        # Auto-show floating button on startup
        self._show_floating_button()

    def _show_floating_button(self) -> None:
        """Show the floating mic button"""
        logger.info("Showing floating button...")

        if self.main_window is None:
            def create_window():
                try:
                    self.main_window = MainWindow(on_mic_press=self._on_mic_button_press)
                    self.main_window.mainloop()
                except Exception as e:
                    logger.error(f"Failed to create floating button: {e}")
                finally:
                    self.main_window = None

            window_thread = threading.Thread(target=create_window, daemon=True)
            window_thread.start()
        else:
            try:
                self.main_window.show()
            except Exception as e:
                logger.error(f"Failed to show floating button: {e}")

    def _hide_floating_button(self) -> None:
        """Hide the floating mic button"""
        logger.info("Hiding floating button...")
        if self.main_window:
            try:
                self.main_window.hide()
            except Exception as e:
                logger.error(f"Failed to hide floating button: {e}")

    def _on_mic_button_press(self) -> None:
        """Handle microphone button press - trigger voice assistant"""
        logger.info("🎤 Manual voice assistant trigger (push-to-talk)")
        
        # Get the protocol instance
        if self.api_server and self.api_server.protocol:
            protocol = self.api_server.protocol
            # Trigger wakeup (manual trigger, no wake word phrase)
            protocol.wakeup("")
        else:
            logger.warning("No active connection to trigger voice assistant")

    def _on_window_close(self) -> None:
        """Handle window close button - hide instead of destroy"""
        if self.main_window:
            self.main_window.withdraw()  # Hide window instead of destroying

    def _request_quit(self) -> None:
        """Request application quit"""
        logger.info("Quit requested from tray")
        self.running = False
        
        # Force exit (multiple background threads may prevent normal exit)
        import os
        import threading
        
        def force_exit():
            import time
            time.sleep(1)  # Give some time for cleanup to complete
            logger.info("Force exiting...")
            os._exit(0)
        
        threading.Thread(target=force_exit, daemon=True).start()

    async def _start_wake_word_detection(self):
        """Start wake word detection in background"""
        try:
            from src.voice.wake_word import WakeWordDetector
            
            if not WakeWordDetector.is_available():
                logger.warning("Wake word detection not available (pymicro-wakeword not installed)")
                logger.info("Install with: pip install pymicro-wakeword")
                logger.info("Manual trigger via mic button still works")
                return
            
            # List available models
            models = WakeWordDetector.list_available_models()
            if models:
                logger.info(f"Available wake words: {[m[1] for m in models]}")
            
            # Get active wake word from server state
            active_wake_word = self._get_active_wake_word()
            
            # Initialize wake word detector
            self._wake_word_detector = WakeWordDetector(active_wake_word)
            
            # Save the event loop reference for use in callback
            self._event_loop = asyncio.get_running_loop()
            self._last_wakeup_time = 0  # For debouncing
            
            # Set callback
            def on_wake_word(wake_word_phrase: str):
                import time
                now = time.monotonic()
                # Debounce: ignore if triggered within 2 seconds
                if now - self._last_wakeup_time < 2.0:
                    return
                self._last_wakeup_time = now
                
                logger.info(f"🎤 Wake word detected: {wake_word_phrase}")
                if self.api_server and self.api_server.protocol and self._event_loop:
                    try:
                        self._event_loop.call_soon_threadsafe(
                            lambda: self.api_server.protocol.wakeup(wake_word_phrase)
                        )
                    except Exception as e:
                        logger.error(f"Failed to trigger wakeup: {e}")
            
            self._wake_word_detector.on_wake_word(on_wake_word)
            
            # Initialize audio recorder
            self._audio_recorder = AudioRecorder()
            
            # Audio callback for wake word detection
            def on_audio_chunk(audio_data: bytes):
                if not self._wake_word_listening:
                    return
                
                # Check if wake word changed
                if self.api_server and self.api_server.state.wake_words_changed:
                    self.api_server.state.wake_words_changed = False
                    self._update_wake_word_detector()
                
                # Pass raw bytes directly to wake word detector
                if self._wake_word_detector:
                    self._wake_word_detector.process_audio(audio_data)
            
            # Start recording
            self._wake_word_listening = True
            self._audio_recorder.start_recording(audio_callback=on_audio_chunk)
            
            wake_phrase = self._wake_word_detector.wake_word_phrase
            logger.info(f"🎤 Wake word detection started (say '{wake_phrase}')")
            
        except ImportError as e:
            logger.warning(f"Wake word detection not available: {e}")
            logger.info("Manual trigger via mic button still works")
        except Exception as e:
            logger.error(f"Failed to start wake word detection: {e}")

    def _get_active_wake_word(self) -> str:
        """Get the first active wake word from server state"""
        if self.api_server and self.api_server.state.active_wake_words:
            return next(iter(self.api_server.state.active_wake_words))
        return 'okay_nabu'  # Default

    def _update_wake_word_detector(self):
        """Update wake word detector when active wake word changes"""
        from src.voice.wake_word import WakeWordDetector
        
        new_wake_word = self._get_active_wake_word()
        
        if self._wake_word_detector and self._wake_word_detector.model_name == new_wake_word:
            return  # No change
        
        logger.info(f"🔄 Switching wake word to: {new_wake_word}")
        
        # Save callback
        old_callback = self._wake_word_detector._on_wake_word if self._wake_word_detector else None
        
        # Create new detector
        self._wake_word_detector = WakeWordDetector(new_wake_word)
        
        # Restore callback
        if old_callback:
            self._wake_word_detector.on_wake_word(old_callback)
        
        wake_phrase = self._wake_word_detector.wake_word_phrase
        logger.info(f"🎤 Now listening for: '{wake_phrase}'")

    def _stop_wake_word_detection(self):
        """Stop wake word detection"""
        self._wake_word_listening = False
        if self._audio_recorder:
            try:
                self._audio_recorder.stop_recording()
            except Exception as e:
                logger.error(f"Failed to stop audio recorder: {e}")
            self._audio_recorder = None
        self._wake_word_detector = None

    async def _main_loop(self):
        """Main loop"""
        logger.info("")
        logger.info("Device started and broadcasting on network!")
        logger.info("")
        logger.info("In Home Assistant:")
        logger.info("  1. Settings > Devices & Services > Add Integration")
        logger.info("  2. Search 'ESPHome' or add manually")
        logger.info("  3. Device should be discovered")
        logger.info("")
        logger.info("Press Ctrl+C to exit...")
        logger.info("")

        # Keep running
        while self.running:
            await asyncio.sleep(1)

    async def _cleanup(self):
        """Cleanup resources"""
        logger.info("Cleaning up resources...")

        self.running = False

        # Stop wake word detection
        self._stop_wake_word_detection()

        # Close main window
        if self.main_window:
            try:
                self.main_window.destroy()
                self.main_window = None
            except Exception as e:
                logger.error(f"Failed to close main window: {e}")

        # Stop system tray icon
        try:
            self.tray.stop()
        except Exception as e:
            logger.error(f"Failed to stop tray icon: {e}")

        # Unregister mDNS service
        if self.mdns_broadcaster:
            try:
                await self.mdns_broadcaster.unregister_service()
            except Exception as e:
                logger.error(f"Failed to unregister mDNS service: {e}")

        # Stop API server
        if self.api_server:
            try:
                await self.api_server.stop()
            except Exception as e:
                logger.error(f"Failed to stop API server: {e}")
        
        logger.info("Cleanup complete, exiting...")
        
        # Force exit process (ensure all background threads are terminated)
        import os
        os._exit(0)


def main():
    """Main function"""
    # Parse command line arguments
    parser = argparse.ArgumentParser(
        description="Home Assistant Windows Client - ESPHome Device Simulator"
    )
    parser.add_argument(
        '--name',
        default=None,
        help='Device name (default: hostname)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=6053,
        help='API service port (default: 6053)'
    )
    parser.add_argument(
        '--language',
        choices=['zh_CN', 'en_US'],
        default='en_US',
        help='Interface language'
    )
    parser.add_argument(
        '--debug',
        action='store_true',
        help='Enable debug mode'
    )

    args = parser.parse_args()

    # Set language
    set_language(args.language)

    # Set log level
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    # Check dependencies
    logger.info("Checking dependencies...")
    if not check_dependencies():
        logger.error("Dependency check failed. Please install missing dependencies.")
        sys.exit(1)

    # Create and run client
    client = HomeAssistantWindows(
        device_name=args.name,
        port=args.port,
    )

    # Run async main program
    try:
        asyncio.run(client.run())
    except KeyboardInterrupt:
        logger.info("Program exited")
        sys.exit(0)


if __name__ == "__main__":
    main()
