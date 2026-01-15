"""
ESPHome API Protocol Implementation

References linux-voice-assistant's satellite.py and api_server.py
Uses asyncio.Protocol architecture, implements complete Voice Assistant state machine
"""

import asyncio
import logging
import socket
import threading
import uuid
from collections.abc import Iterable
from typing import Dict, List, Optional, Set, Callable

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

from .models import ServerState, AvailableWakeWord, WakeWordType, AudioPlayer

# Message type mapping
PROTO_TO_MESSAGE_TYPE = {v: k for k, v in MESSAGE_TYPE_TO_PROTO.items()}

logger = logging.getLogger(__name__)


def _get_mac_address() -> str:
    """Get MAC address (with colons format)"""
    try:
        mac = uuid.getnode()
        return ":".join(f"{(mac >> i) & 0xff:02x}" for i in range(40, -1, -8))
    except Exception:
        return "00:00:00:00:00:01"


def _load_available_wake_words() -> Dict[str, AvailableWakeWord]:
    """Load all available wake words from src/wakewords directory"""
    import json
    from pathlib import Path
    
    wake_words = {}
    wakeword_dir = Path(__file__).parent.parent / "wakewords"
    
    if not wakeword_dir.exists():
        logger.warning(f"Wake word directory not found: {wakeword_dir}")
        return wake_words
    
    for json_file in wakeword_dir.glob("*.json"):
        try:
            with open(json_file, 'r', encoding='utf-8') as f:
                config = json.load(f)
            
            model_id = json_file.stem
            wake_word = config.get('wake_word', model_id)
            trained_languages = config.get('trained_languages', ['en'])
            model_type = config.get('type', 'micro')
            
            ww_type = WakeWordType.MICRO_WAKE_WORD if model_type == 'micro' else WakeWordType.OPEN_WAKE_WORD
            
            wake_words[model_id] = AvailableWakeWord(
                id=model_id,
                type=ww_type,
                wake_word=wake_word,
                trained_languages=trained_languages,
                wake_word_path=json_file,
            )
            logger.debug(f"Loaded wake word: {model_id} -> '{wake_word}'")
            
        except Exception as e:
            logger.error(f"Failed to load wake word config {json_file}: {e}")
    
    logger.info(f"Loaded {len(wake_words)} wake word models")
    return wake_words


def create_default_state(name: str) -> ServerState:
    """Create default server state"""
    from pathlib import Path
    
    available_wake_words = _load_available_wake_words()
    
    # Default activate okay_nabu, if not available use the first one
    default_active = set()
    if 'okay_nabu' in available_wake_words:
        default_active.add('okay_nabu')
    elif available_wake_words:
        default_active.add(next(iter(available_wake_words.keys())))
    
    # Sound file paths
    sounds_dir = Path(__file__).parent.parent / "sounds"
    wakeup_sound = ""
    timer_finished_sound = ""
    
    wakeup_file = sounds_dir / "wake_word_triggered.flac"
    if wakeup_file.exists():
        wakeup_sound = str(wakeup_file)
        logger.info(f"Loaded wakeup sound: {wakeup_sound}")
    else:
        logger.warning(f"Wakeup sound not found: {wakeup_file}")
    
    timer_file = sounds_dir / "timer_finished.flac"
    if timer_file.exists():
        timer_finished_sound = str(timer_file)
    
    state = ServerState(
        name=name,
        mac_address=_get_mac_address(),
        available_wake_words=available_wake_words,
        active_wake_words=default_active,
        wakeup_sound=wakeup_sound,
        timer_finished_sound=timer_finished_sound,
    )
    
    # Load saved preferences
    state.load_preferences()
    if state.preferences.active_wake_words:
        # Use saved wake word settings
        saved_active = set(state.preferences.active_wake_words)
        # Only keep wake words that are still available
        valid_active = saved_active & set(available_wake_words.keys())
        if valid_active:
            state.active_wake_words = valid_active
            logger.info(f"Loaded saved wake word preference: {valid_active}")
    
    return state


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
        
        logger.info(f"ESPHome protocol initialized: {self.state.name}")

    # ========== Connection Lifecycle ==========
    
    def connection_made(self, transport) -> None:
        """New connection established"""
        self._transport = transport
        self._writelines = transport.writelines
        self._event_loop = asyncio.get_event_loop()
        peername = transport.get_extra_info('peername')
        logger.info(f"📱 New client connected: {peername}")

    def connection_lost(self, exc) -> None:
        """Connection lost"""
        logger.info("Client disconnected")
        self._transport = None
        self._writelines = None
        
        # Stop audio stream
        self._stop_audio_streaming()
        
        # Reset state
        self._is_streaming_audio = False
        self._tts_url = None
        self._tts_played = False
        self._continue_conversation = False
        
        # Restore volume (if previously ducked)
        self.unduck()

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
        logger.info(f"Client Hello: {msg.client_info}, API {msg.api_version_major}.{msg.api_version_minor}")
        self.send_messages([
            HelloResponse(
                api_version_major=1,
                api_version_minor=10,
                name=self.state.name,
            )
        ])

    def _handle_auth(self, msg: AuthenticationRequest) -> None:
        """Handle authentication request"""
        logger.info("Client authentication")
        self.send_messages([AuthenticationResponse()])

    def _handle_disconnect(self, msg: DisconnectRequest) -> None:
        """Handle disconnect request"""
        logger.info("Client requested disconnect")
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
            self._is_streaming_audio = False
            self._stop_audio_streaming()
            logger.info("🎤 Speech recognition ended, stopping recording")
            
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
                self.duck()
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
                logger.info(f"Setting wake word: {wake_word_id}")
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
        self.duck()
        
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
            logger.info("🎤 Audio recorder initialized")
        return self._audio_recorder

    def _start_audio_streaming(self) -> None:
        """Start audio streaming"""
        if self._audio_streaming_task is not None:
            logger.warning("Audio stream already running")
            return
        
        recorder = self._get_audio_recorder()
        
        # Define audio callback - called in recording thread
        def on_audio_chunk(audio_data: bytes):
            if self._is_streaming_audio and self._event_loop:
                # Send audio in event loop
                self._event_loop.call_soon_threadsafe(
                    lambda: self.handle_audio(audio_data)
                )
        
        # Start recording
        try:
            recorder.start_recording(audio_callback=on_audio_chunk)
            logger.info("🎤 Started recording microphone audio")
        except Exception as e:
            logger.error(f"Failed to start recording: {e}")

    def _stop_audio_streaming(self) -> None:
        """Stop audio streaming"""
        if self._audio_recorder and self._audio_recorder.is_recording:
            self._audio_recorder.stop_recording()
            logger.info("🎤 Stopped recording microphone audio")

    def handle_audio(self, audio_chunk: bytes) -> None:
        """
        Handle audio chunk
        
        Only send audio when in streaming state
        """
        if not self._is_streaming_audio:
            return
        
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
        
        # Send voice assistant request
        logger.info("Sending VoiceAssistantRequest(start=True)")
        self.send_messages([
            VoiceAssistantRequest(start=True, wake_word_phrase=wake_word_phrase)
        ])
        
        # Duck volume
        self.duck()
        
        # Start audio stream
        self._is_streaming_audio = True
        
        # Start microphone recording
        self._start_audio_streaming()
        
        # Play wakeup sound
        if self.state.wakeup_sound:
            logger.info(f"Playing wakeup sound: {self.state.wakeup_sound}")
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
        # Remove stop word
        if self.state.stop_word:
            self.state.active_wake_words.discard(self.state.stop_word.id)
        
        # Send completion message
        self.send_messages([VoiceAssistantAnnounceFinished()])
        
        if self._continue_conversation:
            # Continue conversation
            self.send_messages([VoiceAssistantRequest(start=True)])
            self._is_streaming_audio = True
            # Restart microphone recording
            self._start_audio_streaming()
            logger.debug("Continuing conversation, restarting recording")
        else:
            # Restore volume
            self.unduck()
        
        logger.debug("TTS playback finished")

    def _play_timer_finished(self) -> None:
        """Play timer finished sound"""
        if not self._timer_finished:
            self.unduck()
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
            yield DeviceInfoResponse(
                uses_password=False,
                name=self.state.name,
                mac_address=self.state.mac_address,
                voice_assistant_feature_flags=(
                    VoiceAssistantFeature.VOICE_ASSISTANT
                    | VoiceAssistantFeature.API_AUDIO
                    | VoiceAssistantFeature.ANNOUNCE
                    | VoiceAssistantFeature.START_CONVERSATION
                    | VoiceAssistantFeature.TIMERS
                ),
            )
        elif isinstance(msg, (ListEntitiesRequest, SubscribeHomeAssistantStatesRequest, MediaPlayerCommandRequest, ButtonCommandRequest, ExecuteServiceRequest)):
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

        packets = [
            (PROTO_TO_MESSAGE_TYPE[msg.__class__], msg.SerializeToString())
            for msg in msgs
        ]

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
            device_name = socket.gethostname().split('.')[0]
        
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
            logger.info(f"✅ ESPHome API server started")
            logger.info(f"   Listening address: {self.host}:{self.port}")
            logger.info(f"   Device name: {self.state.name}")
            logger.info(f"   Waiting for Home Assistant connection...")

            return True

        except Exception as e:
            logger.error(f"❌ Failed to start server: {e}")
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
