"""
ESPHome API Protocol Implementation

References linux-voice-assistant's satellite.py and api_server.py
Uses asyncio.Protocol architecture, implements complete Voice Assistant state machine
"""

import asyncio
import logging
import socket
from collections.abc import Iterable
from typing import Dict, List, Optional, Set

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
from aioesphomeapi.model import (
    VoiceAssistantEventType,
    VoiceAssistantFeature,
    VoiceAssistantTimerEventType,
)
from google.protobuf import message

from .models import ServerState, create_default_state

# Message type mapping
PROTO_TO_MESSAGE_TYPE = {v: k for k, v in MESSAGE_TYPE_TO_PROTO.items()}

logger = logging.getLogger(__name__)


class ESPHomeProtocol(asyncio.Protocol):
    """
    ESPHome API Protocol Handler

    References linux-voice-assistant's VoiceSatelliteProtocol implementation
    Implements complete Voice Assistant state machine
    """

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

        # Voice Assistant state machine
        self._is_streaming_audio = False
        self._tts_url: Optional[str] = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_finished = False
        self._is_playing_tts = False  # Flag to pause wake word detection during TTS playback

        # Audio recorder (lazy load)
        self._audio_recorder = None
        self._audio_streaming_task: Optional[asyncio.Task] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None

        # External wake word cache
        self._external_wake_words: Dict[str, any] = {}

        # Module instances (lazy load)
        self._monitor = None
        self._media_player_entity = None
        self._button_manager = None
        self._service_manager = None

        logger.debug(f"ESPHome protocol initialized: {self.state.name}")

    # ========== Connection Lifecycle ==========

    def connection_made(self, transport) -> None:
        """New connection established"""
        self._transport = transport
        self._writelines = transport.writelines
        self._event_loop = asyncio.get_event_loop()
        peername = transport.get_extra_info("peername")
        logger.info(f"📱 New client connected: {peername}")

    def connection_lost(self, exc) -> None:
        """Connection lost"""
        logger.debug("Client disconnected")
        self._transport = None
        self._writelines = None

        # Reset streaming state (main recorder continues)
        self._is_streaming_audio = False
        self._tts_url = None
        self._tts_played = False
        self._continue_conversation = False

        # Restore volume (if previously ducked)
        # self.unduck()  # Duck feature disabled

    def data_received(self, data: bytes) -> None:
        """Receive data"""
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
                logger.error(f"Invalid preamble: {preamble}")
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

    def _handle_voice_event(self, msg: VoiceAssistantEventResponse) -> None:
        """Handle Voice Assistant event"""
        # Parse event data
        data: Dict[str, str] = {}
        for arg in msg.data:
            data[arg.name] = arg.value

        event_type = VoiceAssistantEventType(msg.event_type)
        self.handle_voice_event(event_type, data)

    def handle_voice_event(self, event_type: VoiceAssistantEventType, data: Dict[str, str]) -> None:
        """
        Handle Voice Assistant event

        References linux-voice-assistant's handle_voice_event
        """
        logger.debug(f"Voice event: type={event_type.name}, data={data}")

        if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START:
            # Conversation started
            self._tts_url = data.get("url")
            self._tts_played = False
            self._continue_conversation = False

        elif event_type in (
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
        ):
            # Speech recognition ended, stop audio stream and recording
            logger.info(f"🎤 Received {event_type.name}, clearing streaming flag")
            self._is_streaming_audio = False
            self._stop_audio_streaming()
            logger.debug("🎤 Speech recognition ended, stopping recording")

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_PROGRESS:
            # Intent processing progress
            if data.get("tts_start_streaming") == "1":
                # Start playing TTS early
                self.play_tts()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_END:
            # Intent processing ended
            if data.get("continue_conversation") == "1":
                self._continue_conversation = True

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            # TTS generation ended
            self._tts_url = data.get("url")
            self.play_tts()

        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END:
            # Conversation ended
            logger.info("🎤 Received RUN_END, clearing streaming flag")
            self._is_streaming_audio = False
            self._stop_audio_streaming()
            if not self._tts_played:
                self._tts_finished()
            self._tts_played = False

        # TODO: Handle error events

    def _handle_timer_event(self, msg: VoiceAssistantTimerEventResponse) -> None:
        """Handle timer event"""
        event_type = VoiceAssistantTimerEventType(msg.event_type)
        self.handle_timer_event(event_type, msg)

    def handle_timer_event(self, event_type: VoiceAssistantTimerEventType, msg) -> None:
        """
        Handle timer event

        References linux-voice-assistant's handle_timer_event
        """
        logger.debug(f"Timer event: type={event_type.name}")

        if event_type == VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED:
            if not self._timer_finished:
                # Add stop word to active wake words
                if self.state.stop_word:
                    self.state.active_wake_words.add(self.state.stop_word.id)
                self._timer_finished = True
                # self.duck()  # Duck feature disabled
                self._play_timer_finished()

    # ========== Voice Assistant Configuration ==========

    def _handle_voice_config(self, msg: VoiceAssistantConfigurationRequest) -> None:
        """Handle voice assistant configuration request"""
        # Build available wake words list
        available_wake_words = [
            VoiceAssistantWakeWord(
                id=ww.id,
                wake_word=ww.wake_word,
                trained_languages=ww.trained_languages,
            )
            for ww in self.state.available_wake_words.values()
        ]

        # Process external wake words
        for eww in msg.external_wake_words:
            if eww.model_type != "micro":
                continue
            available_wake_words.append(
                VoiceAssistantWakeWord(
                    id=eww.id,
                    wake_word=eww.wake_word,
                    trained_languages=eww.trained_languages,
                )
            )
            self._external_wake_words[eww.id] = eww

        response = VoiceAssistantConfigurationResponse(
            available_wake_words=available_wake_words,
            active_wake_words=list(self.state.active_wake_words),
            max_active_wake_words=2,
        )

        self.send_messages([response])
        logger.info("✅ Connected to Home Assistant")

    def _handle_set_voice_config(self, msg: VoiceAssistantSetConfiguration) -> None:
        """Handle set voice assistant configuration"""
        active_wake_words: Set[str] = set()

        for wake_word_id in msg.active_wake_words:
            if wake_word_id in self.state.wake_words:
                active_wake_words.add(wake_word_id)
                continue

            model_info = self.state.available_wake_words.get(wake_word_id)
            if model_info:
                logger.debug(f"Setting wake word: {wake_word_id}")
                active_wake_words.add(wake_word_id)
                break

        self.state.active_wake_words = active_wake_words
        self.state.preferences.active_wake_words = list(active_wake_words)
        self.state.save_preferences()
        self.state.wake_words_changed = True

        logger.info(f"🎤 Active wake words updated: {active_wake_words}")

    # ========== Announcement Processing ==========

    def _handle_announce_request(self, msg: VoiceAssistantAnnounceRequest) -> None:
        """
        Handle voice announcement request

        References linux-voice-assistant's handle_message VoiceAssistantAnnounceRequest handling
        """
        logger.info(f"Received announcement request: {msg.text}")

        # Build playlist
        urls = []
        if msg.preannounce_media_id:
            urls.append(msg.preannounce_media_id)
        urls.append(msg.media_id)

        # Set continue conversation flag
        self._continue_conversation = msg.start_conversation

        # Add stop word
        if self.state.stop_word:
            self.state.active_wake_words.add(self.state.stop_word.id)

        # Duck volume and play
        # self.duck()  # Duck feature disabled

        # Play audio
        if urls:
            self._play_announcement(urls)
        else:
            # No audio, complete directly
            self._tts_finished()

    def _play_announcement(self, urls: List[str]) -> None:
        """Play announcement audio"""
        if not urls:
            self._tts_finished()
            return

        # Play first URL
        url = urls[0]
        remaining = urls[1:]

        def on_done():
            if remaining:
                self._play_announcement(remaining)
            else:
                self._tts_finished()

        self.state.tts_player.play(url, done_callback=on_done)

    # ========== Audio Control ==========

    def _get_audio_recorder(self):
        """Get or create audio recorder"""
        if self._audio_recorder is None:
            from src.voice.audio_recorder import AudioRecorder

            self._audio_recorder = AudioRecorder()
            logger.debug("🎤 Audio recorder initialized")
        return self._audio_recorder

    def _start_audio_streaming(self) -> None:
        """Start audio streaming (audio is handled by main program's recorder)"""
        # Main program's recorder will send audio when _is_streaming_audio is True
        logger.debug("🎤 Audio streaming started (main recorder will send audio)")

    def _stop_audio_streaming(self) -> None:
        """Stop audio streaming"""
        # Main program's recorder continues running, just clear the flag
        logger.debug("🎤 Audio streaming stopped")

    def handle_audio(self, audio_chunk: bytes) -> None:
        """
        Handle audio chunk

        Only send audio when in streaming state
        """
        if not self._is_streaming_audio:
            return

        # Log first few audio chunks
        if not hasattr(self, "_audio_chunks_sent"):
            self._audio_chunks_sent = 0
        self._audio_chunks_sent += 1
        if self._audio_chunks_sent <= 5:
            logger.info(f"🎤 Sending audio chunk #{self._audio_chunks_sent}: {len(audio_chunk)} bytes")

        self.send_messages([VoiceAssistantAudio(data=audio_chunk)])

    def wakeup(self, wake_word_phrase: str = "") -> None:
        """
        Wake word detection callback

        References linux-voice-assistant's wakeup
        """
        if self._timer_finished:
            # If timer is ringing, stop timer
            self._timer_finished = False
            self.state.tts_player.stop()
            logger.debug("Stopped timer sound")
            return

        logger.info(f"🎤 Wake word triggered: {wake_word_phrase}")
        logger.info(f"🎤 Current streaming state before wakeup: {self._is_streaming_audio}")

        # Send voice assistant request
        logger.debug("Sending VoiceAssistantRequest(start=True)")
        self.send_messages([VoiceAssistantRequest(start=True, wake_word_phrase=wake_word_phrase)])

        # Duck volume
        # self.duck()  # Duck feature disabled

        # Start audio stream
        self._is_streaming_audio = True
        logger.info("🎤 Set streaming to True")

        # Start microphone recording
        self._start_audio_streaming()

        # Play wakeup sound
        if self.state.wakeup_sound:
            logger.debug(f"Playing wakeup sound: {self.state.wakeup_sound}")
            self.state.tts_player.play(self.state.wakeup_sound)
        else:
            logger.warning("Wakeup sound not set")

    def stop(self) -> None:
        """Stop current operation"""
        if self.state.stop_word:
            self.state.active_wake_words.discard(self.state.stop_word.id)
        self.state.tts_player.stop()

        if self._timer_finished:
            self._timer_finished = False
            logger.debug("Stopped timer sound")
        else:
            logger.debug("Manually stopped TTS")
            self._tts_finished()

    def play_tts(self) -> None:
        """Play TTS response"""
        if not self._tts_url or self._tts_played:
            return

        self._tts_played = True
        self._is_playing_tts = True  # Mark that TTS is playing
        logger.info(f"Playing TTS: {self._tts_url}")

        # Add stop word
        if self.state.stop_word:
            self.state.active_wake_words.add(self.state.stop_word.id)

        self.state.tts_player.play(self._tts_url, done_callback=self._tts_finished)

    def duck(self) -> None:
        """Lower volume (disabled)"""
        pass  # Duck feature disabled

    def unduck(self) -> None:
        """Restore volume (disabled)"""
        pass  # Unduck feature disabled

    def _tts_finished(self) -> None:
        """TTS playback finished callback"""
        self._is_playing_tts = False  # Mark that TTS is no longer playing

        # Remove stop word
        if self.state.stop_word:
            self.state.active_wake_words.discard(self.state.stop_word.id)

        # Send completion message
        self.send_messages([VoiceAssistantAnnounceFinished()])

        if self._continue_conversation:
            # Continue conversation
            self.send_messages([VoiceAssistantRequest(start=True)])
            self._is_streaming_audio = True

            # Play wakeup sound to prompt user to speak, then start recording
            if self.state.wakeup_sound:
                logger.debug("Playing wakeup sound for continue conversation")
                self.state.tts_player.play(self.state.wakeup_sound, done_callback=self._start_audio_streaming)
            else:
                # No wakeup sound, start recording directly
                self._start_audio_streaming()

            logger.debug("Continuing conversation")
        else:
            # Restore volume
            # self.unduck()  # Duck feature disabled
            pass

        logger.debug("TTS playback finished")

    def _play_timer_finished(self) -> None:
        """Play timer finished sound"""
        if not self._timer_finished:
            # self.unduck()  # Duck feature disabled
            return

        # Loop play timer sound
        def on_done():
            import time

            time.sleep(1.0)
            self._play_timer_finished()

        if self.state.timer_finished_sound:
            self.state.tts_player.play(self.state.timer_finished_sound, done_callback=on_done)

    # ========== Entity Message Processing ==========

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """Handle entity-related messages"""
        if isinstance(msg, DeviceInfoRequest):
            # Get version from src.__init__
            try:
                from src import __version__

                version = __version__
            except Exception:
                version = "unknown"

            yield DeviceInfoResponse(
                uses_password=False,
                name=self.state.name,
                mac_address=self.state.mac_address,
                project_version=version,
                voice_assistant_feature_flags=(
                    VoiceAssistantFeature.VOICE_ASSISTANT
                    | VoiceAssistantFeature.API_AUDIO
                    | VoiceAssistantFeature.ANNOUNCE
                    | VoiceAssistantFeature.START_CONVERSATION
                    | VoiceAssistantFeature.TIMERS
                ),
            )
        elif isinstance(
            msg,
            (
                ListEntitiesRequest,
                SubscribeHomeAssistantStatesRequest,
                MediaPlayerCommandRequest,
                ButtonCommandRequest,
                ExecuteServiceRequest,
            ),
        ):
            # Handle entity messages
            yield from self._handle_entity_message(msg)

            if isinstance(msg, ListEntitiesRequest):
                yield ListEntitiesDoneResponse()

    def _handle_entity_message(self, msg: message.Message) -> Iterable[message.Message]:
        """Handle entity messages"""
        # Get Windows Monitor
        if self._monitor is None:
            from src.sensors.windows_monitor import WindowsMonitor

            self._monitor = WindowsMonitor()

        # Get MediaPlayer entity
        if self._media_player_entity is None:
            from src.sensors.media_player import MediaPlayerEntity

            self._media_player_entity = MediaPlayerEntity(
                server=self,
                key=10,
                name="Media Player",
                object_id="windows_media_player",
            )

        # Get button manager
        if self._button_manager is None:
            from src.commands.button_entity import ButtonEntityManager

            self._button_manager = ButtonEntityManager()

        # Get service manager
        if self._service_manager is None:
            from src.notify.service_entity import ServiceEntityManager

            self._service_manager = ServiceEntityManager()

        if isinstance(msg, ListEntitiesRequest):
            # Send sensor entity definitions
            for entity_def in self._monitor.get_esp_entity_definitions():
                if not isinstance(entity_def, ListEntitiesDoneResponse):
                    yield entity_def
            # Send MediaPlayer entity definition
            yield self._media_player_entity.get_entity_definition()
            # Send button entity definitions
            for btn_def in self._button_manager.get_entity_definitions():
                yield btn_def
            # Send service entity definitions
            for svc_def in self._service_manager.get_entity_definitions():
                yield svc_def

        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            # Send sensor states
            for state in self._monitor.get_esp_sensor_states():
                yield state
            # Send MediaPlayer state
            yield self._media_player_entity.get_state()

        elif isinstance(msg, MediaPlayerCommandRequest):
            # Handle MediaPlayer command
            yield from self._media_player_entity.handle_message(msg)

        elif isinstance(msg, ButtonCommandRequest):
            # Handle button command
            yield from self._button_manager.handle_message(msg)

        elif isinstance(msg, ExecuteServiceRequest):
            # Handle service execution
            yield from self._service_manager.handle_message(msg)

    # ========== Message Sending ==========

    def send_messages(self, msgs: List[message.Message]) -> None:
        """Send messages to client"""
        if self._writelines is None:
            return

        from aioesphomeapi._frame_helper.packets import make_plain_text_packets

        packets = [(PROTO_TO_MESSAGE_TYPE[msg.__class__], msg.SerializeToString()) for msg in msgs]

        packet_bytes = make_plain_text_packets(packets)
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

    async def start(self) -> bool:
        """Start server"""
        try:
            logger.info(f"Starting ESPHome API server @ {self.host}:{self.port}")

            loop = asyncio.get_event_loop()

            def protocol_factory():
                self._protocol = ESPHomeProtocol(self.state)
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
