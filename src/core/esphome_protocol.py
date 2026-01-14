"""
ESPHome API 协议实现

参考 linux-voice-assistant 的 api_server.py，使用 asyncio.Protocol 架构
"""

import asyncio
import logging
import socket
import uuid
from collections.abc import Iterable
from typing import List, Optional

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
    ListEntitiesMediaPlayerResponse,
    MediaPlayerCommandRequest,
    MediaPlayerStateResponse,
    SubscribeHomeAssistantStatesRequest,
    VoiceAssistantConfigurationRequest,
    VoiceAssistantConfigurationResponse,
    VoiceAssistantEventResponse,
    VoiceAssistantAnnounceRequest,
    VoiceAssistantAnnounceFinished,
    VoiceAssistantRequest,
    VoiceAssistantResponse,
    VoiceAssistantAudio,
    VoiceAssistantSetConfiguration,
    VoiceAssistantWakeWord,
)
from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO
from aioesphomeapi.model import (
    MediaPlayerCommand,
    MediaPlayerState,
    VoiceAssistantFeature,
)
from google.protobuf import message

# 消息类型映射
PROTO_TO_MESSAGE_TYPE = {v: k for k, v in MESSAGE_TYPE_TO_PROTO.items()}

logger = logging.getLogger(__name__)


class ClientInfo:
    """客户端信息"""
    def __init__(self, transport):
        self.transport = transport
        self.remote_address = transport.get_extra_info('peername')
        self.is_authenticated = False
        self.api_version_major = 1
        self.api_version_minor = 0


class ESPHomeProtocol(asyncio.Protocol):
    """
    ESPHome API 协议处理器

    参考 linux-voice-assistant 的 api_server.py 实现
    使用 asyncio.Protocol 架构
    """

    def __init__(self, device_name: str = None):
        super().__init__()

        # 设备信息
        if device_name is None:
            device_name = socket.gethostname()
        self.device_name = device_name

        # MAC 地址
        self.device_mac = self._get_mac_address()

        # 协议状态
        self._buffer: Optional[bytes] = None
        self._buffer_len: int = 0
        self._pos: int = 0
        self._transport = None
        self._writelines = None

        # 客户端信息
        self.client: Optional[ClientInfo] = None

        logger.info(f"ESPHome 协议初始化: {self.device_name}")

    def _get_mac_address(self) -> str:
        """获取 MAC 地址（有冒号格式）"""
        try:
            mac = uuid.getnode()
            return ":".join(f"{(mac >> i) & 0xff:02x}" for i in range(40, -1, -8))
        except Exception:
            return "00:00:00:00:00:01"

    def connection_made(self, transport) -> None:
        """新连接建立"""
        self._transport = transport
        self._writelines = transport.writelines
        self.client = ClientInfo(transport)
        logger.info(f"📱 新客户端连接: {self.client.remote_address}")

    def connection_lost(self, exc) -> None:
        """连接断开"""
        logger.info(f"客户端 {self.client.remote_address if self.client else 'unknown'} 断开连接")
        self._transport = None
        self._writelines = None
        self.client = None

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

            # 读取消息长度
            length = self._read_varuint()
            if length == -1:
                logger.error("无效的 length")
                return

            # 读取消息类型
            msg_type = self._read_varuint()
            if msg_type == -1:
                logger.error("无效的 message type")
                return

            if length == 0:
                # 空消息
                self._remove_from_buffer()
                self.process_packet(msg_type, b"")
                continue

            # 读取消息体
            packet_data = self._read(length)
            if packet_data is None:
                # 数据不完整，等待更多数据
                return

            self._remove_from_buffer()
            self.process_packet(msg_type, packet_data)

    def _read(self, length: int) -> Optional[bytes]:
        """从缓冲区读取指定长度的数据"""
        new_pos = self._pos + length
        if self._buffer_len < new_pos:
            return None

        original_pos = self._pos
        self._pos = new_pos
        return self._buffer[original_pos:new_pos]

    def _read_varuint(self) -> int:
        """从缓冲区读取 varuint 编码的整数"""
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
        """从缓冲区移除已处理的数据"""
        end_of_frame_pos = self._pos
        self._buffer_len -= end_of_frame_pos
        if self._buffer_len == 0:
            self._buffer = None
        else:
            self._buffer = self._buffer[end_of_frame_pos:]

    def process_packet(self, msg_type: int, packet_data: bytes) -> None:
        """处理接收到的数据包"""
        msg_class = MESSAGE_TYPE_TO_PROTO.get(msg_type)
        if msg_class is None:
            logger.warning(f"未知消息类型: {msg_type}")
            return

        msg_inst = msg_class.FromString(packet_data)

        # 处理各种消息类型
        if isinstance(msg_inst, HelloRequest):
            self._handle_hello(msg_inst)
        elif isinstance(msg_inst, AuthenticationRequest):
            self._handle_auth(msg_inst)
        elif isinstance(msg_inst, DisconnectRequest):
            self._handle_disconnect(msg_inst)
        elif isinstance(msg_inst, PingRequest):
            self._handle_ping(msg_inst)
        elif isinstance(msg_inst, DeviceInfoRequest):
            self._handle_device_info(msg_inst)
        elif isinstance(msg_inst, ListEntitiesRequest):
            self._handle_list_entities(msg_inst)
        elif isinstance(msg_inst, SubscribeHomeAssistantStatesRequest):
            self._handle_subscribe_states(msg_inst)
        elif isinstance(msg_inst, MediaPlayerCommandRequest):
            self._handle_media_player_command(msg_inst)
        elif isinstance(msg_inst, VoiceAssistantConfigurationRequest):
            self._handle_voice_assistant_config(msg_inst)
        elif isinstance(msg_inst, VoiceAssistantSetConfiguration):
            self._handle_set_voice_config(msg_inst)
        elif isinstance(msg_inst, VoiceAssistantRequest):
            self._handle_voice_assistant_request(msg_inst)
        elif isinstance(msg_inst, VoiceAssistantAudio):
            self._handle_voice_assistant_audio(msg_inst)
        elif isinstance(msg_inst, VoiceAssistantAnnounceRequest):
            self._handle_announce_request(msg_inst)
        else:
            # 调用 handle_message 处理其他消息
            msgs = self.handle_message(msg_inst)
            if msgs:
                if isinstance(msgs, message.Message):
                    msgs = [msgs]
                self.send_messages(msgs)

    def _handle_hello(self, msg: HelloRequest) -> None:
        """处理 Hello 请求"""
        self.client.api_version_major = msg.api_version_major
        self.client.api_version_minor = msg.api_version_minor

        logger.info(f"客户端发送 Hello:")
        logger.info(f"  - Client Info: {msg.client_info}")
        logger.info(f"  - API Version: {msg.api_version_major}.{msg.api_version_minor}")

        response = HelloResponse()
        response.api_version_major = 1
        response.api_version_minor = 10
        response.server_info = "Windows Assistant"
        response.name = self.device_name

        self.send_messages([response])
        self.client.is_authenticated = True
        logger.info(f"✅ 客户端已完成握手")

    def _handle_auth(self, msg: AuthenticationRequest) -> None:
        """处理认证请求"""
        logger.info(f"客户端请求认证 (has_password={bool(msg.password)})")

        response = AuthenticationResponse()
        response.invalid_password = False

        self.send_messages([response])
        logger.info(f"✅ 客户端已认证")

    def _handle_disconnect(self, msg: DisconnectRequest) -> None:
        """处理断开连接请求"""
        logger.info("客户端请求断开连接")
        self.send_messages([DisconnectResponse()])
        if self._transport:
            self._transport.close()

    def _handle_ping(self, msg: PingRequest) -> None:
        """处理 Ping 请求"""
        self.send_messages([PingResponse()])

    def _handle_device_info(self, msg: DeviceInfoRequest) -> None:
        """处理设备信息请求"""
        logger.info("客户端请求设备信息")

        # 参考 linux-voice-assistant：只设置必需字段
        response = DeviceInfoResponse()
        response.uses_password = False
        response.name = self.device_name
        response.mac_address = self.device_mac
        response.voice_assistant_feature_flags = (
            VoiceAssistantFeature.VOICE_ASSISTANT
            | VoiceAssistantFeature.API_AUDIO
            | VoiceAssistantFeature.ANNOUNCE
            | VoiceAssistantFeature.START_CONVERSATION
            | VoiceAssistantFeature.TIMERS
        )

        self.send_messages([response])
        logger.info("✅ 已发送设备信息")

    def _handle_list_entities(self, msg: ListEntitiesRequest) -> None:
        """处理实体列表请求"""
        # 发送 MediaPlayer 实体定义
        media_player = ListEntitiesMediaPlayerResponse(
            object_id="voice_assistant",
            key=0,
            name="Voice Assistant",
            supports_pause=True,
        )

        self.send_messages([media_player, ListEntitiesDoneResponse()])
        logger.info("已发送 MediaPlayer 实体定义")

    def _handle_subscribe_states(self, msg: SubscribeHomeAssistantStatesRequest) -> None:
        """处理订阅状态请求"""
        # 发送 MediaPlayer 状态
        from aioesphomeapi.api_pb2 import MediaPlayerStateResponse as MPState

        state = MPState()
        state.key = 0
        state.state = MediaPlayerState.IDLE
        state.volume = 1.0

        self.send_messages([state])
        logger.info("已发送实体状态")

    def _handle_media_player_command(self, msg: MediaPlayerCommandRequest) -> None:
        """处理 MediaPlayer 命令"""
        from aioesphomeapi.api_pb2 import MediaPlayerStateResponse as MPState

        logger.info(f"收到 MediaPlayer 命令: command={msg.command}")

        # 发送状态更新
        state = MPState()
        state.key = 0
        state.state = MediaPlayerState.IDLE
        if msg.has_volume:
            state.volume = msg.volume
        else:
            state.volume = 1.0

        self.send_messages([state])

    def _handle_voice_assistant_config(self, msg: VoiceAssistantConfigurationRequest) -> None:
        """处理语音助手配置请求"""
        available_wake_words = [
            VoiceAssistantWakeWord(
                id="ok_nabu",
                wake_word="ok nabu",
                trained_languages=["en"],
            )
        ]

        response = VoiceAssistantConfigurationResponse(
            available_wake_words=available_wake_words,
            active_wake_words=["ok_nabu"],
            max_active_wake_words=2,
        )

        self.send_messages([response])
        logger.info("✅ 已发送语音助手配置")

    def _handle_set_voice_config(self, msg: VoiceAssistantSetConfiguration) -> None:
        """处理设置语音助手配置"""
        logger.info(f"HA 设置唤醒词: {list(msg.active_wake_words)}")

    def _handle_voice_assistant_request(self, msg: VoiceAssistantRequest) -> None:
        """处理语音助手请求"""
        logger.info(f"HA 发起语音助手请求 (start={msg.start})")

        response = VoiceAssistantResponse(
            path="http://172.16.1.101:6053/audio",
        )

        self.send_messages([response])

    def _handle_voice_assistant_audio(self, msg: VoiceAssistantAudio) -> None:
        """处理语音助手音频数据"""
        logger.info(f"收到 TTS 音频 (size={len(msg.data)})")
        finished = VoiceAssistantAnnounceFinished()
        self.send_messages([finished])

    def _handle_announce_request(self, msg: VoiceAssistantAnnounceRequest) -> None:
        """处理语音播报请求"""
        logger.info(f"收到语音播报请求: {msg.text}")
        finished = VoiceAssistantAnnounceFinished()
        self.send_messages([finished])

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """
        处理消息的通用方法（子类可重写）

        Args:
            msg: 接收到的消息

        Returns:
            要发送的响应消息列表
        """
        return []

    def send_messages(self, msgs: List[message.Message]) -> None:
        """
        发送消息给客户端

        使用 aioesphomeapi 的 make_plain_text_packets 打包
        """
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

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT, device_name: str = None):
        self.host = host
        self.port = port
        self.device_name = device_name
        self.server: Optional[asyncio.Server] = None
        self._is_running = False

    async def start(self) -> bool:
        """启动服务器"""
        try:
            logger.info(f"启动 ESPHome API 服务器 @ {self.host}:{self.port}")

            loop = asyncio.get_event_loop()
            self.server = await loop.create_server(
                lambda: ESPHomeProtocol(self.device_name),
                host=self.host,
                port=self.port,
            )

            self._is_running = True
            logger.info(f"✅ ESPHome API 服务器已启动")
            logger.info(f"   监听地址: {self.host}:{self.port}")
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
