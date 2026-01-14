"""
ESPHome 连接管理模块
负责与 Home Assistant 的 ESPHome API 建立连接
"""

import asyncio
import logging
from typing import Optional, Callable, Any
from enum import Enum

from aioesphomeapi import (
    APIClient,
    VoiceAssistantEventType,
)

from .mdns_discovery import HomeAssistantInstance
from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class ConnectionState(Enum):
    """连接状态枚举"""

    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    ERROR = "error"


class ESPHomeConnection:
    """ESPHome 连接管理器"""

    def __init__(self, instance: HomeAssistantInstance):
        """
        初始化 ESPHome 连接

        Args:
            instance: Home Assistant 实例信息
        """
        self.instance = instance
        self.client: Optional[APIClient] = None
        self.state = ConnectionState.DISCONNECTED
        self._on_state_change_callbacks: list[Callable[[ConnectionState], None]] = []
        self._on_message_callbacks: list[Callable[[Any], None]] = []

    def on_state_change(self, callback: Callable[[ConnectionState], None]) -> None:
        """
        注册状态变化回调

        Args:
            callback: 状态变化回调函数
        """
        self._on_state_change_callbacks.append(callback)

    def on_message(self, callback: Callable[[Any], None]) -> None:
        """
        注册消息回调

        Args:
            callback: 消息回调函数
        """
        self._on_message_callbacks.append(callback)

    def _notify_state_change(self, state: ConnectionState) -> None:
        """通知状态变化"""
        self.state = state
        for callback in self._on_state_change_callbacks:
            try:
                callback(state)
            except Exception as e:
                logger.error(f"状态变化回调失败: {e}")

    def _notify_message(self, message: Any) -> None:
        """通知消息"""
        for callback in self._on_message_callbacks:
            try:
                callback(message)
            except Exception as e:
                logger.error(f"消息回调失败: {e}")

    async def connect(self) -> bool:
        """
        连接到 Home Assistant ESPHome API

        Returns:
            bool: 连接是否成功
        """
        try:
            logger.info(
                _i18n.t('connecting_to_ha').format(
                    self.instance.name, self.instance.esphome_url
                )
            )

            self._notify_state_change(ConnectionState.CONNECTING)

            # 创建 ESPHome API 客户端
            # 注意：这里使用无密码认证（uses_password=False）
            # Home Assistant 会自动接受来自本地网络的连接
            self.client = APIClient(
                address=self.instance.host,
                port=self.instance.esphome_port,
                password=None,  # 无密码认证
            )

            # 连接并登录
            await self.client.connect(login=True)

            # 连接成功
            self._notify_state_change(ConnectionState.CONNECTED)
            logger.info(
                _i18n.t('connection_successful').format(
                    self.instance.name
                )
            )

            return True

        except Exception as e:
            logger.error(f"ESPHome 连接失败: {e}")
            self._notify_state_change(ConnectionState.ERROR)
            return False

    async def disconnect(self) -> None:
        """断开连接"""
        try:
            if self.client:
                await self.client.disconnect()
                self.client = None

            self._notify_state_change(ConnectionState.DISCONNECTED)
            logger.info("ESPHome 连接已断开")

        except Exception as e:
            logger.error(f"断开连接失败: {e}")

    async def reconnect(self) -> bool:
        """
        重新连接

        Returns:
            bool: 重连是否成功
        """
        await self.disconnect()
        await asyncio.sleep(1)  # 等待 1 秒后重连
        return await self.connect()

    def is_connected(self) -> bool:
        """
        检查是否已连接

        Returns:
            bool: 是否已连接
        """
        return self.state == ConnectionState.CONNECTED and self.client is not None

    async def subscribe_voice_assistant(self, start: bool = True) -> None:
        """
        订阅 Voice Assistant 服务

        Args:
            start: 是否立即启动 Voice Assistant
        """
        try:
            if not self.client or not self.is_connected():
                raise RuntimeError("未连接到 ESPHome API")

            # 订阅 Voice Assistant 事件
            # 注意：新版本 aioesphomeapi 使用回调函数而不是 VoiceAssistantSettings
            # TODO: 实现完整的 Voice Assistant 回调处理
            async def handle_start(path: str, conversation_id: int, audio_settings, wakeword: str):
                """处理 Voice Assistant 启动事件"""
                logger.info(f"Voice Assistant 启动: conversation_id={conversation_id}")
                return None

            async def handle_stop(force: bool):
                """处理 Voice Assistant 停止事件"""
                logger.info(f"Voice Assistant 停止: force={force}")

            if start:
                self.client.subscribe_voice_assistant(
                    handle_start=handle_start,
                    handle_stop=handle_stop,
                )

            logger.info("Voice Assistant 订阅成功")

        except Exception as e:
            logger.error(f"订阅 Voice Assistant 失败: {e}")
            raise

    async def send_audio_data(self, audio_data: bytes) -> None:
        """
        发送音频数据到 Home Assistant

        Args:
            audio_data: 音频数据（16kHz mono PCM）
        """
        try:
            if not self.client or not self.is_connected():
                raise RuntimeError("未连接到 ESPHome API")

            # 发送音频数据
            # 注意：具体 API 需要参考 aioesphomeapi 文档
            await self.client.send_voice_assistant_audio(audio_data)

        except Exception as e:
            logger.error(f"发送音频数据失败: {e}")
            raise


class ESPHomeConnectionManager:
    """ESPHome 连接管理器（支持多个实例）"""

    def __init__(self):
        """初始化连接管理器"""
        self.connections: dict[str, ESPHomeConnection] = {}
        self.active_connection: Optional[ESPHomeConnection] = None

    async def connect_to_instance(
        self, instance: HomeAssistantInstance
    ) -> ESPHomeConnection:
        """
        连接到指定的 Home Assistant 实例

        Args:
            instance: Home Assistant 实例信息

        Returns:
            ESPHomeConnection: 连接对象
        """
        # 检查是否已有连接
        key = f"{instance.host}:{instance.esphome_port}"

        if key in self.connections:
            connection = self.connections[key]
            if connection.is_connected():
                return connection

        # 创建新连接
        connection = ESPHomeConnection(instance)
        success = await connection.connect()

        if success:
            self.connections[key] = connection
            self.active_connection = connection

        return connection

    async def disconnect_all(self) -> None:
        """断开所有连接"""
        for connection in self.connections.values():
            await connection.disconnect()

        self.connections.clear()
        self.active_connection = None

    def get_active_connection(self) -> Optional[ESPHomeConnection]:
        """
        获取当前活动的连接

        Returns:
            Optional[ESPHomeConnection]: 当前活动的连接
        """
        return self.active_connection

    def get_connection(
        self, instance: HomeAssistantInstance
    ) -> Optional[ESPHomeConnection]:
        """
        获取指定实例的连接

        Args:
            instance: Home Assistant 实例信息

        Returns:
            Optional[ESPHomeConnection]: 连接对象
        """
        key = f"{instance.host}:{instance.esphome_port}"
        return self.connections.get(key)


# 便捷函数
async def connect_to_ha(
    instance: HomeAssistantInstance,
) -> ESPHomeConnection:
    """
    连接到 Home Assistant 实例

    Args:
        instance: Home Assistant 实例信息

    Returns:
        ESPHomeConnection: 连接对象
    """
    connection = ESPHomeConnection(instance)
    await connection.connect()
    return connection


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)

    async def test_connection():
        """测试连接"""
        from .mdns_discovery import discover_ha_async

        print("发现 Home Assistant 实例...")
        instances = await discover_ha_async(timeout=10.0)

        if not instances:
            print("未发现任何 Home Assistant 实例")
            return

        instance = instances[0]
        print(f"连接到: {instance}")

        connection = ESPHomeConnection(instance)

        def on_state_change(state: ConnectionState):
            print(f"连接状态变化: {state.value}")

        connection.on_state_change(on_state_change)

        success = await connection.connect()

        if success:
            print("连接成功！")
            await asyncio.sleep(5)  # 保持连接 5 秒
            await connection.disconnect()
        else:
            print("连接失败")

    # 运行测试
    asyncio.run(test_connection())
