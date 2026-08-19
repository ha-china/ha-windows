"""
Sendspin audio receiver (client side).

Music Assistant runs the Sendspin *server* (port 8927). This app runs a Sendspin
*client* that advertises itself via mDNS (`_sendspin._tcp.local.`) on port 8928;
Music Assistant auto-discovers it and connects. Incoming audio (PCM) is played
through the default sounddevice output device.

Music Assistant currently ships `aiosendspin[server]==6.0.5`; the wire protocol
changed substantially in 6.0 (no pairing/PSK handshake on the client side), so
this module targets aiosendspin 6.x. Only the PLAYER role is advertised, with
PCM 16-bit 48 kHz stereo, so no `av` dependency is pulled in.
"""

import asyncio
import logging
import socket
import uuid
from pathlib import Path
from typing import Callable, Optional

from src.core.models import get_user_data_dir

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
        self._stream_task: Optional[asyncio.Task] = None
        self._started = False
        self._connecting = False
        self._connected = False
        self._metadata_callback: Optional[Callable[[dict], None]] = None
        self._connection_callback: Optional[Callable[[bool], None]] = None
        self._state_callback: Optional[Callable[[bool], None]] = None
        self._artwork_callback: Optional[Callable[[bytes], None]] = None
        self._volume_callback: Optional[Callable[[int, bool], None]] = None
        # Software volume: PCM gain applied in the playback loop. This only
        # affects the music stream, not the Windows system volume.
        self._volume: float = 1.0   # 0.0 - 1.0
        self._muted: bool = False
        self._playing: bool = False
        self._audio_queue: Optional[asyncio.Queue] = None
        self._client_id: Optional[str] = None

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
        """Current volume as 0-100 (falls back to the system master volume)."""
        sys_vol = self.get_system_volume()
        return sys_vol if sys_vol is not None else round(self._volume * 100)

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
        """Report volume/mute state upstream so Music Assistant stays in sync."""
        client = self._client
        if client is None:
            return
        try:
            from aiosendspin.models.types import PlayerStateType

            task = asyncio.create_task(
                client.send_player_state(
                    state=PlayerStateType.SYNCHRONIZED,
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

        from aiosendspin.client import ClientListener, SendspinClient
        from aiosendspin.models.core import DeviceInfo
        from aiosendspin.models.artwork import ArtworkChannel, ClientHelloArtworkSupport
        from aiosendspin.models.player import ClientHelloPlayerSupport, SupportedAudioFormat
        from aiosendspin.models.types import AudioCodec, PictureFormat, PlayerCommand, Roles, ArtworkSource

        self._connecting = True
        try:
            self._client_id = self._load_or_create_client_id()

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

            async def handle_connection(ws) -> None:
                from aiosendspin.client import SendspinClient

                disconnect_event = asyncio.Event()

                def on_disconnect() -> None:
                    self._connected = False
                    disconnect_event.set()

                self._client = SendspinClient(
                    client_id=self._client_id,
                    client_name=self.name,
                    # PLAYER receives the audio stream; CONTROLLER lets us send
                    # playback commands upstream; METADATA delivers track info;
                    # ARTWORK delivers album cover images.
                    roles=[Roles.PLAYER, Roles.CONTROLLER, Roles.METADATA, Roles.ARTWORK],
                    player_support=player_support,
                    artwork_support=artwork_support,
                    device_info=device_info,
                )
                self._client.add_audio_chunk_listener(self._on_audio_chunk)
                self._client.add_metadata_listener(self._on_metadata)
                self._client.add_artwork_listener(self._on_artwork)
                self._client.add_stream_start_listener(self._on_stream_start)
                self._client.add_stream_end_listener(self._on_stream_end)
                self._client.add_server_command_listener(self._on_server_command)
                self._client.add_disconnect_listener(on_disconnect)

                logger.info("Sendspin: Music Assistant connected")
                self._connected = True
                self._notify_connection()
                try:
                    # attach_websocket returns after the handshake; keep the
                    # connection alive until the server disconnects.
                    await self._client.attach_websocket(ws)
                    await disconnect_event.wait()
                finally:
                    self._connected = False
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
            logger.error(f"Sendspin not available (install aiosendspin>=6.0,<7): {e}")
        except Exception as e:
            logger.error(f"Failed to start Sendspin receiver: {e}")
        finally:
            self._connecting = False

    def _get_app_version(self) -> Optional[str]:
        """Return the app version string, if available."""
        try:
            from src import __version__

            return __version__
        except Exception:
            return None

    def _load_or_create_client_id(self) -> str:
        """Persist a stable client id so Music Assistant keeps the same player."""
        path: Path = get_user_data_dir() / "sendspin_client_id"
        try:
            if path.exists():
                value = path.read_text(encoding="utf-8").strip()
                if value:
                    return value
        except Exception as e:
            logger.warning(f"Failed to read sendspin client id: {e}")
        client_id = uuid.uuid4().hex
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(client_id, encoding="utf-8")
        except Exception as e:
            logger.warning(f"Failed to persist sendspin client id: {e}")
        return client_id

    async def stop(self) -> None:
        """Stop the listener, disconnect clients and stop playback."""
        self._started = False
        if self._stream_task:
            self._stream_task.cancel()
            try:
                await self._stream_task
            except asyncio.CancelledError:
                pass
            self._stream_task = None
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
        """Queue incoming PCM audio for playback on the output device."""
        try:
            if audio_format.codec.value != "pcm":
                logger.warning("Unexpected codec %s, dropping chunk", audio_format.codec.value)
                return
            if self._audio_queue is None:
                return
            if not getattr(self, "_chunk_logged", False):
                self._chunk_logged = True
                logger.info(
                    "Sendspin: first audio chunk (%d bytes, codec=%s)",
                    len(payload),
                    audio_format.codec.value,
                )
            self._audio_queue.put_nowait(payload)
        except Exception as e:
            logger.debug(f"Audio chunk error: {e}")

    async def _playback_loop(self) -> None:
        """Consume PCM from the queue and stream it to sounddevice."""
        import sounddevice as sd
        import numpy as np

        stream: Optional[sd.OutputStream] = None
        try:
            while True:
                chunk = await self._audio_queue.get()
                if chunk is None:
                    break
                if stream is None:
                    stream = sd.OutputStream(
                        samplerate=SAMPLE_RATE,
                        channels=CHANNELS,
                        dtype="int16",
                        blocksize=2048,
                    )
                    stream.start()
                data = np.frombuffer(chunk, dtype=np.int16).reshape(-1, CHANNELS)
                stream.write(data)
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"Sendspin playback error: {e}")
        finally:
            if stream:
                try:
                    stream.stop()
                    stream.close()
                except Exception:
                    pass

    def _stop_playback(self) -> None:
        if self._stream_task:
            self._stream_task.cancel()
            self._stream_task = None
        self._audio_queue = None

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

    def _on_stream_start(self, message) -> None:
        logger.info("Sendspin: stream started")
        self._audio_queue = asyncio.Queue()
        if self._stream_task is None or self._stream_task.done():
            self._stream_task = asyncio.create_task(self._playback_loop())
        self._set_playing(True, "stream start")

    def _on_stream_end(self, roles) -> None:
        logger.info("Sendspin: stream ended")
        self._stop_playback()
        self._set_playing(False, "stream end")

    def _on_server_command(self, payload) -> None:
        """Apply volume/mute commands sent by Music Assistant to the system."""
        try:
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
