"""
ESPHome API 服务器模块

实现 ESPHome 设备 API 服务器，让 Home Assistant 可以作为客户端连接
ESPHome API 基于 Protocol Buffers，使用 varuint 编码
"""

import asyncio
import logging
import socket
from typing import Optional, Dict, Callable
from functools import lru_cache

from aioesphomeapi.api_pb2 import (
    HelloResponse,
    HelloRequest,
    DeviceInfoResponse,
    DeviceInfoRequest,
    AuthenticationResponse,
    AuthenticationRequest,
    DisconnectResponse,
    DisconnectRequest,
    PingResponse,
    PingRequest,
    GetTimeResponse,
    GetTimeRequest,
    SubscribeStatesRequest,
    ListEntitiesRequest,
    ListEntitiesDoneResponse,
    SubscribeHomeAssistantStatesRequest,
    SubscribeHomeAssistantStateResponse,
    # Voice Assistant 相关
    VoiceAssistantConfigurationRequest,
    VoiceAssistantConfigurationResponse,
    VoiceAssistantSetConfiguration,
    VoiceAssistantRequest,
    VoiceAssistantResponse,
    VoiceAssistantEventResponse,
    VoiceAssistantAnnounceRequest,
    VoiceAssistantAnnounceFinished,
    VoiceAssistantAudio,
    SubscribeVoiceAssistantRequest,
    # 实体相关 (参考 linux-voice-assistant 使用 MediaPlayer)
    ListEntitiesMediaPlayerResponse,
    MediaPlayerStateResponse,
    ListEntitiesTextSensorResponse,
    TextSensorStateResponse,
)
from aioesphomeapi.model import VoiceAssistantFeature, VoiceAssistantWakeWord
from aioesphomeapi.core import MESSAGE_TYPE_TO_PROTO

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


# ============================================================================
# Varuint 编码/解码
# ============================================================================

@lru_cache(maxsize=1024)
def varuint_to_bytes(value: int) -> bytes:
    """
    将整数编码为 varuint 格式

    Args:
        value: 要编码的整数值

    Returns:
        bytes: varuint 编码的字节
    """
    if value <= 0x7F:
        return bytes((value,))

    result = bytearray()
    while value:
        temp = value & 0x7F
        value >>= 7
        if value:
            result.append(temp | 0x80)
        else:
            result.append(temp)

    return bytes(result)


async def read_varuint(reader: asyncio.StreamReader) -> Optional[int]:
    """
    从流中读取 varuint 编码的整数

    Args:
        reader: 流读取器

    Returns:
        Optional[int]: 解码后的整数，如果读取失败返回 None
    """
    result = 0
    bitpos = 0

    while True:
        try:
            byte = await reader.readexactly(1)
        except asyncio.IncompleteReadError:
            return None

        val = byte[0]
        result |= (val & 0x7F) << bitpos
        if (val & 0x80) == 0:
            return result
        bitpos += 7


# ============================================================================
# 消息类型映射 (设备 -> HA)
# ============================================================================

# 从 aioesphomeapi 获取完整的消息类型映射
MESSAGE_TYPE_TO_PROTO_INV = {v: k for k, v in MESSAGE_TYPE_TO_PROTO.items()}


# ============================================================================
# 数据类
# ============================================================================

class ClientInfo:
    """连接的客户端信息"""

    def __init__(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter, remote_address: str):
        self.reader = reader
        self.writer = writer
        self.remote_address = remote_address
        self.is_authenticated = False
        self.api_version_major = 1
        self.api_version_minor = 0


# ============================================================================
# ESPHome API 服务器
# ============================================================================

class ESPHomeServer:
    """
    ESPHome API 服务器

    监听指定端口，等待 Home Assistant 连接
    使用 Protocol Buffers 消息格式和 varuint 编码
    """

    DEFAULT_PORT = 6053

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT, device_name: str = None):
        """
        初始化服务器

        Args:
            host: 监听地址
            port: 监听端口
            device_name: 设备名称 (None 时使用本机机器名)
        """
        self.host = host
        self.port = port

        # 获取设备名称
        if device_name is None:
            self.device_name = socket.gethostname()
        else:
            self.device_name = device_name

        # 获取本机 MAC 地址
        self.device_mac = self._get_mac_address()

        self.server: Optional[asyncio.Server] = None
        self.clients: Dict[asyncio.Task, ClientInfo] = {}
        self._is_running = False

        # 实体管理
        self._entities: List[object] = []  # ESPHomeEntity 列表
        self._next_entity_key = 1

        # 消息处理器映射
        self._message_handlers: Dict[int, Callable] = {
            1: self._handle_hello_request,              # HelloRequest
            3: self._handle_auth_request,               # AuthenticationRequest
            5: self._handle_disconnect_request,         # DisconnectRequest
            7: self._handle_ping_request,               # PingRequest
            8: self._handle_ping_request,               # PingRequest (备用)
            9: self._handle_device_info_request,        # DeviceInfoRequest
            11: self._handle_list_entities_request,     # ListEntitiesRequest
            20: self._handle_subscribe_states,          # SubscribeStatesRequest
            27: self._handle_text_sensor_state_request, # TextSensorStateRequest (查询状态)
            28: self._handle_subscribe_logs_request,    # SubscribeLogsRequest
            36: self._handle_get_time_request,          # GetTimeRequest
            38: self._handle_subscribe_home_assistant_states,  # SubscribeHomeAssistantStatesRequest
            # MediaPlayer 相关
            65: self._handle_media_player_command,      # MediaPlayerCommandRequest
            # Voice Assistant 相关 (关键!)
            89: self._handle_subscribe_voice_assistant,  # SubscribeVoiceAssistantRequest
            90: self._handle_voice_assistant_request,    # VoiceAssistantRequest
            106: self._handle_voice_assistant_audio,     # VoiceAssistantAudio
            119: self._handle_announce_request,         # VoiceAssistantAnnounceRequest
            121: self._handle_voice_assistant_config,    # VoiceAssistantConfigurationRequest (关键!)
            123: self._handle_set_voice_config,          # VoiceAssistantSetConfiguration
        }

        # Voice Assistant 状态
        self._voice_assistant_subscribed = False
        self._active_wake_words: list = []  # 激活的唤醒词 ID 列表

    def _get_mac_address(self) -> str:
        """获取本机 MAC 地址"""
        try:
            # 获取第一个非回卡接口的 MAC
            import uuid
            mac = uuid.getnode()
            return ':'.join(f'{(mac >> (i * 8)) & 0xFF:02X}' for i in range(5, -1, -1))
        except Exception:
            return "00:00:00:00:00:01"

    async def start(self) -> bool:
        """
        启动服务器

        Returns:
            bool: 启动是否成功
        """
        try:
            logger.info(f"启动 ESPHome API 服务器 @ {self.host}:{self.port}")

            self.server = await asyncio.start_server(
                self._handle_client,
                self.host,
                self.port,
            )

            self._is_running = True
            logger.info(f"✅ ESPHome API 服务器已启动")
            logger.info(f"   设备名称: {self.device_name}")
            logger.info(f"   MAC 地址: {self.device_mac}")
            logger.info(f"   监听地址: {self.host}:{self.port}")
            logger.info(f"   等待 Home Assistant 连接...")

            return True

        except Exception as e:
            logger.error(f"❌ 启动服务器失败: {e}")
            return False

    async def stop(self) -> None:
        """停止服务器"""
        self._is_running = False

        # 关闭所有客户端连接
        for task, client in list(self.clients.items()):
            try:
                client.writer.close()
                await client.writer.wait_closed()
                task.cancel()
            except Exception:
                pass

        self.clients.clear()

        # 关闭服务器
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

    # ========================================================================
    # 实体管理
    # ========================================================================

    def register_entity(self, entity: object) -> None:
        """
        注册实体

        Args:
            entity: ESPHomeEntity 实例
        """
        self._entities.append(entity)
        logger.debug(f"注册实体: {entity.name} (key={entity.key})")

    def add_entity(self, entity: object) -> object:
        """
        添加实体并返回实体（方便链式调用）

        Args:
            entity: ESPHomeEntity 实例

        Returns:
            添加的实体实例
        """
        self.register_entity(entity)
        return entity

    # ========================================================================
    # 客户端连接处理
    # ========================================================================

    async def _handle_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """
        处理客户端连接

        Args:
            reader: 流读取器
            writer: 流写入器
        """
        remote_address = writer.get_extra_info('peername')
        client_addr = f"{remote_address[0]}:{remote_address[1]}"
        logger.info(f"📱 新客户端连接: {client_addr}")

        client_info = ClientInfo(reader, writer, client_addr)

        # 创建处理任务
        task = asyncio.create_task(self._process_client_messages(client_info))
        self.clients[task] = client_info

        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"客户端处理错误 ({client_addr}): {e}")
        finally:
            await self._cleanup_client(client_info, task)

    async def _process_client_messages(self, client: ClientInfo) -> None:
        """
        处理客户端消息

        Args:
            client: 客户端信息
        """
        try:
            while self._is_running:
                # 读取 preamble (必须是 0x00)
                preamble = await read_varuint(client.reader)
                if preamble is None or preamble != 0x00:
                    logger.warning(f"无效的 preamble: {preamble}")
                    break

                # 读取消息长度
                length = await read_varuint(client.reader)
                if length is None:
                    break

                # 读取消息类型
                msg_type = await read_varuint(client.reader)
                if msg_type is None:
                    break

                logger.debug(f"收到消息: type={msg_type}, length={length}")

                # 读取消息体
                if length > 0:
                    msg_data = await client.reader.readexactly(length)
                else:
                    msg_data = b""

                # 处理消息
                await self._handle_message(client, msg_type, msg_data)

        except asyncio.IncompleteReadError:
            logger.info(f"客户端 {client.remote_address} 断开连接")
        except Exception as e:
            logger.error(f"处理客户端消息错误 ({client.remote_address}): {e}")

    async def _handle_message(
        self,
        client: ClientInfo,
        msg_type: int,
        msg_data: bytes,
    ) -> None:
        """
        处理收到的消息

        Args:
            client: 客户端信息
            msg_type: 消息类型
            msg_data: 消息数据
        """
        handler = self._message_handlers.get(msg_type)

        if handler:
            try:
                await handler(client, msg_data)
            except Exception as e:
                logger.error(f"处理消息 {msg_type} 失败: {e}", exc_info=True)
        else:
            logger.warning(f"未处理的消息类型: {msg_type}")

    # ========================================================================
    # 消息处理器
    # ========================================================================

    async def _handle_hello_request(self, client: ClientInfo, data: bytes) -> None:
        """
        处理 Hello 请求

        Args:
            client: 客户端信息
            data: 请求数据
        """
        # 解析 HelloRequest
        from aioesphomeapi.api_pb2 import HelloRequest
        req = HelloRequest()
        req.ParseFromString(data)

        client.api_version_major = req.api_version_major
        client.api_version_minor = req.api_version_minor

        logger.info(f"客户端 {client.remote_address} 发送 Hello:")
        logger.info(f"  - Client Info: {req.client_info}")
        logger.info(f"  - API Version: {req.api_version_major}.{req.api_version_minor}")

        # 发送 Hello 响应
        response = HelloResponse()
        response.api_version_major = 1
        response.api_version_minor = 10  # 参考项目用 1.10
        response.server_info = "Windows Assistant"
        response.name = self.device_name

        await self._send_message(client, 2, response)  # Message type 2 = HelloResponse

        client.is_authenticated = True
        logger.info(f"✅ 客户端 {client.remote_address} 已完成握手")

    async def _handle_auth_request(self, client: ClientInfo, data: bytes) -> None:
        """
        处理 Authentication 请求

        Args:
            client: 客户端信息
            data: 请求数据
        """
        req = AuthenticationRequest()
        try:
            req.ParseFromString(data)
            logger.info(f"客户端 {client.remote_address} 请求认证 (has_password={bool(req.password)})")
        except Exception:
            logger.info(f"客户端 {client.remote_address} 请求认证")

        # 暂时不验证密码，直接接受所有连接
        # TODO: 如果需要密码验证，检查 req.password
        response = AuthenticationResponse()
        response.invalid_password = False

        await self._send_message(client, 4, response)  # Message type 4 = AuthenticationResponse
        logger.info(f"✅ 客户端 {client.remote_address} 已认证")

    async def _handle_device_info_request(self, client: ClientInfo, data: bytes) -> None:
        """
        处理 DeviceInfo 请求

        Args:
            client: 客户端信息
            data: 请求数据
        """
        req = DeviceInfoRequest()
        try:
            req.ParseFromString(data)
        except Exception:
            pass

        logger.info(f"客户端 {client.remote_address} 请求设备信息")

        # 发送设备信息响应
        # 参考 linux-voice-assistant：只设置必需的字段！
        response = DeviceInfoResponse()
        response.uses_password = False
        response.name = self.device_name
        response.mac_address = self.device_mac
        # 设置语音助手功能标志（这个很关键！）
        response.voice_assistant_feature_flags = (
            VoiceAssistantFeature.VOICE_ASSISTANT
            | VoiceAssistantFeature.API_AUDIO
            | VoiceAssistantFeature.ANNOUNCE
            | VoiceAssistantFeature.START_CONVERSATION
            | VoiceAssistantFeature.TIMERS
        )

        await self._send_message(client, 10, response)  # Message type 10 = DeviceInfoResponse
        logger.info(f"✅ 已发送设备信息给 {client.remote_address}")

    async def _handle_disconnect_request(self, client: ClientInfo, data: bytes) -> None:
        """处理 Disconnect 请求"""
        logger.info(f"客户端 {client.remote_address} 请求断开连接")

        response = DisconnectResponse()
        await self._send_message(client, 7, response)

    async def _handle_ping_request(self, client: ClientInfo, data: bytes) -> None:
        """处理 Ping 请求"""
        await self._send_message(client, 10, PingResponse())  # Message type 10 = PingResponse

    async def _handle_get_time_request(self, client: ClientInfo, data: bytes) -> None:
        """处理 GetTime 请求"""
        from datetime import datetime

        response = GetTimeResponse()
        response.epoch_seconds = int(datetime.now().timestamp())

        await self._send_message(client, 13, response)  # Message type 13 = GetTimeResponse

    async def _handle_subscribe_states(self, client: ClientInfo, data: bytes) -> None:
        """
        处理订阅状态请求

        发送所有实体的当前状态
        """
        from aioesphomeapi.api_pb2 import TextSensorStateResponse
        from aioesphomeapi.model import MediaPlayerState

        # 发送 MediaPlayer 状态 (key=0)
        media_state = MediaPlayerStateResponse(
            key=0,
            state=MediaPlayerState.IDLE,  # 空闲状态
            volume=1.0,  # 音量 100%
        )
        await self._send_message(client, 64, media_state)  # Message type 64 = MediaPlayerStateResponse

        # 如果有 TextSensor，也发送状态
        state_msg = TextSensorStateResponse(
            key=1,
            state="online",
        )
        await self._send_message(client, 27, state_msg)  # Message type 27 = TextSensorStateResponse
        logger.info(f"已发送实体状态给 {client.remote_address}")

    async def _handle_list_entities_request(self, client: ClientInfo, data: bytes) -> None:
        """
        处理 ListEntities 请求

        发送实体定义给 HA，让 HA 能够识别设备
        关键：必须发送 MediaPlayer 实体（参考 linux-voice-assistant）
        """
        # 发送 MediaPlayer 实体定义 - 这是 Voice Assistant 的关键！
        # 参考 linux-voice-assistant 的实现
        media_player = ListEntitiesMediaPlayerResponse(
            object_id="voice_assistant",
            key=0,
            name="Voice Assistant",
            icon="mdi:voice-assistant",
            supports_pause=True,
        )
        await self._send_message(client, 33, media_player)  # Message type 33 = ListEntitiesMediaPlayerResponse

        # 发送完成标记
        await self._send_message(client, 29, ListEntitiesDoneResponse())
        logger.info(f"已发送 MediaPlayer 实体定义给 {client.remote_address}")

    async def _handle_subscribe_home_assistant_states(self, client: ClientInfo, data: bytes) -> None:
        """处理订阅 Home Assistant 状态请求"""
        from aioesphomeapi.api_pb2 import SubscribeHomeAssistantStatesRequest

        req = SubscribeHomeAssistantStatesRequest()
        try:
            req.ParseFromString(data)
            logger.info(f"客户端订阅 HA 状态 (entity_id={req.entity_id})")
        except Exception:
            pass

        # 暂时不需要处理 HA 状态订阅
        pass

    async def _handle_text_sensor_state_request(self, client: ClientInfo, data: bytes) -> None:
        """
        处理文本传感器状态请求

        HA 请求实体的当前状态
        """
        from aioesphomeapi.api_pb2 import TextSensorStateResponse

        # 检查请求是否针对我们的状态传感器 (key=0)
        # 如果 data 为空，返回所有传感器状态
        # 这里我们只有一个状态传感器
        state_msg = TextSensorStateResponse(
            key=0,
            state="online",
        )
        await self._send_message(client, 27, state_msg)
        logger.debug(f"已发送传感器状态给 {client.remote_address}")

    # ========================================================================
    # MediaPlayer 消息处理器
    # ========================================================================

    async def _handle_media_player_command(self, client: ClientInfo, data: bytes) -> None:
        """处理 MediaPlayer 命令请求"""
        from aioesphomeapi.api_pb2 import MediaPlayerCommandRequest
        from aioesphomeapi.model import MediaPlayerCommand, MediaPlayerState

        req = MediaPlayerCommandRequest()
        try:
            req.ParseFromString(data)
            logger.info(f"收到 MediaPlayer 命令: command={req.command}, has_volume={req.has_volume}")

            # 处理命令并发送状态更新
            if req.command == MediaPlayerCommand.PLAY:
                logger.info("MediaPlayer: PLAY")
            elif req.command == MediaPlayerCommand.PAUSE:
                logger.info("MediaPlayer: PAUSE")

            # 发送状态更新
            state = MediaPlayerStateResponse(
                key=0,
                state=MediaPlayerState.IDLE,
                volume=req.volume if req.has_volume else 1.0,
            )
            await self._send_message(client, 64, state)  # Message type 64
        except Exception as e:
            logger.error(f"处理 MediaPlayer 命令失败: {e}")

    # ========================================================================
    # Voice Assistant 消息处理器 (关键!)
    # ========================================================================

    async def _handle_subscribe_logs_request(self, client: ClientInfo, data: bytes) -> None:
        """处理订阅日志请求"""
        logger.info(f"客户端 {client.remote_address} 订阅日志")
        # 暂不发送日志，只响应即可

    async def _handle_voice_assistant_config(self, client: ClientInfo, data: bytes) -> None:
        """
        处理 Voice Assistant 配置请求 (关键!)

        这是 HA 识别设备为语音助手的关键步骤！
        必须返回 VoiceAssistantConfigurationResponse 包含可用唤醒词
        """
        from aioesphomeapi.model import VoiceAssistantWakeWord

        req = VoiceAssistantConfigurationRequest()
        try:
            req.ParseFromString(data)
            logger.info(f"HA 请求语音助手配置")
        except Exception:
            pass

        # 创建一个默认唤醒词 (使用 OK Generic 模型)
        available_wake_words = [
            VoiceAssistantWakeWord(
                id="ok_nabu",
                wake_word="ok nabu",
                trained_languages=["en"],  # 英文
            )
        ]

        # 发送配置响应
        response = VoiceAssistantConfigurationResponse(
            available_wake_words=available_wake_words,
            active_wake_words=["ok_nabu"],  # 默认激活一个
            max_active_wake_words=2,
        )
        await self._send_message(client, 122, response)  # Message type 122
        logger.info(f"✅ 已发送语音助手配置给 {client.remote_address}")

    async def _handle_set_voice_config(self, client: ClientInfo, data: bytes) -> None:
        """处理设置语音助手配置请求"""
        req = VoiceAssistantSetConfiguration()
        try:
            req.ParseFromString(data)
            self._active_wake_words = list(req.active_wake_words)
            logger.info(f"HA 设置唤醒词: {self._active_wake_words}")
        except Exception:
            pass

    async def _handle_subscribe_voice_assistant(self, client: ClientInfo, data: bytes) -> None:
        """处理订阅语音助手请求"""
        self._voice_assistant_subscribed = True
        logger.info(f"✅ HA 订阅语音助手服务")
        # 发送一个初始事件，表明语音助手已就绪
        event = VoiceAssistantEventResponse(
            event_type=0,  # VOICE_ASSISTANT_RUN_STARTED (参考 model.py)
        )
        await self._send_message(client, 91, event)  # Message type 91

    async def _handle_voice_assistant_request(self, client: ClientInfo, data: bytes) -> None:
        """处理语音助手请求 (开始对话)"""
        req = VoiceAssistantRequest()
        try:
            req.ParseFromString(data)
            logger.info(f"HA 发起语音助手请求 (start={req.start})")
            # 发送响应，表明准备好接收音频
            response = VoiceAssistantResponse(
                path="http://172.16.1.101:6053/audio",  # 暂时用假的 URL
            )
            await self._send_message(client, 90, response)  # Message type 90
        except Exception as e:
            logger.error(f"处理语音助手请求失败: {e}")

    async def _handle_voice_assistant_audio(self, client: ClientInfo, data: bytes) -> None:
        """处理语音助手音频数据 (TTS)"""
        req = VoiceAssistantAudio()
        try:
            req.ParseFromString(data)
            logger.info(f"收到 TTS 音频 (url={req.url}, size={len(data)})")
            # TODO: 使用 MPV 播放器播放 TTS
            # 发送完成事件
            finished = VoiceAssistantAnnounceFinished()
            await self._send_message(client, 120, finished)  # Message type 120
        except Exception as e:
            logger.error(f"处理音频数据失败: {e}")

    async def _handle_announce_request(self, client: ClientInfo, data: bytes) -> None:
        """处理语音播报请求"""
        req = VoiceAssistantAnnounceRequest()
        try:
            req.ParseFromString(data)
            logger.info(f"收到语音播报请求")
            # TODO: 处理播报，发送 finished
            finished = VoiceAssistantAnnounceFinished()
            await self._send_message(client, 120, finished)  # Message type 120
        except Exception as e:
            logger.error(f"处理播报请求失败: {e}")

    # ========================================================================
    # 消息发送
    # ========================================================================

    async def _send_message(self, client: ClientInfo, msg_type: int, message) -> None:
        """
        发送消息给客户端

        Args:
            client: 客户端信息
            msg_type: 消息类型
            message: protobuf 消息对象
        """
        try:
            # 序列化 protobuf 消息
            data = message.SerializeToString()

            # 构建数据包: preamble(0x00) + length(varuint) + msg_type(varuint) + data
            packet = b'\x00'
            packet += varuint_to_bytes(len(data))
            packet += varuint_to_bytes(msg_type)
            packet += data

            # 发送
            client.writer.write(packet)
            await client.writer.drain()

            logger.debug(f"发送消息: type={msg_type}, length={len(data)}")

        except Exception as e:
            logger.error(f"发送消息失败 ({client.remote_address}): {e}")

    # ========================================================================
    # 清理
    # ========================================================================

    async def _cleanup_client(
        self,
        client: ClientInfo,
        task: asyncio.Task,
    ) -> None:
        """清理客户端资源"""
        try:
            client.writer.close()
            await client.writer.wait_closed()
        except Exception:
            pass

        if task in self.clients:
            del self.clients[task]

        logger.info(f"客户端 {client.remote_address} 已清理")

    @property
    def is_running(self) -> bool:
        """服务器是否运行中"""
        return self._is_running


# ============================================================================
# 便捷函数
# ============================================================================

async def start_server(
    host: str = "0.0.0.0",
    port: int = ESPHomeServer.DEFAULT_PORT,
    device_name: str = None,
) -> ESPHomeServer:
    """
    启动 ESPHome API 服务器

    Args:
        host: 监听地址
        port: 监听端口
        device_name: 设备名称

    Returns:
        ESPHomeServer: 服务器实例
    """
    server = ESPHomeServer(host, port, device_name)
    success = await server.start()

    if not success:
        raise RuntimeError("启动服务器失败")

    return server


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(
        level=logging.DEBUG,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )

    async def test():
        print("启动 ESPHome API 服务器测试...")

        server = ESPHomeServer()
        await server.start()

        print("\n服务器运行中，按 Ctrl+C 退出...")
        try:
            await server.serve_forever()
        except KeyboardInterrupt:
            print("\n正在停止服务器...")
            await server.stop()

    asyncio.run(test())
