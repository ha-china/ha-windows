"""
ESPHome API 协议实现

参考 linux-voice-assistant 的 satellite.py 和 api_server.py
使用 asyncio.Protocol 架构，实现完整的 Voice Assistant 状态机
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

# 消息类型映射
PROTO_TO_MESSAGE_TYPE = {v: k for k, v in MESSAGE_TYPE_TO_PROTO.items()}

logger = logging.getLogger(__name__)


def _get_mac_address() -> str:
    """获取 MAC 地址（有冒号格式）"""
    try:
        mac = uuid.getnode()
        return ":".join(f"{(mac >> i) & 0xff:02x}" for i in range(40, -1, -8))
    except Exception:
        return "00:00:00:00:00:01"


def _load_available_wake_words() -> Dict[str, AvailableWakeWord]:
    """从 src/wakewords 目录加载所有可用的唤醒词"""
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
    """创建默认的服务器状态"""
    from pathlib import Path
    
    available_wake_words = _load_available_wake_words()
    
    # 默认激活 okay_nabu，如果没有则用第一个
    default_active = set()
    if 'okay_nabu' in available_wake_words:
        default_active.add('okay_nabu')
    elif available_wake_words:
        default_active.add(next(iter(available_wake_words.keys())))
    
    # 音效文件路径
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
    
    # 加载保存的偏好设置
    state.load_preferences()
    if state.preferences.active_wake_words:
        # 使用保存的唤醒词设置
        saved_active = set(state.preferences.active_wake_words)
        # 只保留仍然可用的唤醒词
        valid_active = saved_active & set(available_wake_words.keys())
        if valid_active:
            state.active_wake_words = valid_active
            logger.info(f"Loaded saved wake word preference: {valid_active}")
    
    return state


class ESPHomeProtocol(asyncio.Protocol):
    """
    ESPHome API 协议处理器
    
    参考 linux-voice-assistant 的 VoiceSatelliteProtocol 实现
    实现完整的 Voice Assistant 状态机
    """

    def __init__(self, state: ServerState):
        super().__init__()
        
        self.state = state
        self.state.satellite = self
        
        # 协议缓冲区
        self._buffer: Optional[bytes] = None
        self._buffer_len: int = 0
        self._pos: int = 0
        self._transport = None
        self._writelines = None
        
        # Voice Assistant 状态机
        self._is_streaming_audio = False
        self._tts_url: Optional[str] = None
        self._tts_played = False
        self._continue_conversation = False
        self._timer_finished = False
        
        # 音频录制器（懒加载）
        self._audio_recorder = None
        self._audio_streaming_task: Optional[asyncio.Task] = None
        self._event_loop: Optional[asyncio.AbstractEventLoop] = None
        
        # 外部唤醒词缓存
        self._external_wake_words: Dict[str, any] = {}
        
        # 模块实例（懒加载）
        self._monitor = None
        self._media_player_entity = None
        self._button_manager = None
        self._service_manager = None
        
        logger.info(f"ESPHome 协议初始化: {self.state.name}")

    # ========== 连接生命周期 ==========
    
    def connection_made(self, transport) -> None:
        """新连接建立"""
        self._transport = transport
        self._writelines = transport.writelines
        self._event_loop = asyncio.get_event_loop()
        peername = transport.get_extra_info('peername')
        logger.info(f"📱 新客户端连接: {peername}")

    def connection_lost(self, exc) -> None:
        """连接断开"""
        logger.info("客户端断开连接")
        self._transport = None
        self._writelines = None
        
        # 停止音频流
        self._stop_audio_streaming()
        
        # 重置状态
        self._is_streaming_audio = False
        self._tts_url = None
        self._tts_played = False
        self._continue_conversation = False
        
        # 恢复音量（如果之前 ducked）
        self.unduck()

    def data_received(self, data: bytes) -> None:
        """接收数据"""
        if self._buffer is None:
            self._buffer = data
            self._buffer_len = len(data)
        else:
            self._buffer += data
            self._buffer_len += len(data)

        # 处理缓冲区中的所有完整消息
        while self._buffer_len >= 3:
            self._pos = 0

            # 读取 preamble (必须是 0x00)
            preamble = self._read_varuint()
            if preamble != 0x00:
                logger.error(f"无效的 preamble: {preamble}")
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

    # ========== 缓冲区操作 ==========
    
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

    # ========== 消息处理 ==========
    
    def _process_packet(self, msg_type: int, packet_data: bytes) -> None:
        """处理接收到的数据包"""
        msg_class = MESSAGE_TYPE_TO_PROTO.get(msg_type)
        if msg_class is None:
            logger.warning(f"未知消息类型: {msg_type}")
            return

        msg_inst = msg_class.FromString(packet_data)
        
        # 基础协议消息
        if isinstance(msg_inst, HelloRequest):
            self._handle_hello(msg_inst)
        elif isinstance(msg_inst, AuthenticationRequest):
            self._handle_auth(msg_inst)
        elif isinstance(msg_inst, DisconnectRequest):
            self._handle_disconnect(msg_inst)
        elif isinstance(msg_inst, PingRequest):
            self.send_messages([PingResponse()])
        # Voice Assistant 消息
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
        # 实体消息
        else:
            msgs = list(self.handle_message(msg_inst))
            if msgs:
                self.send_messages(msgs)

    def _handle_hello(self, msg: HelloRequest) -> None:
        """处理 Hello 请求"""
        logger.info(f"客户端 Hello: {msg.client_info}, API {msg.api_version_major}.{msg.api_version_minor}")
        self.send_messages([
            HelloResponse(
                api_version_major=1,
                api_version_minor=10,
                name=self.state.name,
            )
        ])

    def _handle_auth(self, msg: AuthenticationRequest) -> None:
        """处理认证请求"""
        logger.info("客户端认证")
        self.send_messages([AuthenticationResponse()])

    def _handle_disconnect(self, msg: DisconnectRequest) -> None:
        """处理断开连接请求"""
        logger.info("客户端请求断开")
        self.send_messages([DisconnectResponse()])
        if self._transport:
            self._transport.close()

    # ========== Voice Assistant 事件处理 ==========
    
    def _handle_voice_event(self, msg: VoiceAssistantEventResponse) -> None:
        """处理 Voice Assistant 事件"""
        # 解析事件数据
        data: Dict[str, str] = {}
        for arg in msg.data:
            data[arg.name] = arg.value
        
        event_type = VoiceAssistantEventType(msg.event_type)
        self.handle_voice_event(event_type, data)

    def handle_voice_event(self, event_type: VoiceAssistantEventType, data: Dict[str, str]) -> None:
        """
        处理 Voice Assistant 事件
        
        参考 linux-voice-assistant 的 handle_voice_event
        """
        logger.debug(f"Voice event: type={event_type.name}, data={data}")
        
        if event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_START:
            # 对话开始
            self._tts_url = data.get("url")
            self._tts_played = False
            self._continue_conversation = False
            
        elif event_type in (
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_VAD_END,
            VoiceAssistantEventType.VOICE_ASSISTANT_STT_END,
        ):
            # 语音识别结束，停止音频流和录制
            self._is_streaming_audio = False
            self._stop_audio_streaming()
            logger.info("🎤 语音识别结束，停止录音")
            
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_PROGRESS:
            # 意图处理进度
            if data.get("tts_start_streaming") == "1":
                # 提前开始播放 TTS
                self.play_tts()
                
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_INTENT_END:
            # 意图处理结束
            if data.get("continue_conversation") == "1":
                self._continue_conversation = True
                
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_TTS_END:
            # TTS 生成结束
            self._tts_url = data.get("url")
            self.play_tts()
            
        elif event_type == VoiceAssistantEventType.VOICE_ASSISTANT_RUN_END:
            # 对话结束
            self._is_streaming_audio = False
            self._stop_audio_streaming()
            if not self._tts_played:
                self._tts_finished()
            self._tts_played = False
        
        # TODO: 处理错误事件

    def _handle_timer_event(self, msg: VoiceAssistantTimerEventResponse) -> None:
        """处理定时器事件"""
        event_type = VoiceAssistantTimerEventType(msg.event_type)
        self.handle_timer_event(event_type, msg)

    def handle_timer_event(self, event_type: VoiceAssistantTimerEventType, msg) -> None:
        """
        处理定时器事件
        
        参考 linux-voice-assistant 的 handle_timer_event
        """
        logger.debug(f"Timer event: type={event_type.name}")
        
        if event_type == VoiceAssistantTimerEventType.VOICE_ASSISTANT_TIMER_FINISHED:
            if not self._timer_finished:
                # 添加 stop word 到活动唤醒词
                if self.state.stop_word:
                    self.state.active_wake_words.add(self.state.stop_word.id)
                self._timer_finished = True
                self.duck()
                self._play_timer_finished()

    # ========== Voice Assistant 配置 ==========
    
    def _handle_voice_config(self, msg: VoiceAssistantConfigurationRequest) -> None:
        """处理语音助手配置请求"""
        # 构建可用唤醒词列表
        available_wake_words = [
            VoiceAssistantWakeWord(
                id=ww.id,
                wake_word=ww.wake_word,
                trained_languages=ww.trained_languages,
            )
            for ww in self.state.available_wake_words.values()
        ]
        
        # 处理外部唤醒词
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
        logger.info("✅ 已连接到 Home Assistant")

    def _handle_set_voice_config(self, msg: VoiceAssistantSetConfiguration) -> None:
        """处理设置语音助手配置"""
        active_wake_words: Set[str] = set()
        
        for wake_word_id in msg.active_wake_words:
            if wake_word_id in self.state.wake_words:
                active_wake_words.add(wake_word_id)
                continue
            
            model_info = self.state.available_wake_words.get(wake_word_id)
            if model_info:
                logger.info(f"设置唤醒词: {wake_word_id}")
                active_wake_words.add(wake_word_id)
                break
        
        self.state.active_wake_words = active_wake_words
        self.state.preferences.active_wake_words = list(active_wake_words)
        self.state.save_preferences()
        self.state.wake_words_changed = True
        
        logger.info(f"🎤 活动唤醒词已更新: {active_wake_words}")

    # ========== Announcement 处理 ==========
    
    def _handle_announce_request(self, msg: VoiceAssistantAnnounceRequest) -> None:
        """
        处理语音播报请求
        
        参考 linux-voice-assistant 的 handle_message 中的 VoiceAssistantAnnounceRequest 处理
        """
        logger.info(f"收到播报请求: {msg.text}")
        
        # 构建播放列表
        urls = []
        if msg.preannounce_media_id:
            urls.append(msg.preannounce_media_id)
        urls.append(msg.media_id)
        
        # 设置继续对话标志
        self._continue_conversation = msg.start_conversation
        
        # 添加 stop word
        if self.state.stop_word:
            self.state.active_wake_words.add(self.state.stop_word.id)
        
        # Duck 音量并播放
        self.duck()
        
        # 播放音频
        if urls:
            self._play_announcement(urls)
        else:
            # 没有音频，直接完成
            self._tts_finished()

    def _play_announcement(self, urls: List[str]) -> None:
        """播放播报音频"""
        if not urls:
            self._tts_finished()
            return
        
        # 播放第一个 URL
        url = urls[0]
        remaining = urls[1:]
        
        def on_done():
            if remaining:
                self._play_announcement(remaining)
            else:
                self._tts_finished()
        
        self.state.tts_player.play(url, done_callback=on_done)

    # ========== 音频控制 ==========
    
    def _get_audio_recorder(self):
        """获取或创建音频录制器"""
        if self._audio_recorder is None:
            from src.voice.audio_recorder import AudioRecorder
            self._audio_recorder = AudioRecorder()
            logger.info("🎤 音频录制器已初始化")
        return self._audio_recorder

    def _start_audio_streaming(self) -> None:
        """启动音频流式传输"""
        if self._audio_streaming_task is not None:
            logger.warning("音频流已在运行")
            return
        
        recorder = self._get_audio_recorder()
        
        # 定义音频回调 - 在录音线程中调用
        def on_audio_chunk(audio_data: bytes):
            if self._is_streaming_audio and self._event_loop:
                # 在事件循环中发送音频
                self._event_loop.call_soon_threadsafe(
                    lambda: self.handle_audio(audio_data)
                )
        
        # 启动录音
        try:
            recorder.start_recording(audio_callback=on_audio_chunk)
            logger.info("🎤 开始录制麦克风音频")
        except Exception as e:
            logger.error(f"启动录音失败: {e}")

    def _stop_audio_streaming(self) -> None:
        """停止音频流式传输"""
        if self._audio_recorder and self._audio_recorder.is_recording:
            self._audio_recorder.stop_recording()
            logger.info("🎤 停止录制麦克风音频")

    def handle_audio(self, audio_chunk: bytes) -> None:
        """
        处理音频块
        
        只在 streaming 状态时发送音频
        """
        if not self._is_streaming_audio:
            return
        
        self.send_messages([VoiceAssistantAudio(data=audio_chunk)])

    def wakeup(self, wake_word_phrase: str = "") -> None:
        """
        唤醒词检测回调
        
        参考 linux-voice-assistant 的 wakeup
        """
        if self._timer_finished:
            # 如果定时器正在响，停止定时器
            self._timer_finished = False
            self.state.tts_player.stop()
            logger.debug("停止定时器音效")
            return
        
        logger.info(f"🎤 唤醒词触发: {wake_word_phrase}")
        
        # 发送语音助手请求
        logger.info("发送 VoiceAssistantRequest(start=True)")
        self.send_messages([
            VoiceAssistantRequest(start=True, wake_word_phrase=wake_word_phrase)
        ])
        
        # Duck 音量
        self.duck()
        
        # 开始音频流
        self._is_streaming_audio = True
        
        # 启动麦克风录制
        self._start_audio_streaming()
        
        # 播放唤醒音效
        if self.state.wakeup_sound:
            logger.info(f"播放唤醒音: {self.state.wakeup_sound}")
            self.state.tts_player.play(self.state.wakeup_sound)
        else:
            logger.warning("未设置唤醒音")

    def stop(self) -> None:
        """停止当前操作"""
        if self.state.stop_word:
            self.state.active_wake_words.discard(self.state.stop_word.id)
        self.state.tts_player.stop()
        
        if self._timer_finished:
            self._timer_finished = False
            logger.debug("停止定时器音效")
        else:
            logger.debug("手动停止 TTS")
            self._tts_finished()

    def play_tts(self) -> None:
        """播放 TTS 响应"""
        if not self._tts_url or self._tts_played:
            return
        
        self._tts_played = True
        logger.info(f"播放 TTS: {self._tts_url}")
        
        # 添加 stop word
        if self.state.stop_word:
            self.state.active_wake_words.add(self.state.stop_word.id)
        
        self.state.tts_player.play(self._tts_url, done_callback=self._tts_finished)

    def duck(self) -> None:
        """降低音量（已禁用）"""
        pass  # 禁用 duck 功能

    def unduck(self) -> None:
        """恢复音量（已禁用）"""
        pass  # 禁用 unduck 功能

    def _tts_finished(self) -> None:
        """TTS 播放完成回调"""
        # 移除 stop word
        if self.state.stop_word:
            self.state.active_wake_words.discard(self.state.stop_word.id)
        
        # 发送完成消息
        self.send_messages([VoiceAssistantAnnounceFinished()])
        
        if self._continue_conversation:
            # 继续对话
            self.send_messages([VoiceAssistantRequest(start=True)])
            self._is_streaming_audio = True
            # 重新启动麦克风录制
            self._start_audio_streaming()
            logger.debug("继续对话，重新启动录音")
        else:
            # 恢复音量
            self.unduck()
        
        logger.debug("TTS 播放完成")

    def _play_timer_finished(self) -> None:
        """播放定时器完成音效"""
        if not self._timer_finished:
            self.unduck()
            return
        
        # 循环播放定时器音效
        def on_done():
            import time
            time.sleep(1.0)
            self._play_timer_finished()
        
        if self.state.timer_finished_sound:
            self.state.tts_player.play(self.state.timer_finished_sound, done_callback=on_done)

    # ========== 实体消息处理 ==========
    
    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """处理实体相关消息"""
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
            # 处理实体消息
            yield from self._handle_entity_message(msg)
            
            if isinstance(msg, ListEntitiesRequest):
                yield ListEntitiesDoneResponse()

    def _handle_entity_message(self, msg: message.Message) -> Iterable[message.Message]:
        """处理实体消息"""
        # 获取 Windows Monitor
        if self._monitor is None:
            from src.sensors.windows_monitor import WindowsMonitor
            self._monitor = WindowsMonitor()
        
        # 获取 MediaPlayer 实体
        if self._media_player_entity is None:
            from src.sensors.media_player import MediaPlayerEntity
            self._media_player_entity = MediaPlayerEntity(
                server=self,
                key=10,
                name="Media Player",
                object_id="windows_media_player",
            )
        
        # 获取按钮管理器
        if self._button_manager is None:
            from src.commands.button_entity import ButtonEntityManager
            self._button_manager = ButtonEntityManager()
        
        # 获取服务管理器
        if self._service_manager is None:
            from src.notify.service_entity import ServiceEntityManager
            self._service_manager = ServiceEntityManager()
        
        if isinstance(msg, ListEntitiesRequest):
            # 发送传感器实体定义
            for entity_def in self._monitor.get_esp_entity_definitions():
                if not isinstance(entity_def, ListEntitiesDoneResponse):
                    yield entity_def
            # 发送 MediaPlayer 实体定义
            yield self._media_player_entity.get_entity_definition()
            # 发送按钮实体定义
            for btn_def in self._button_manager.get_entity_definitions():
                yield btn_def
            # 发送服务实体定义
            for svc_def in self._service_manager.get_entity_definitions():
                yield svc_def
            
        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            # 发送传感器状态
            for state in self._monitor.get_esp_sensor_states():
                yield state
            # 发送 MediaPlayer 状态
            yield self._media_player_entity.get_state()
            
        elif isinstance(msg, MediaPlayerCommandRequest):
            # 处理 MediaPlayer 命令
            yield from self._media_player_entity.handle_message(msg)
            
        elif isinstance(msg, ButtonCommandRequest):
            # 处理按钮命令
            yield from self._button_manager.handle_message(msg)
            
        elif isinstance(msg, ExecuteServiceRequest):
            # 处理服务执行
            yield from self._service_manager.handle_message(msg)

    # ========== 消息发送 ==========
    
    def send_messages(self, msgs: List[message.Message]) -> None:
        """发送消息给客户端"""
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
    ESPHome API 服务器
    
    使用 asyncio.Protocol 架构
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
        
        # 创建或使用提供的状态
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
        """启动服务器"""
        try:
            logger.info(f"启动 ESPHome API 服务器 @ {self.host}:{self.port}")

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
            logger.info(f"✅ ESPHome API 服务器已启动")
            logger.info(f"   监听地址: {self.host}:{self.port}")
            logger.info(f"   设备名称: {self.state.name}")
            logger.info(f"   等待 Home Assistant 连接...")

            return True

        except Exception as e:
            logger.error(f"❌ 启动服务器失败: {e}")
            return False

    async def stop(self) -> None:
        """停止服务器"""
        self._is_running = False
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None
        logger.info("ESPHome API 服务器已停止")

    async def serve_forever(self) -> None:
        """持续运行服务器"""
        if not self.server:
            raise RuntimeError("服务器未启动")

        async with self.server:
            await self.server.serve_forever()

    @property
    def is_running(self) -> bool:
        """服务器是否运行中"""
        return self._is_running
    
    @property
    def protocol(self) -> Optional[ESPHomeProtocol]:
        """获取当前协议实例"""
        return self._protocol


# 便捷函数
async def start_server(
    host: str = "0.0.0.0",
    port: int = ESPHomeServer.DEFAULT_PORT,
    device_name: str = None,
) -> ESPHomeServer:
    """启动 ESPHome API 服务器"""
    server = ESPHomeServer(host, port, device_name)
    success = await server.start()
    if not success:
        raise RuntimeError("启动服务器失败")
    return server
