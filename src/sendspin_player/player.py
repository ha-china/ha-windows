"""
Sendspin audio receiver (client side).

Music Assistant runs the Sendspin *server* (port 8927). This app runs a Sendspin
*client* that advertises itself via mDNS (`_sendspin._tcp.local.`) on port 8928;
Music Assistant auto-discovers it and connects. Incoming audio (PCM) is played
through the default sounddevice output device.

Targets aiosendspin 9.x: Noise-encrypted pairing, a persistent client Identity
and time-synchronized playback (play timestamps computed from the shared clock,
so audio stays in sync with the UI instead of lagging a buffer behind).
"""

import asyncio
import logging
import socket
from pathlib import Path
from typing import Callable, Optional

from src.core.models import get_user_data_dir

from src.sendspin_player.sync_audio_player import SyncAudioPlayer

logger = logging.getLogger(__name__)

PLAYER_NAME = "HA Windows"
DEFAULT_PORT = 8928
DEFAULT_PATH = "/sendspin"

# PCM 16-bit 48 kHz stereo: decodable without av (PcmDecoder is a pass-through).
SAMPLE_RATE = 48000
CHANNELS = 2
BIT_DEPTH = 16

# Maximum compressed-audio bytes buffered before playback (about 1 second of PCM).
BUFFER_CAPACITY = 48000 * CHANNELS * (BIT_DEPTH // 8)

# Time-synchronized playback tuning: see aiosendspin SendspinClient docs.
STATIC_DELAY_MS = 50.0      # fixed extra delay after clock sync
REQUIRED_LEAD_MS = 200.0    # decode/pre-buffer lead before the first chunk
MIN_BUFFER_MS = 200.0       # sustained playback buffer for jitter absorption
# Local target buffer: we feed sounddevice this much AHEAD of the server
# clock instead of exactly on time. A fixed buffer absorbs scheduling jitter,
# write() blocking and clock-drift residuals; chasing the exact play time
# makes the skew grow monotonically (per-chunk overhead is never recovered).
_TARGET_BUFFER_MS = 100.0

# Drop backlog when more than this many PCM chunks are waiting. Each chunk is
# ~512 samples @48 kHz (~10.7 ms), so this caps the reported offset at ~107 ms
# - comfortably inside the +/-150 ms tolerance, and never growing.
_MAX_QUEUE_DEPTH = 10


def get_hostname() -> str:
    """Return the Windows machine name (hostname without domain part)."""
    try:
        return socket.gethostname().split(".")[0]
    except Exception:
        return PLAYER_NAME


def _defined(value):
    """Return the value when actually set; None for None/UndefinedField sentinel."""
    try:
        from aiosendspin.models.types import UndefinedField

        if isinstance(value, UndefinedField):
            return None
    except Exception:
        pass
    return value if value is not None else None


def get_device_info():
    """Return (product_name, manufacturer) of the local machine.

    Delegates to the shared SMBIOS registry read in core.models so the
    ESPHome device info card and Music Assistant report identical identity.
    """
    from src.core.models import get_hardware_identity

    manufacturer, model = get_hardware_identity()
    # Registry read failed -> generic fallbacks for Music Assistant display
    if manufacturer == "ha-china":
        manufacturer = "Microsoft"
    if model == "Home Assistant Windows":
        model = "Windows PC"
    return (model, manufacturer)


class SendspinReceiver:
    """Sendspin client that Music Assistant discovers and streams audio to."""

    def __init__(self, name: Optional[str] = None):
        self.name = name or get_hostname()
        self._listener: Optional[object] = None
        self._client: Optional[object] = None
        self._started = False
        self._connecting = False
        self._connected = False
        self._metadata_callback: Optional[Callable[[dict], None]] = None
        self._connection_callback: Optional[Callable[[bool], None]] = None
        self._state_callback: Optional[Callable[[bool], None]] = None
        self._sync_callback: Optional[Callable[[int, bool], None]] = None
        self._stream_event_callback: Optional[Callable[[str], None]] = None
        self._artwork_callback: Optional[Callable[[bytes], None]] = None
        self._volume_callback: Optional[Callable[[int, bool], None]] = None
        # Software volume: PCM gain applied in the playback loop. This only
        # affects the music stream, not the Windows system volume.
        self._volume: float = 1.0   # 0.0 - 1.0
        self._muted: bool = False
        self._playing: bool = False
        self._player: Optional[SyncAudioPlayer] = None   # DAC-clocked sync player
        self._client_id: Optional[str] = None
        self._identity = None          # aiosendspin.noise.keys.Identity (lazy)
        self._pairing_store = None     # FileClientPairingStore (lazy, async open)

    # ------------------------------------------------------------------ lifecycle

    @property
    def is_connected(self) -> bool:
        return bool(self._connected and self._client is not None)

    @property
    def is_running(self) -> bool:
        return self._started

    def set_metadata_callback(self, callback: Callable[[dict], None]) -> None:
        """Register a callback receiving current track info {"title","artist"}."""
        self._metadata_callback = callback

    def set_connection_callback(self, callback: Callable[[bool], None]) -> None:
        """Register a callback notified on connection state changes (True=connected)."""
        self._connection_callback = callback

    def set_state_callback(self, callback: Callable[[bool], None]) -> None:
        """Register a callback notified on playback state changes (True=playing)."""
        self._state_callback = callback

    def set_artwork_callback(self, callback: Callable[[bytes], None]) -> None:
        """Register a callback receiving album artwork image bytes (JPEG)."""
        self._artwork_callback = callback

    def set_volume_callback(self, callback: Callable[[int, bool], None]) -> None:
        """Register a callback notified on volume/mute changes: (percent, muted)."""
        self._volume_callback = callback

    @property
    def volume_percent(self) -> int:
        """Last known volume as 0-100 (updated by commands / local changes)."""
        return round(self._volume * 100)

    @property
    def muted(self) -> bool:
        """Last known mute state."""
        return self._muted

    def apply_local_volume(self, volume: int) -> None:
        """Apply system volume locally (0-100) and notify listeners."""
        volume = max(0, min(100, int(volume)))
        self._volume = volume / 100
        self._muted = volume == 0
        self._set_system_volume(volume)
        self._notify_volume()

    def apply_local_mute(self, muted: bool) -> None:
        """Mute/unmute the system volume and notify listeners."""
        self._muted = bool(muted)
        self._set_system_mute(muted)
        self._notify_volume()

    def _notify_volume(self) -> None:
        if self._volume_callback:
            try:
                self._volume_callback(self.volume_percent, self._muted)
            except Exception as e:
                logger.debug(f"Volume callback error: {e}")

    def _report_player_state(self) -> None:
        """Report volume/mute availability upstream so Music Assistant stays in sync."""
        client = self._client
        if client is None:
            return
        try:
            task = asyncio.create_task(
                client.send_player_state(
                    available=True,
                    volume=self.volume_percent,
                    muted=self._muted,
                )
            )
            task.add_done_callback(lambda t: t.exception() if not t.cancelled() else None)
        except Exception as e:
            logger.debug(f"Failed to report player state: {e}")

    def is_playing(self) -> bool:
        """True when playback is active per the last metadata speed update."""
        return self._playing

    def set_local_playing(self, playing: bool) -> None:
        """Optimistically flip the playing state after a LOCAL control action.

        MA only reports the authoritative state via periodic metadata (which
        stops entirely while paused); without this the UI lags seconds behind
        the user's own button presses. The next metadata/stream event will
        correct any drift.
        """
        self._set_playing(playing, "local control")

    def _set_playing(self, playing: bool, source: str) -> None:
        if playing == self._playing:
            return
        self._playing = playing
        logger.debug(f"Sendspin: playing={playing} ({source})")
        self._notify_state(playing)

    async def send_media_command(self, command, volume: Optional[int] = None,
                                 mute: Optional[bool] = None) -> None:
        """Send a playback control command upstream to Music Assistant.

        command: aiosendspin MediaCommand (PLAY/PAUSE/STOP/NEXT/PREVIOUS/VOLUME/MUTE/...)
        volume: 0-100, only for MediaCommand.VOLUME
        mute: True/False, only for MediaCommand.MUTE
        """
        client = self._client
        if client is None:
            logger.warning("Sendspin: cannot send command, not connected")
            return
        try:
            await client.send_group_command(command, volume=volume, mute=mute)
            logger.info(f"Sendspin: sent command {getattr(command, 'name', command)}"
                        f"{f' volume={volume}' if volume is not None else ''}"
                        f"{f' mute={mute}' if mute is not None else ''}")
        except Exception as e:
            logger.error(f"Sendspin: failed to send command: {e}")

    async def start(self) -> None:
        """Start the client listener and mDNS advertising."""
        if self._started:
            return

        from aiosendspin.client import ClientListener, PairingSupport, SendspinClient
        from aiosendspin.models.artwork import ArtworkChannel, ClientHelloArtworkSupport
        from aiosendspin.models.core import DeviceInfo
        from aiosendspin.models.player import ClientHelloPlayerSupport, SupportedAudioFormat
        from aiosendspin.models.types import AudioCodec, ArtworkSource, PictureFormat, PlayerCommand, Roles
        from aiosendspin.noise.keys import Identity, b64url_decode
        from aiosendspin.noise.trust_store import FileClientPairingStore

        self._connecting = True
        try:
            # Persistent client identity: restarts keep the same player + keys.
            self._identity = self._load_or_create_identity()
            self._client_id = self._identity.peer_id

            pairing_store = await self._load_pairing_store()

            product_name, manufacturer = get_device_info()
            device_info = DeviceInfo(
                product_name=product_name,
                manufacturer=manufacturer,
                software_version=self._get_app_version(),
            )

            player_support = ClientHelloPlayerSupport(
                supported_formats=[
                    SupportedAudioFormat(
                        codec=AudioCodec.PCM,
                        channels=CHANNELS,
                        sample_rate=SAMPLE_RATE,
                        bit_depth=BIT_DEPTH,
                    )
                ],
                buffer_capacity=BUFFER_CAPACITY,
                supported_commands=[PlayerCommand.VOLUME, PlayerCommand.MUTE],
            )

            artwork_support = ClientHelloArtworkSupport(
                channels=[
                    ArtworkChannel(
                        source=ArtworkSource.ALBUM,
                        format=PictureFormat.JPEG,
                        media_width=600,
                        media_height=600,
                    )
                ]
            )

            async def show_pin(pin) -> None:
                """Show/clear the pairing PIN to the user (None clears)."""
                self._notify_pairing_pin(pin)

            pairing_support = PairingSupport(pin_display=show_pin)

            async def handle_connection(ws) -> None:
                client = SendspinClient(
                    self._identity,
                    self.name,
                    # PLAYER receives the audio stream; CONTROLLER lets us send
                    # playback commands upstream; METADATA delivers track info;
                    # ARTWORK delivers album cover images.
                    roles=[Roles.PLAYER, Roles.CONTROLLER, Roles.METADATA, Roles.ARTWORK],
                    pairing_store=pairing_store,
                    player_support=player_support,
                    artwork_support=artwork_support,
                    device_info=device_info,
                    pairing_support=pairing_support,
                    static_delay_ms=STATIC_DELAY_MS,
                    required_lead_time_ms=REQUIRED_LEAD_MS,
                    min_buffer_ms=MIN_BUFFER_MS,
                    initial_volume=self.volume_percent,
                    initial_muted=self._muted,
                )
                self._client = client
                client.add_audio_chunk_listener(self._on_audio_chunk)
                client.add_metadata_listener(self._on_metadata)
                client.add_artwork_listener(self._on_artwork)
                client.add_stream_start_listener(self._on_stream_start)
                client.add_stream_end_listener(self._on_stream_end)
                client.add_server_command_listener(self._on_server_command)
                client.add_disconnect_listener(self._on_disconnect)

                # Report the PC's REAL volume/mute so MA drops any stale
                # state it stored for this device (e.g. a mute from a
                # previous session).
                sys_vol = self.get_system_volume()
                if sys_vol is not None:
                    self._volume = sys_vol / 100
                sys_mute = self.get_system_mute()
                if sys_mute is not None:
                    self._muted = sys_mute
                self._report_player_state()

                logger.info("Sendspin: Music Assistant connected")
                self._connected = True
                self._notify_connection()
                try:
                    # attach_websocket blocks until the connection closes.
                    await client.attach_websocket(ws)
                finally:
                    self._connected = False
                    if self._client is client:
                        self._client = None
                    logger.info("Sendspin: Music Assistant disconnected")
                    self._stop_playback()
                    self._notify_connection()

            self._listener = ClientListener(
                client_id=self._client_id,
                on_connection=handle_connection,
                client_name=self.name,
                port=DEFAULT_PORT,
                path=DEFAULT_PATH,
            )
            await self._listener.start()
            self._started = True
            logger.info(
                "Sendspin receiver started on ws://0.0.0.0:%d%s (player '%s', id %s)",
                DEFAULT_PORT,
                DEFAULT_PATH,
                self.name,
                self._client_id,
            )
        except ImportError as e:
            logger.error(f"Sendspin not available (install aiosendspin>=9.1.1): {e}")
        except Exception as e:
            logger.error(f"Failed to start Sendspin receiver: {e}")
        finally:
            self._connecting = False

    def _load_or_create_identity(self):
        """Load or create the persistent client Identity (X25519 key pair)."""
        from aiosendspin.noise.keys import Identity, b64url_decode, b64url_encode

        path: Path = get_user_data_dir() / "sendspin_identity"
        try:
            if path.exists():
                priv_b64 = path.read_text(encoding="utf-8").strip()
                if priv_b64:
                    return Identity.from_private_bytes(b64url_decode(priv_b64))
        except Exception as e:
            logger.warning(f"Failed to load sendspin identity: {e}")
        identity = Identity.generate()
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(b64url_encode(identity.private_bytes), encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to persist sendspin identity: {e}")
        return identity

    async def _load_pairing_store(self):
        """Open the file-backed pairing store (persists Noise PSKs across runs)."""
        from aiosendspin.noise.trust_store import FileClientPairingStore

        path: Path = get_user_data_dir() / "sendspin_pairing.json"
        self._pairing_store = await FileClientPairingStore.open(path)
        return self._pairing_store

    def _notify_pairing_pin(self, pin) -> None:
        """Expose the pairing PIN (str or None=clear) to the UI/notifications."""
        try:
            if pin:
                logger.info(f"Sendspin pairing PIN: {pin}")
            else:
                logger.debug("Sendspin pairing PIN cleared")
        except Exception as e:
            logger.debug(f"Pairing pin notify error: {e}")

    def _on_disconnect(self) -> None:
        """Called when the current Sendspin connection closes."""
        self._connected = False

    def _get_app_version(self) -> Optional[str]:
        """Return the app version string, if available."""
        try:
            from src import __version__

            return __version__
        except Exception:
            return None

    async def stop(self) -> None:
        """Stop the listener, disconnect clients and stop playback."""
        self._started = False
        self._stop_playback()

        if self._client is not None:
            try:
                await self._client.disconnect()
            except Exception as e:
                logger.debug(f"Failed to disconnect Sendspin client: {e}")
            self._client = None

        if self._listener:
            try:
                await self._listener.stop()
            except Exception as e:
                logger.debug(f"Failed to stop Sendspin listener: {e}")
            self._listener = None

    # ------------------------------------------------------------------ audio

    def _on_audio_chunk(self, timestamp_us: int, payload: bytes, audio_format) -> None:
        """Feed incoming PCM to the DAC-clocked sync player."""
        try:
            codec = getattr(audio_format, "codec", None)
            codec_value = codec.value if hasattr(codec, "value") else str(codec)
            if codec_value != "pcm":
                logger.warning("Unexpected codec %s, dropping chunk", codec_value)
                return
            if self._player is None or not self._player.is_ready():
                return
            if not getattr(self, "_chunk_logged", False):
                self._chunk_logged = True
                logger.info(
                    "Sendspin: first audio chunk (%d bytes, codec=%s)",
                    len(payload),
                    codec_value,
                )
            self._player.enqueue(timestamp_us, payload)
        except Exception as e:
            logger.debug(f"Audio chunk error: {e}")

    def _start_player(self) -> None:
        """Create (once) the DAC-clocked sync player and start its stream."""
        if self._player is None:
            self._player = SyncAudioPlayer(
                compute_play_time=self._compute_play_time,
                now_us=self._now_us,
                is_synced=self._is_synced,
                on_skew=self._notify_sync,
            )
        self._player.start()

    def _stop_playback(self) -> None:
        if self._player is not None:
            self._player.stop()

    def _notify_connection(self) -> None:
        """Notify the registered callback of the current connection state."""
        if self._connection_callback:
            try:
                self._connection_callback(self.is_connected)
            except Exception as e:
                logger.debug(f"Connection callback error: {e}")

    # ------------------------------------------------------------------ events

    def _on_metadata(self, state_payload) -> None:
        """Handle server state updates carrying track metadata and progress."""
        try:
            metadata = getattr(state_payload, "metadata", None)
            if metadata is None:
                return
            title = _defined(getattr(metadata, "title", None))
            artist = _defined(getattr(metadata, "artist", None))

            info = {}
            if title or artist:
                info["title"] = str(title) if title else ""
                info["artist"] = str(artist) if artist else ""

            # Playback progress may arrive in updates without a title; do not
            # gate it behind the title check.
            progress = _defined(getattr(metadata, "progress", None))
            if progress is not None:
                info["progress_ms"] = _defined(getattr(progress, "track_progress", 0)) or 0
                info["duration_ms"] = _defined(getattr(progress, "track_duration", 0)) or 0
                speed = _defined(getattr(progress, "playback_speed", 1000))
                if speed is None:
                    speed = 0  # paused
                info["speed"] = speed / 1000
                # playback_speed 0 means paused; > 0 means actively playing.
                self._set_playing(speed > 0, "metadata speed")

            if info and self._metadata_callback:
                self._metadata_callback(info)
        except Exception as e:
            logger.debug(f"Metadata error: {e}")

    def _on_artwork(self, channel: int, data: bytes) -> None:
        """Handle artwork binary frames from the server."""
        if channel != 0 or not data:
            return
        if self._artwork_callback:
            try:
                self._artwork_callback(data)
            except Exception as e:
                logger.debug(f"Artwork callback error: {e}")

    def _notify_state(self, playing: bool) -> None:
        if self._state_callback:
            try:
                self._state_callback(playing)
            except Exception as e:
                logger.debug(f"State callback error: {e}")

    def set_stream_event_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        """Register a callback for stream lifecycle events: "start" / "end". """
        self._stream_event_callback = callback

    def set_sync_callback(self, callback: Optional[Callable[[int, bool], None]]) -> None:
        """Register a callback receiving playback clock skew in ms.

        offset_ms > 0  -> this client is playing behind the server (slow)
        offset_ms < 0  -> this client is playing ahead of the server (fast)
        synchronized   -> whether the shared clock has converged.
        """
        self._sync_callback = callback

    def _is_synced(self) -> bool:
        client = self._client
        if client is not None:
            try:
                return bool(client.is_time_synchronized())
            except Exception:
                pass
        return False

    def _compute_play_time(self, server_timestamp_us: int) -> int:
        """Convert a server timestamp to the loop-clock play instant (µs)."""
        client = self._client
        if client is not None:
            try:
                return int(client.compute_play_time(server_timestamp_us))
            except Exception as e:
                logger.debug(f"compute_play_time failed: {e}")
        return self._now_us()

    def _now_us(self) -> int:
        client = self._client
        if client is not None:
            try:
                return int(client.now_us())
            except Exception:
                pass
        try:
            import time as _time

            return int(_time.monotonic() * 1_000_000)
        except Exception:
            return 0

    def _notify_sync(self, offset_ms: int, synchronized: bool) -> None:
        if not self._sync_callback:
            return
        try:
            self._sync_callback(offset_ms, synchronized)
        except Exception as e:
            logger.debug(f"Sync callback error: {e}")

    def _on_stream_start(self, message) -> None:
        logger.info("Sendspin: stream started")
        if self._stream_event_callback:
            try:
                self._stream_event_callback("start")
            except Exception as e:
                logger.debug(f"Stream event callback error: {e}")
        try:
            self._start_player()
        except Exception as e:
            logger.error(f"Failed to start sync audio player: {e}")
        self._set_playing(True, "stream start")

    def _on_stream_end(self, roles) -> None:
        logger.info("Sendspin: stream ended")
        try:
            self._stop_playback()
        except Exception as e:
            logger.error(f"Failed to stop playback: {e}")
        self._set_playing(False, "stream end")

    def _on_server_command(self, payload) -> None:
        """Apply volume/mute commands sent by Music Assistant to the system."""
        try:
            if not self.is_playing():
                # Nothing is playing: this is MA replaying its stored state at
                # connect. Don't let it touch the system volume.
                logger.debug("Sendspin: ignoring volume/mute while not playing")
                return
            player_cmd = getattr(payload, "player", None)
            if player_cmd is None:
                return
            command = getattr(player_cmd, "command", None)
            command_value = command.value if hasattr(command, "value") else str(command)
            if command_value == "volume" and getattr(player_cmd, "volume", None) is not None:
                volume = max(0, min(100, int(player_cmd.volume)))
                self._volume = volume / 100
                self._muted = volume == 0
                logger.info(f"Sendspin: system volume set to {volume}%")
                self._set_system_volume(volume)
                self._notify_volume()
                self._report_player_state()
            elif command_value == "mute" and getattr(player_cmd, "mute", None) is not None:
                self._muted = bool(player_cmd.mute)
                logger.info(f"Sendspin: system muted={self._muted}")
                self._set_system_mute(self._muted)
                self._notify_volume()
                self._report_player_state()
        except Exception as e:
            logger.error(f"Failed to apply server command: {e}")

    # ------------------------------------------------------------------ system volume

    @staticmethod
    def _set_system_volume(volume: int) -> None:
        """Set the Windows system (master) volume, 0-100."""
        try:
            from pycaw.pycaw import AudioUtilities

            volume = max(0, min(100, volume))
            devices = AudioUtilities.GetSpeakers()
            volume_control = devices.EndpointVolume
            volume_control.SetMasterVolumeLevelScalar(volume / 100.0, None)
            logger.info(f"Sendspin: system volume set to {volume}%")
        except Exception as e:
            logger.warning(f"Failed to set system volume: {e}")

    @staticmethod
    def _set_system_mute(muted: bool) -> None:
        """Mute or unmute the Windows system (master) volume."""
        try:
            from pycaw.pycaw import AudioUtilities

            devices = AudioUtilities.GetSpeakers()
            volume_control = devices.EndpointVolume
            volume_control.SetMute(1 if muted else 0, None)
            logger.info(f"Sendspin: system muted={muted}")
        except Exception as e:
            logger.warning(f"Failed to set system mute: {e}")

    @staticmethod
    def get_system_volume() -> Optional[int]:
        """Read the Windows master volume as 0-100, None when unavailable."""
        try:
            from pycaw.pycaw import AudioUtilities

            devices = AudioUtilities.GetSpeakers()
            level = devices.EndpointVolume.GetMasterVolumeLevelScalar()
            return round(float(level) * 100)
        except Exception as e:
            logger.debug(f"Failed to read system volume: {e}")
            return None

    @staticmethod
    def get_system_mute() -> Optional[bool]:
        """Read the Windows master mute state, None when unavailable."""
        try:
            from pycaw.pycaw import AudioUtilities

            devices = AudioUtilities.GetSpeakers()
            return bool(devices.EndpointVolume.GetMute())
        except Exception as e:
            logger.debug(f"Failed to read system mute: {e}")
            return None
