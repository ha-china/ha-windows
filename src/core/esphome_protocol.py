"""
ESPHome protocol core: framing, handshake, connection lifecycle.

The voice-assistant conversation, playback and entity-registry concerns live
in dedicated mixins (va_conversation / media_playback / entity_registry) that
are composed into ESPHomeProtocol below. The split is purely structural -
all methods still run on the same instance and share its state.
"""

import asyncio
import logging
import socket
import threading
from collections.abc import Iterable
from typing import Any, Callable, Dict, List, Optional, Set

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (
    HelloRequest,
    HelloResponse,
    AuthenticationRequest,
    AuthenticationResponse,
    DisconnectRequest,
    DisconnectResponse,
    PingRequest,
    PingResponse,
    DeviceInfoRequest,
    DeviceInfoResponse,
    ListEntitiesRequest,
    ListEntitiesDoneResponse,
    MediaPlayerCommandRequest,
    ButtonCommandRequest,
    ExecuteServiceRequest,
    SubscribeHomeAssistantStatesRequest,
    SwitchCommandRequest,
    VoiceAssistantConfigurationRequest,
    VoiceAssistantConfigurationResponse,
    VoiceAssistantEventResponse,
    VoiceAssistantAnnounceRequest,
    VoiceAssistantAnnounceFinished,
    VoiceAssistantRequest,
    VoiceAssistantAudio,
    VoiceAssistantSetConfiguration,
    VoiceAssistantTimerEventResponse,
    VoiceAssistantWakeWord,
)
from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO
from aioesphomeapi._frame_helper.packets import make_plain_text_packets
from aioesphomeapi.model import (
    VoiceAssistantEventType,
    VoiceAssistantFeature,
    VoiceAssistantTimerEventType,
)
from google.protobuf import message

from .models import ServerState, create_default_state
from .entity_registry import EntityRegistryMixin
from .media_playback import PlaybackMixin
from .va_conversation import VoiceAssistantMixin

# Message type mapping
PROTO_TO_MESSAGE_TYPE = {v: k for k, v in MESSAGE_TYPE_TO_PROTO.items()}

logger = logging.getLogger(__name__)


class ESPHomeProtocol(VoiceAssistantMixin, PlaybackMixin, EntityRegistryMixin,
                      asyncio.Protocol):
    """
    ESPHome API Protocol Handler

    References linux-voice-assistant's VoiceSatelliteProtocol implementation
    Implements complete Voice Assistant state machine
    """

    MAX_BUFFER_SIZE = 4 * 1024 * 1024
    STATE_UPDATE_INTERVAL = 15.0

    def __init__(self, state: ServerState):
        super().__init__()

        self.state = state
        self.state.satellite = self

        # Protocol buffer
        self._buffer: Optional[bytes] = None
        self._buffer_len: int = 0
        self._pos: int = 0
        self._transport = None
        self._writelines = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._loop_thread_id: Optional[int] = None

        # Voice Assistant state machine
        self._is_streaming_audio = False
        self._tts_url: Optional[str] = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_finished = False
        self._is_playing_tts = False  # Flag to pause wake word detection during TTS playback
        self._volume_ducking_enabled = False  # User preference: do not lower global system volume

        self._audio_streaming_task: Optional[asyncio.Task] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # External wake word cache
        self._external_wake_words: Dict[str, Any] = {}

        # Module instances (lazy load)
        self._monitor = None
        self._media_player_entity = None
        self._button_manager = None
        self._service_manager = None
        self._config_sensor_manager = None
        self._hotkey_manager = None
        self._thinking_sound_entity = None
        self._mic_mute_entity = None
        self._state_update_task: Optional[asyncio.Task] = None
        self._processing = False
        self._ha_host: Optional[str] = None

        # Phase callback for tray icon state updates
        self._phase_callback: Optional[Callable[[str], None]] = None

        # Microphone mute callback (set by main program)
        self._muted_callback: Optional[Callable[[bool], None]] = None

        # Conversation text callback for tray balloon notifications
        self._conversation_callback: Optional[Callable[[str, str], None]] = None

        # Debug capture of the audio actually streamed to HA (last conversation)
        self._debug_audio_chunks: List[bytes] = []
        self._audio_chunks_sent = 0

        logger.debug(f"ESPHome protocol initialized: {self.state.name}")

    @property
    def is_playing_tts(self) -> bool:
        """Thread-safe view of the TTS playback flag (read from the audio thread)."""
        return self._is_playing_tts

    def set_phase_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        self._phase_callback = callback

    def set_muted_callback(self, callback: Optional[Callable[[bool], None]]) -> None:
        self._muted_callback = callback

    def set_conversation_callback(self, callback: Optional[Callable[[str, str], None]]) -> None:
        self._conversation_callback = callback

    def _set_muted(self, muted: bool) -> None:
        """Persist and apply microphone mute state (called by switch entity)."""
        if self._muted_callback:
            try:
                self._muted_callback(muted)
            except Exception as e:
                logger.error(f"Failed to apply microphone mute: {e}")

    def _push_mute_state(self) -> None:
        """Push the current mute switch state to Home Assistant."""
        if self._mic_mute_entity is not None:
            self.send_messages(
                list(self._mic_mute_entity.handle_message(SubscribeHomeAssistantStatesRequest()))
            )

    def _set_muted_and_push(self, muted: bool) -> None:
        """Apply the mute state and push it to Home Assistant (tray path)."""
        self._set_muted(muted)
        self._push_mute_state()

    def _set_phase(self, phase: str) -> None:
        logger.info(f"Phase: {phase}")
        if self._phase_callback:
            try:
                self._phase_callback(phase)
            except Exception as e:
                logger.debug(f"Phase callback error: {e}")

    # ========== Connection Lifecycle ==========

    def connection_made(self, transport) -> None:
        """New connection established"""
        self._transport = transport
        self._writelines = transport.writelines
        try:
            self._event_loop = asyncio.get_running_loop()
        except RuntimeError:
            pass  # no running loop; keep previous reference
        try:
            self._loop = asyncio.get_running_loop()
        except RuntimeError:
            self._loop = None
            self._loop_thread_id = None
        else:
            self._loop_thread_id = threading.get_ident()
        peername = transport.get_extra_info("peername")
        if peername:
            self._ha_host = peername[0]
            if self._service_manager is not None:
                self._service_manager.set_ha_host(self._ha_host)
        logger.info(f"📱 New client connected: {peername}")
        self._set_phase('idle')

    def connection_lost(self, exc) -> None:
        """Connection lost"""
        logger.debug("Client disconnected")
        self._transport = None
        self._writelines = None
        self._loop = None
        self._loop_thread_id = None

        # Reset streaming state (main recorder continues)
        self._is_streaming_audio = False
        self._tts_url = None
        self._tts_played = False
        self._continue_conversation = False
        self._cancel_state_updates()

        # Drop the satellite reference so a dead connection does not keep the
        # whole object graph alive or serve stale state.
        if self.state.satellite is self:
            self.state.satellite = None

        # Restore volume (if previously ducked)
        self.unduck()
        self._set_phase('not_ready')

    def data_received(self, data: bytes) -> None:
        """Receive data"""
        incoming_size = len(data)
        if self._buffer_len + incoming_size > self.MAX_BUFFER_SIZE:
            logger.error(
                "Protocol buffer exceeded %d bytes; closing connection",
                self.MAX_BUFFER_SIZE,
            )
            self._buffer = None
            self._buffer_len = 0
            self._pos = 0
            if self._transport:
                self._transport.close()
            return

        if self._buffer is None:
            self._buffer = data
            self._buffer_len = len(data)
        else:
            self._buffer += data
            self._buffer_len += len(data)

        # Process all complete messages in buffer
        while self._buffer_len >= 3:
            self._pos = 0

            # Read preamble (must be 0x00)
            preamble = self._read_varuint()
            if preamble != 0x00:
                logger.error(f"Invalid preamble: {preamble}, clearing buffer")
                self._buffer = None
                self._buffer_len = 0
                self._pos = 0
                return

            length = self._read_varuint()
            if length == -1:
                return

            msg_type = self._read_varuint()
            if msg_type == -1:
                return

            if length == 0:
                self._remove_from_buffer()
                self._process_packet(msg_type, b"")
                continue

            packet_data = self._read(length)
            if packet_data is None:
                return

            self._remove_from_buffer()
            self._process_packet(msg_type, packet_data)

    # ========== Buffer Operations ==========

    def _read(self, length: int) -> Optional[bytes]:
        new_pos = self._pos + length
        if self._buffer_len < new_pos:
            return None
        original_pos = self._pos
        self._pos = new_pos
        return self._buffer[original_pos:new_pos]

    def _read_varuint(self) -> int:
        if not self._buffer:
            return -1
        result = 0
        bitpos = 0
        while self._buffer_len > self._pos:
            val = self._buffer[self._pos]
            self._pos += 1
            result |= (val & 0x7F) << bitpos
            if (val & 0x80) == 0:
                return result
            bitpos += 7
        return -1

    def _remove_from_buffer(self) -> None:
        end_of_frame_pos = self._pos
        self._buffer_len -= end_of_frame_pos
        if self._buffer_len == 0:
            self._buffer = None
        else:
            self._buffer = self._buffer[end_of_frame_pos:]

    # ========== Message Processing ==========

    def _process_packet(self, msg_type: int, packet_data: bytes) -> None:
        """Process received packet"""
        msg_class = MESSAGE_TYPE_TO_PROTO.get(msg_type)
        if msg_class is None:
            logger.warning(f"Unknown message type: {msg_type}")
            return

        msg_inst = msg_class.FromString(packet_data)

        # Basic protocol messages
        if isinstance(msg_inst, HelloRequest):
            self._handle_hello(msg_inst)
        elif isinstance(msg_inst, AuthenticationRequest):
            self._handle_auth(msg_inst)
        elif isinstance(msg_inst, DisconnectRequest):
            self._handle_disconnect(msg_inst)
        elif isinstance(msg_inst, PingRequest):
            self.send_messages([PingResponse()])
        # Voice Assistant messages
        elif isinstance(msg_inst, VoiceAssistantEventResponse):
            self._handle_voice_event(msg_inst)
        elif isinstance(msg_inst, VoiceAssistantAnnounceRequest):
            self._handle_announce_request(msg_inst)
        elif isinstance(msg_inst, VoiceAssistantTimerEventResponse):
            self._handle_timer_event(msg_inst)
        elif isinstance(msg_inst, VoiceAssistantConfigurationRequest):
            self._handle_voice_config(msg_inst)
        elif isinstance(msg_inst, VoiceAssistantSetConfiguration):
            self._handle_set_voice_config(msg_inst)
        # Entity messages
        else:
            msgs = list(self.handle_message(msg_inst))
            if msgs:
                self.send_messages(msgs)

    def _handle_hello(self, msg: HelloRequest) -> None:
        """Handle Hello request"""
        logger.debug(f"Client Hello: {msg.client_info}, API {msg.api_version_major}.{msg.api_version_minor}")
        self.send_messages(
            [
                HelloResponse(
                    api_version_major=1,
                    api_version_minor=10,
                    name=self.state.name,
                )
            ]
        )

    def _handle_auth(self, msg: AuthenticationRequest) -> None:
        """Handle authentication request"""
        logger.debug("Client authentication")
        self.send_messages([AuthenticationResponse()])

    def _handle_disconnect(self, msg: DisconnectRequest) -> None:
        """Handle disconnect request"""
        logger.debug("Client requested disconnect")
        self.send_messages([DisconnectResponse()])
        if self._transport:
            self._transport.close()

    # ========== Voice Assistant Event Processing ==========

    # ---------- transport ----------

    def send_messages(self, msgs: List[message.Message]) -> None:
        """Send messages to client"""
        if self._writelines is None:
            return

        packets = [(PROTO_TO_MESSAGE_TYPE[msg.__class__], msg.SerializeToString()) for msg in msgs]

        packet_bytes = make_plain_text_packets(packets)
        if (
            self._loop is not None
            and self._loop_thread_id is not None
            and threading.get_ident() != self._loop_thread_id
        ):
            self._loop.call_soon_threadsafe(self._writelines, packet_bytes)
            return

        self._writelines(packet_bytes)


class ESPHomeServer:
    """
    ESPHome API Server

    Uses asyncio.Protocol architecture
    """

    DEFAULT_PORT = 6053

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = DEFAULT_PORT,
        device_name: str = None,
        state: ServerState = None,
    ):
        self.host = host
        self.port = port

        # Create or use provided state
        if device_name is None:
            device_name = socket.gethostname().split(".")[0]

        if state is None:
            self.state = create_default_state(device_name)
        else:
            self.state = state

        self.server: Optional[asyncio.Server] = None
        self._is_running = False
        self._protocol: Optional[ESPHomeProtocol] = None
        self._phase_callback: Optional[Callable[[str], None]] = None
        self._muted_callback: Optional[Callable[[bool], None]] = None
        self._conversation_callback: Optional[Callable[[str, str], None]] = None

    def set_phase_callback(self, callback: Optional[Callable[[str], None]]) -> None:
        self._phase_callback = callback
        if self._protocol:
            self._protocol.set_phase_callback(callback)

    def set_muted_callback(self, callback: Optional[Callable[[bool], None]]) -> None:
        self._muted_callback = callback
        if self._protocol:
            self._protocol.set_muted_callback(callback)

    def set_conversation_callback(self, callback: Optional[Callable[[str, str], None]]) -> None:
        self._conversation_callback = callback
        if self._protocol:
            self._protocol.set_conversation_callback(callback)

    async def start(self) -> bool:
        """Start server"""
        try:
            logger.info(f"Starting ESPHome API server @ {self.host}:{self.port}")

            loop = asyncio.get_running_loop()

            def protocol_factory():
                self._protocol = ESPHomeProtocol(self.state)
                if self._phase_callback:
                    self._protocol.set_phase_callback(self._phase_callback)
                if self._muted_callback:
                    self._protocol.set_muted_callback(self._muted_callback)
                if self._conversation_callback:
                    self._protocol.set_conversation_callback(self._conversation_callback)
                return self._protocol

            self.server = await loop.create_server(
                protocol_factory,
                host=self.host,
                port=self.port,
            )

            self._is_running = True
            logger.info("ESPHome API server started")
            logger.info(f"Listening address: {self.host}:{self.port}")
            logger.info(f"Device name: {self.state.name}")
            logger.info("Waiting for Home Assistant connection...")

            return True

        except Exception as e:
            logger.error(f"Failed to start server: {e}")
            return False

    async def stop(self) -> None:
        """Stop server"""
        self._is_running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        logger.info("ESPHome API server stopped")

    async def serve_forever(self) -> None:
        """Run server continuously"""
        if not self.server:
            raise RuntimeError("Server not started")

        async with self.server:
            await self.server.serve_forever()

    @property
    def is_running(self) -> bool:
        """Whether server is running"""
        return self._is_running

    @property
    def protocol(self) -> Optional[ESPHomeProtocol]:
        """Get current protocol instance"""
        return self._protocol


# Convenience function
async def start_server(
    host: str = "0.0.0.0",
    port: int = ESPHomeServer.DEFAULT_PORT,
    device_name: str = None,
) -> ESPHomeServer:
    """Start ESPHome API server"""
    server = ESPHomeServer(host, port, device_name)
    success = await server.start()
    if not success:
        raise RuntimeError("Failed to start server")
    return server
