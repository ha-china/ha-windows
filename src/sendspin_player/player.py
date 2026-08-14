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
import subprocess
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


def get_device_info():
    """Return (product_name, manufacturer) of the local machine.

    Queries WMI for the real hardware model and manufacturer; falls back to
    sensible defaults when unavailable.
    """
    product_name: Optional[str] = None
    manufacturer: Optional[str] = None
    try:
        out = subprocess.run(
            [
                "powershell",
                "-NoProfile",
                "-Command",
                "(Get-CimInstance Win32_ComputerSystem).Manufacturer;"
                " (Get-CimInstance Win32_ComputerSystem).Model",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        lines = [ln.strip() for ln in out.stdout.splitlines() if ln.strip()]
        if len(lines) >= 1:
            manufacturer = lines[0]
        if len(lines) >= 2:
            product_name = lines[1]
    except Exception as e:
        logger.debug(f"Failed to query device info: {e}")
    return (
        product_name or "Windows PC",
        manufacturer or "Microsoft",
    )


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
        self._metadata_callback: Optional[Callable[[str], None]] = None
        self._audio_queue: Optional[asyncio.Queue] = None
        self._client_id: Optional[str] = None

    # ------------------------------------------------------------------ lifecycle

    @property
    def is_connected(self) -> bool:
        return bool(self._connected and self._client is not None)

    @property
    def is_running(self) -> bool:
        return self._started

    def set_metadata_callback(self, callback: Callable[[str], None]) -> None:
        """Register a callback receiving current track metadata (title)."""
        self._metadata_callback = callback

    async def start(self) -> None:
        """Start the client listener and mDNS advertising."""
        if self._started:
            return

        from aiosendspin.client import ClientListener, SendspinClient
        from aiosendspin.models.core import DeviceInfo
        from aiosendspin.models.player import ClientHelloPlayerSupport, SupportedAudioFormat
        from aiosendspin.models.types import AudioCodec, PlayerCommand, Roles

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

            async def handle_connection(ws) -> None:
                from aiosendspin.client import SendspinClient

                disconnect_event = asyncio.Event()

                def on_disconnect() -> None:
                    self._connected = False
                    disconnect_event.set()

                self._client = SendspinClient(
                    client_id=self._client_id,
                    client_name=self.name,
                    roles=[Roles.PLAYER],
                    player_support=player_support,
                    device_info=device_info,
                )
                self._client.add_audio_chunk_listener(self._on_audio_chunk)
                self._client.add_metadata_listener(self._on_metadata)
                self._client.add_stream_start_listener(self._on_stream_start)
                self._client.add_stream_end_listener(self._on_stream_end)
                self._client.add_server_command_listener(self._on_server_command)
                self._client.add_disconnect_listener(on_disconnect)

                logger.info("Sendspin: Music Assistant connected")
                self._connected = True
                try:
                    # attach_websocket returns after the handshake; keep the
                    # connection alive until the server disconnects.
                    await self._client.attach_websocket(ws)
                    await disconnect_event.wait()
                finally:
                    self._connected = False
                    logger.info("Sendspin: Music Assistant disconnected")
                    self._stop_playback()

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

    # ------------------------------------------------------------------ events

    def _on_metadata(self, state_payload) -> None:
        """Handle server state updates carrying track metadata."""
        try:
            metadata = getattr(state_payload, "metadata", None)
            if metadata is None:
                return
            title = getattr(metadata, "title", None)
            artist = getattr(metadata, "artist", None)
            text = title or artist
            if text and self._metadata_callback:
                self._metadata_callback(str(text))
        except Exception as e:
            logger.debug(f"Metadata error: {e}")

    def _on_stream_start(self, message) -> None:
        logger.info("Sendspin: stream started")
        self._audio_queue = asyncio.Queue()
        if self._stream_task is None or self._stream_task.done():
            self._stream_task = asyncio.create_task(self._playback_loop())

    def _on_stream_end(self, roles) -> None:
        logger.info("Sendspin: stream ended")
        self._stop_playback()

    def _on_server_command(self, payload) -> None:
        """Apply volume/mute commands sent by Music Assistant to the system."""
        try:
            player_cmd = getattr(payload, "player", None)
            if player_cmd is None:
                return
            command = getattr(player_cmd, "command", None)
            command_value = command.value if hasattr(command, "value") else str(command)
            if command_value == "volume" and getattr(player_cmd, "volume", None) is not None:
                self._set_system_volume(int(player_cmd.volume))
            elif command_value == "mute" and getattr(player_cmd, "mute", None) is not None:
                self._set_system_mute(bool(player_cmd.mute))
        except Exception as e:
            logger.error(f"Failed to apply server command: {e}")

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
