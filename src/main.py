"""
Home Assistant Windows Client Main Program

Simulates ESPHome device for Home Assistant integration.
Uses Windows native APIs - no external DLL dependencies required.
"""

from src import __version__
from src.i18n import set_language
from src.voice.audio_recorder import AudioRecorder
from src.ui.system_tray_icon import get_tray
from src.core.esphome_protocol import ESPHomeServer
from src.core.mdns_discovery import MDNSBroadcaster, DeviceInfo
import sys
import logging
import asyncio
import argparse
import socket
import threading
import platform

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
        ('sounddevice', 'Audio recording'),
        ('psutil', 'System monitoring'),
        ('zeroconf', 'mDNS discovery'),
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


# Configure logging
# Use user directory for log file to avoid permission issues in Program Files
import os


def _get_log_dir() -> str:
    """Log directory (same location as the app data dir)."""
    from src.core.models import get_user_data_dir
    return str(get_user_data_dir())


class SizeLimitedFileHandler(logging.FileHandler):
    """Keep a single log file capped at a fixed size."""

    def __init__(self, filename: str, max_bytes: int, **kwargs):
        self.max_bytes = max_bytes
        super().__init__(filename, **kwargs)

    def emit(self, record):
        if self.stream is None:
            self.stream = self._open()

        if self.max_bytes > 0:
            try:
                self.stream.seek(0, os.SEEK_END)
                if self.stream.tell() >= self.max_bytes:
                    self.stream.close()
                    self.mode = 'w'
                    self.stream = self._open()
                    self.mode = 'a'
            except Exception:
                self.handleError(record)
                return

        super().emit(record)


log_dir = _get_log_dir()
os.makedirs(log_dir, exist_ok=True)
log_file = os.path.join(log_dir, 'ha_windows.log')
log_max_bytes = 5 * 1024 * 1024

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        SizeLimitedFileHandler(
            log_file,
            max_bytes=log_max_bytes,
            encoding='utf-8',
        ),
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
        return "HA-Client"


class HomeAssistantWindows:
    """
    Home Assistant Windows Client Main Class

    Features:
    1. Start ESPHome API server (listening on port 6053)
    2. Register mDNS service broadcast (let HA discover device)
    3. Wait for Home Assistant connection
    """

    DEFAULT_PORT = 6053
    MDNS_RESTART_INTERVAL_SECONDS = 6 * 60 * 60

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
        self.tray = None
        self._local_ip = None  # Save local IP for tray display

        # Wake word detection
        self._wake_word_detectors = {}
        self._stop_word_detector = None
        self._wake_word_callback = None
        self._audio_recorder: AudioRecorder = None
        self._audio_callback = None
        self._wake_word_listening = False
        self._event_loop = None  # Event loop reference for callbacks
        self._mdns_refresh_task: asyncio.Task | None = None
        self._server_task: asyncio.Task | None = None
        self.sendspin = None  # SendspinReceiver instance

        self.running = False
        self._cleanup_done = threading.Event()
        self._last_wakeup_time = 0.0  # wake-word debounce

    async def run(self):
        """Run main program"""
        try:
            logger.info("=" * 60)
            logger.info(f"Device: {self.device_name}")
            logger.info(f"Version: {__version__}")
            logger.info("=" * 60)

            # Step 1: Start ESPHome API server
            await self._start_api_server()

            # Step 2: Register mDNS service broadcast
            await self._register_mdns_service()

            # Step 3: Start wake word detection
            await self._start_wake_word_detection()

            # Step 3.5: Start Sendspin audio receiver
            await self._start_sendspin()

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

        # Create system tray icon after server is initialized
        self.tray = get_tray(state=self.api_server.state)

        # Connect voice assistant phase changes to tray icon updates
        self.api_server.set_phase_callback(self.tray.set_phase)

        # Wire microphone mute and conversation callbacks to the server
        self.api_server.set_muted_callback(self._set_muted)
        self.api_server.set_conversation_callback(self._on_conversation_text)

        # Run server in background
        # Keep a reference: tasks are only weakly referenced by the loop and
        # could otherwise be garbage-collected mid-flight.
        self._server_task = asyncio.create_task(self.api_server.serve_forever())

    def _set_microphone(self, device_name: str) -> None:
        """Switch the recording microphone ("" = system default) and persist it."""
        state = self.api_server.state
        state.preferences.mic_device = device_name
        state.save_preferences()

        if not self._audio_recorder:
            return

        was_recording = self._audio_recorder.is_recording
        self._audio_recorder.stop_recording()
        self._audio_recorder.device = device_name or None
        if was_recording:
            self._audio_recorder.start_recording(audio_callback=self._audio_callback)
        logger.info(f"🎤 Microphone set to: {device_name or 'system default'}")

    def _set_muted(self, muted: bool) -> None:
        """Set microphone mute state and persist it (called by protocol callback)."""
        state = self.api_server.state
        state.preferences.muted = muted
        state.save_preferences()

        if self._audio_recorder:
            self._audio_recorder.muted = muted
            logger.info(f"🎤 Microphone {'muted' if muted else 'unmuted'}")

        # Refresh the tray menu so the checkmark reflects the current state
        if self.tray:
            self.tray.refresh_menu()

    def _on_tray_mute_toggle(self, muted: bool) -> None:
        """Handle mute toggle from tray, syncing to HA if connected."""
        if self.api_server and self.api_server.protocol:
            self.api_server.protocol._set_muted_and_push(muted)
        else:
            self._set_muted(muted)

    def _on_tray_bubble_toggle(self, enabled: bool) -> None:
        """Handle conversation bubble toggle from tray."""
        from src.ui import conversation_bubble

        state = self.api_server.state
        state.preferences.conversation_bubble_enabled = enabled
        state.save_preferences()
        conversation_bubble.set_enabled(enabled)
        logger.info(f"💬 Conversation bubbles {'enabled' if enabled else 'disabled'}")

    def _on_conversation_text(self, msg_type: str, text: str) -> None:
        """Handle conversation text from voice assistant events."""
        if self.tray:
            try:
                self.tray._show_conversation_balloon(msg_type, text)
            except Exception as e:
                logger.debug(f"Conversation balloon error: {e}")

    # ------------------------------------------------------------------ Sendspin

    async def _start_sendspin(self) -> None:
        """Start the Sendspin audio receiver (Music Assistant streams music to us)."""
        if not getattr(self.api_server.state.preferences, 'sendspin_enabled', True):
            logger.info("Sendspin player disabled by preference, skipping")
            return

        try:
            from src.sendspin_player import SendspinReceiver

            self.sendspin = SendspinReceiver(name=self.device_name)
            self.sendspin.set_metadata_callback(self._on_sendspin_metadata)
            self.sendspin.set_connection_callback(self._on_sendspin_connection)
            self.sendspin.set_state_callback(self._on_sendspin_state)
            self.sendspin.set_artwork_callback(self._on_sendspin_artwork)
            self.sendspin.set_volume_callback(self._on_sendspin_volume)
            self.sendspin.set_sync_callback(self._on_sendspin_sync)
            await self.sendspin.start()
            if self.tray:
                self.tray.set_sendspin_status(self.sendspin.is_connected)
        except ImportError as e:
            logger.warning(f"Sendspin not available (pip install aiosendspin): {e}")
            self.sendspin = None
        except Exception as e:
            logger.error(f"Failed to start Sendspin receiver: {e}")
            self.sendspin = None

    async def _stop_sendspin(self) -> None:
        if self.sendspin:
            try:
                await self.sendspin.stop()
            except Exception as e:
                logger.error(f"Failed to stop Sendspin receiver: {e}")
            self.sendspin = None

    def _run_on_loop(self, coro) -> None:
        """Schedule a coroutine on the event loop from any thread (tray etc.)."""
        loop = self._event_loop
        if loop is None or loop.is_closed():
            logger.warning("Event loop not available, dropping coroutine")
            return
        asyncio.run_coroutine_threadsafe(coro, loop)

    def _on_tray_sendspin_toggle(self, enabled: bool) -> None:
        """Handle Sendspin enable/disable toggle from tray."""
        state = self.api_server.state
        state.preferences.sendspin_enabled = enabled
        state.save_preferences()

        if enabled and self.sendspin is None:
            self._run_on_loop(self._start_sendspin())
        elif not enabled and self.sendspin is not None:
            self._run_on_loop(self._stop_sendspin())
        logger.info(f"🔊 Sendspin player {'enabled' if enabled else 'disabled'}")

    def _on_sendspin_metadata(self, info: dict) -> None:
        """Handle track metadata/progress updates from the Sendspin stream."""
        try:
            from src.ui import mini_player
            title = info.get("title")
            artist = info.get("artist")
            if title is not None or artist is not None:
                logger.info(f"🎵 Now playing: {title} - {artist}")
                mini_player.update_track(
                    title or "", artist or "", info.get("duration_ms", 0)
                )
            elif "duration_ms" in info:
                mini_player.update_duration(info.get("duration_ms", 0))
            if "progress_ms" in info:
                mini_player.update_progress(
                    info.get("progress_ms", 0), info.get("speed", 0.0)
                )
        except Exception as e:
            logger.debug(f"Mini player track update failed: {e}")

    def _on_sendspin_artwork(self, data: bytes) -> None:
        """Handle album artwork frames from the Sendspin stream."""
        try:
            from src.ui import mini_player
            mini_player.set_artwork(data)
        except Exception as e:
            logger.debug(f"Mini player artwork update failed: {e}")

    def _on_sendspin_volume(self, volume: int, muted: bool) -> None:
        """Keep the mini player slider and mute icon in sync."""
        try:
            from src.ui import mini_player
            mini_player.set_volume(volume)
            mini_player.set_muted(muted)
        except Exception as e:
            logger.debug(f"Mini player volume update failed: {e}")

    def _on_sendspin_sync(self, offset_ms: int, synchronized: bool) -> None:
        """Forward the Sendspin playback clock skew to the mini player."""
        try:
            from src.ui import mini_player
            mini_player.set_sync(offset_ms, synchronized)
        except Exception as e:
            logger.debug(f"Mini player sync update failed: {e}")

    def _on_sendspin_state(self, playing: bool) -> None:
        """Handle Sendspin playback state changes."""
        logger.info(f"🎵 Sendspin playing: {playing}")
        try:
            from src.ui import mini_player
            if playing:
                mini_player.show()
                if self.sendspin:
                    mini_player.set_volume(self.sendspin.volume_percent)
            mini_player.set_playing(playing)
        except Exception as e:
            logger.debug(f"Mini player state update failed: {e}")

    def _on_sendspin_connection(self, connected: bool) -> None:
        """Handle Sendspin connection state changes (may run on any thread)."""
        if self.tray:
            try:
                self.tray.set_sendspin_status(connected)
            except Exception as e:
                logger.debug(f"Sendspin status update error: {e}")
        if not connected:
            try:
                from src.ui import mini_player
                mini_player.hide()
            except Exception:
                pass

    def _on_mini_player_command(self, cmd: str) -> None:
        """Forward a mini player button press upstream to Music Assistant."""
        from aiosendspin.models.types import MediaCommand

        mapping = {
            "previous": MediaCommand.PREVIOUS,
            "next": MediaCommand.NEXT,
            "stop": MediaCommand.STOP,
        }
        mute_value = None
        try:
            if cmd == "play_pause":
                command = MediaCommand.PAUSE if (self.sendspin and self.sendspin.is_playing()) else MediaCommand.PLAY
            elif cmd == "mute":
                command = MediaCommand.MUTE
                mute_value = not (self.sendspin.muted if self.sendspin else False)
                if self.sendspin:
                    self.sendspin.apply_local_mute(mute_value)
            else:
                command = mapping.get(cmd)
            if command is None or self.sendspin is None:
                return
            loop = self._event_loop
            if loop is None or loop.is_closed():
                return
            asyncio.run_coroutine_threadsafe(
                self.sendspin.send_media_command(command, mute=mute_value), loop
            )
            # Optimistic UI update: MA's authoritative state only arrives with
            # the next metadata push (seconds away, or never while paused).
            if cmd == "play_pause":
                self.sendspin.set_local_playing(command == MediaCommand.PLAY)
            elif cmd == "stop":
                self.sendspin.set_local_playing(False)
        except Exception as e:
            logger.error(f"Mini player command failed: {e}")

    def _on_mini_player_volume(self, volume: int) -> None:
        """Apply music volume locally (software gain) and sync upstream."""
        from aiosendspin.models.types import MediaCommand

        try:
            if self.sendspin is None:
                return
            self.sendspin.apply_local_volume(volume)
            loop = self._event_loop
            if loop is None or loop.is_closed():
                return
            asyncio.run_coroutine_threadsafe(
                self.sendspin.send_media_command(MediaCommand.VOLUME, volume=volume), loop
            )
        except Exception as e:
            logger.error(f"Mini player volume failed: {e}")

    def _on_mini_player_closed(self) -> None:
        """✕ on the mini player: remember the choice so it stays hidden."""
        logger.info("Mini player closed by user, remembering")
        state = self.api_server.state
        state.preferences.mini_player_enabled = False
        state.save_preferences()
        from src.ui import mini_player
        mini_player.set_enabled(False)
        if self.tray:
            try:
                self.tray.refresh_menu()
            except Exception:
                pass

    def _on_tray_mini_player_toggle(self, enabled: bool) -> None:
        """Handle mini player enable/disable toggle from tray."""
        logger.info(f"Mini player toggled: {enabled}")
        state = self.api_server.state
        state.preferences.mini_player_enabled = enabled
        state.save_preferences()
        from src.ui import mini_player
        mini_player.set_enabled(enabled)
        if enabled and self.sendspin and self.sendspin.is_playing():
            mini_player.show()

    async def _register_mdns_service(self):
        """Register mDNS service broadcast"""
        logger.info("Registering mDNS service broadcast...")

        device_info = DeviceInfo(
            name=self.device_name,
            version=__version__,
            platform=platform.system(),
            board="PC",
        )

        self.mdns_broadcaster = MDNSBroadcaster(device_info)
        success = await self.mdns_broadcaster.register_service(self.port)

        if not success:
            raise RuntimeError("Failed to register mDNS service")

        # Save local IP for tray display
        self._local_ip = self.mdns_broadcaster._get_local_ip()

        # Set up tray callbacks
        self.tray.set_version(__version__)
        self.tray.set_callbacks(
            on_quit=self._request_quit,
            on_mic_change=self._set_microphone,
            on_mute_change=self._on_tray_mute_toggle,
            on_bubble_toggle=self._on_tray_bubble_toggle,
            on_sendspin_toggle=self._on_tray_sendspin_toggle,
            on_run_as_admin=self._relaunch_as_admin,
            on_mini_player_toggle=self._on_tray_mini_player_toggle,
        )

        # Apply saved mini player preference and wire its handlers
        from src.ui import mini_player
        mini_player.set_enabled(getattr(self.api_server.state.preferences, 'mini_player_enabled', True))
        mini_player.set_command_handler(self._on_mini_player_command)
        mini_player.set_volume_handler(self._on_mini_player_volume)
        mini_player.set_close_handler(self._on_mini_player_closed)

        # Apply saved conversation bubble preference
        from src.ui import conversation_bubble
        conversation_bubble.set_enabled(
            self.api_server.state.preferences.conversation_bubble_enabled
        )

        # Start system tray icon
        display_name = device_info.name if device_info.name else self.device_name
        self.tray.start(
            name=display_name,
            ip=self._local_ip or "Unknown",
            port=self.port
        )

        self._mdns_refresh_task = asyncio.create_task(self._refresh_mdns_periodically())

    async def _refresh_mdns_periodically(self) -> None:
        """Periodically recreate AsyncZeroconf to avoid long-lived cache growth."""
        try:
            while True:
                await asyncio.sleep(self.MDNS_RESTART_INTERVAL_SECONDS)
                if not self.running or not self.mdns_broadcaster:
                    return

                logger.info("Refreshing mDNS broadcaster to release cached zeroconf state")
                success = await self.mdns_broadcaster.restart_service(self.port)
                if not success:
                    logger.warning("Failed to refresh mDNS broadcaster")
        except asyncio.CancelledError:
            return
        except Exception as e:
            logger.error(f"mDNS refresh loop failed: {e}")

    def _request_quit(self) -> None:
        """Request application quit"""
        logger.info("Quit requested from tray")
        self.running = False

        # Watchdog: normally _cleanup finishes and exits by itself; this only
        # fires if cleanup hangs, giving it a generous grace period first.
        import os
        import threading

        def force_exit():
            if not self._cleanup_done.wait(timeout=8):
                logger.info("Cleanup did not finish in time, force exiting...")
                os._exit(0)

        threading.Thread(target=force_exit, daemon=True).start()

    def _relaunch_as_admin(self) -> None:
        """Relaunch the current executable elevated (ShellExecute runas)."""
        import ctypes
        import os
        import sys

        try:
            exe = sys.executable
            # Rebuild the current command line (name/port/language/debug)
            args = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else ""

            # ShellExecuteW verb "runas" triggers the UAC prompt.
            result = ctypes.windll.shell32.ShellExecuteW(None, "runas", exe, args, None, 1)
            if result <= 32:
                logger.error(f"Failed to relaunch as administrator (code {result})")
                return
            logger.info("Relaunching as administrator...")
            # Let the elevated instance take over the tray, then exit.
            self._request_quit()
        except Exception as e:
            logger.error(f"Failed to relaunch as administrator: {e}")

    async def _start_wake_word_detection(self):
        """Start voice recording and, if available, wake word detection."""
        # The audio recorder is always created/started (used for voice input too).
        self._audio_recorder = AudioRecorder(
            self.api_server.state.preferences.mic_device or None
        )
        self._audio_recorder.muted = self.api_server.state.preferences.muted

        # Audio callback for wake word detection
        def on_audio_chunk(audio_data: bytes):
            if not self._wake_word_listening:
                return

            # Always send audio to voice assistant (handle_audio will check _is_streaming_audio internally)
            if self.api_server and self.api_server.protocol:
                self.api_server.protocol.handle_audio(audio_data)

            # Check if wake word changed
            if self.api_server and self.api_server.state.wake_words_changed:
                self.api_server.state.wake_words_changed = False
                self._update_wake_word_detector()

            # Skip wake word detection if TTS is playing (to avoid false positives)
            if self.api_server and self.api_server.protocol and not self.api_server.protocol.is_playing_tts:
                for detector in self._wake_word_detectors.values():
                    detector.process_audio(audio_data)

            if self._stop_word_detector and self.api_server:
                stop_word = self.api_server.state.stop_word
                stop_is_active = stop_word is not None and stop_word.id in self.api_server.state.active_wake_words
                if stop_is_active and self._stop_word_detector.process_audio(audio_data):
                    self.api_server.protocol.stop()

        # Start recording
        self._wake_word_listening = True
        self._audio_callback = on_audio_chunk
        self._audio_recorder.start_recording(audio_callback=on_audio_chunk)

        # Wake word detection is optional
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

            # Initialize wake word detectors from active server state
            self._update_wake_word_detector(initial_setup=True)

            # Initialize stop word detector
            self._stop_word_detector = WakeWordDetector('stop')

            # Save the event loop reference for use in callback
            self._event_loop = asyncio.get_running_loop()

            # Set callback
            def on_wake_word(wake_word_phrase: str):
                import time
                now = time.monotonic()
                # Debounce: ignore if triggered within 2 seconds
                if now - self._last_wakeup_time < 2.0:
                    return
                self._last_wakeup_time = now

                logger.info(f"🎤 Wake word detected: {wake_word_phrase}")
                if self.api_server and self.api_server.protocol:
                    try:
                        self.api_server.protocol.wakeup(wake_word_phrase)
                    except Exception as e:
                        logger.error(f"Failed to trigger wakeup: {e}")

            self._wake_word_callback = on_wake_word
            for detector in self._wake_word_detectors.values():
                detector.on_wake_word(on_wake_word)

            wake_phrases = [det.wake_word_phrase for det in self._wake_word_detectors.values()]
            if wake_phrases:
                logger.info(f"🎤 Wake word detection started (say one of: {', '.join(wake_phrases)})")
            else:
                logger.warning("No valid wake word detectors active; only manual trigger is available")

        except ImportError as e:
            logger.warning(f"Wake word detection not available: {e}")
            logger.info("Manual trigger via mic button still works")
        except Exception as e:
            logger.error(f"Failed to set up wake word detection: {e}")

    def _get_active_wake_words(self) -> list[str]:
        """Get active wake words from server state in a stable order"""
        if not self.api_server:
            return ['okay_nabu']

        # snapshot: the event loop thread mutates this set concurrently
        active_set = set(self.api_server.state.active_wake_words)
        if not active_set:
            return ['okay_nabu']

        ordered = [
            wake_word_id
            for wake_word_id in self.api_server.state.available_wake_words.keys()
            if wake_word_id in active_set
        ]
        if ordered:
            return ordered

        return sorted(active_set)

    def _update_wake_word_detector(self, initial_setup: bool = False):
        """Update wake word detector when active wake word changes"""
        from src.voice.wake_word import WakeWordDetector

        target_wake_words = self._get_active_wake_words()
        current_wake_words = list(self._wake_word_detectors.keys())

        if current_wake_words == target_wake_words:
            return

        action = "Initializing" if initial_setup else "Switching"
        logger.info(f"🔄 {action} wake words: {target_wake_words}")

        existing = self._wake_word_detectors
        detectors = {}

        for wake_word_id in target_wake_words:
            detector = existing.get(wake_word_id)
            if detector is None:
                detector = WakeWordDetector(wake_word_id)
                if getattr(detector, "_model", None) is None:
                    logger.warning(f"Wake word detector unavailable: {wake_word_id}")
                    continue

            if self._wake_word_callback:
                detector.on_wake_word(self._wake_word_callback)
            detectors[wake_word_id] = detector

        for wake_word_id, detector in existing.items():
            if wake_word_id in detectors:
                continue

            try:
                detector.close()
            except Exception as e:
                logger.debug(f"Failed to close wake word detector {wake_word_id}: {e}")

        self._wake_word_detectors = detectors
        wake_phrases = [det.wake_word_phrase for det in self._wake_word_detectors.values()]
        if wake_phrases:
            logger.info(f"🎤 Now listening for: {', '.join(wake_phrases)}")
        else:
            logger.warning("No wake word detectors are active")

    def _stop_wake_word_detection(self):
        """Stop wake word detection"""
        self._wake_word_listening = False
        if self._audio_recorder:
            try:
                self._audio_recorder.stop_recording()
            except Exception as e:
                logger.error(f"Failed to stop audio recorder: {e}")
            self._audio_recorder = None
        for wake_word_id, detector in self._wake_word_detectors.items():
            try:
                detector.close()
            except Exception as e:
                logger.debug(f"Failed to close wake word detector {wake_word_id}: {e}")
        self._wake_word_detectors = {}
        self._wake_word_callback = None
        if self._stop_word_detector:
            try:
                self._stop_word_detector.close()
            except Exception as e:
                logger.debug(f"Failed to close stop word detector: {e}")
        self._stop_word_detector = None

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

        if self._mdns_refresh_task:
            self._mdns_refresh_task.cancel()
            try:
                await self._mdns_refresh_task
            except asyncio.CancelledError:
                pass
            self._mdns_refresh_task = None

        # Stop wake word detection
        self._stop_wake_word_detection()

        # Stop Sendspin receiver
        await self._stop_sendspin()

        # Stop system tray icon
        if self.tray:
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

        self._cleanup_done.set()
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

    # Check for updates
    try:
        from src.update_checker import check_for_updates_async, show_update_notification
        import asyncio

        async def check_updates():
            result = await check_for_updates_async(timeout=5)
            if result:
                has_update, current, latest = result
                if has_update:
                    logger.info(f"Update available: {current} -> {latest}")
                    show_update_notification(current, latest)
                else:
                    logger.info(f"Already on latest version: {current}")

        asyncio.run(check_updates())
    except Exception as e:
        logger.warning(f"Failed to check for updates: {e}")

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
