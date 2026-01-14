"""
ESPHome API 服务器模块

实现 ESPHome 设备 API 服务器，让 Home Assistant 可以作为客户端连接
ESPHome API 基于 Protocol Buffers，这里实现基本的服务器框架
"""

import asyncio
import logging
import struct
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


# ESPHome 协议常量
PROTO_HEADER_SIZE = 3  # [type(1), length(2)]
PROTO_MAX_MESSAGE_SIZE = 1024 * 1024  # 1MB


class MessageType:
    """ESPHome API 消息类型"""

    # 客户端消息 (Home Assistant -> 设备)
    HELLO = 1
    CONNECT = 3
    DISCONNECT = 4
    SUBSCRIBE_STATES = 5
    GET_TIME = 12
    SUBSCRIBE_SERVICE_ARGUMENTS = 15
    SUBSCRIBE_HOME_ASSISTANT_STATES = 19
    SUBSCRIBE_LOG_BUFFER = 23
    SUBSCRIBE_BLE_CONNECTION_ADVERTISE = 28
    SUBSCRIBE_BLE_CONNECTIONS = 29
    SUBSCRIBE_VOICE_ASSISTANT = 31
    HOME_ASSISTANT_ALARM_CONTROL_PANEL_COMMAND = 100
    HOME_ASSISTANT_CLIMATE_COMMAND = 105
    HOME_ASSISTANT_COVER_COMMAND = 107
    HOME_ASSISTANT_FAN_COMMAND = 109
    HOME_ASSISTANT_LIGHT_COMMAND = 110
    HOME_ASSISTANT_MEDIA_PLAYER_COMMAND = 112
    HOME_ASSISTANT_SERVICE = 113
    HOME_ASSISTANT_SWITCH_COMMAND = 115

    # 服务器消息 (设备 -> Home Assistant)
    HELLO_RESPONSE = 2
    CONNECTION_STATE_RESPONSE = 6
    DEVICE_INFO_RESPONSE = 20
    LOG_BUFFER_RESPONSE = 24
    HOME_ASSISTANT_STATE_RESPONSE = 31
    SUBSCRIBE_VOICE_ASSISTANT_RESPONSE = 33
    VOICE_ASSISTANT_AUDIO = 38


@dataclass
class ClientInfo:
    """连接的客户端信息"""

    reader: asyncio.StreamReader
    writer: asyncio.StreamWriter
    remote_address: str
    is_authenticated: bool = False


class ESPHomeServer:
    """
    ESPHome API 服务器

    监听指定端口，等待 Home Assistant 连接
    """

    DEFAULT_PORT = 6053

    def __init__(self, host: str = "0.0.0.0", port: int = DEFAULT_PORT):
        """
        初始化服务器

        Args:
            host: 监听地址
            port: 监听端口
        """
        self.host = host
        self.port = port
        self.server: Optional[asyncio.Server] = None
        self.clients: Dict[asyncio.Task, ClientInfo] = {}
        self._is_running = False

        # 设备信息
        self.device_name = "Windows Assistant"
        self.device_mac = "00:00:00:00:00:01"

        # 消息处理器
        self._message_handlers: Dict[int, Callable] = {
            MessageType.HELLO: self._handle_hello,
            MessageType.CONNECT: self._handle_connect,
            MessageType.DISCONNECT: self._handle_disconnect,
            MessageType.SUBSCRIBE_STATES: self._handle_subscribe_states,
        }

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
        logger.info(f"📱 新客户端连接: {remote_address[0]}:{remote_address[1]}")

        client_info = ClientInfo(
            reader=reader,
            writer=writer,
            remote_address=f"{remote_address[0]}:{remote_address[1]}",
        )

        # 创建处理任务
        task = asyncio.create_task(self._process_client_messages(client_info))
        self.clients[task] = client_info

        try:
            await task
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"客户端处理错误: {e}")
        finally:
            # 清理
            await self._cleanup_client(client_info, task)

    async def _process_client_messages(self, client: ClientInfo) -> None:
        """
        处理客户端消息

        Args:
            client: 客户端信息
        """
        try:
            while self._is_running:
                # 读取消息头
                header = await client.reader.readexactly(PROTO_HEADER_SIZE)
                if not header:
                    break

                # 解析消息类型和长度
                msg_type = header[0]
                msg_length = struct.unpack(">H", header[1:3])[0]

                logger.debug(f"收到消息: type={msg_type}, length={msg_length}")

                # 读取消息体
                if msg_length > 0:
                    msg_data = await client.reader.readexactly(msg_length)
                else:
                    msg_data = b""

                # 处理消息
                await self._handle_message(client, msg_type, msg_data)

        except asyncio.IncompleteReadError:
            logger.info(f"客户端 {client.remote_address} 断开连接")
        except Exception as e:
            logger.error(f"处理客户端消息错误: {e}")

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
                logger.error(f"处理消息 {msg_type} 失败: {e}")
        else:
            logger.warning(f"未处理的消息类型: {msg_type}")

    async def _handle_hello(self, client: ClientInfo, data: bytes) -> None:
        """
        处理 Hello 消息

        Args:
            client: 客户端信息
            data: 消息数据
        """
        logger.info(f"客户端 {client.remote_address} 发送 Hello")

        # 发送 Hello 响应
        # 简化版本：返回基本信息
        response = b"\x02"  # HELLO_RESPONSE
        response += struct.pack(">H", 0)  # 长度
        # TODO: 添加实际的设备信息

        client.writer.write(response)
        await client.writer.drain()

        client.is_authenticated = True
        logger.info(f"✅ 客户端 {client.remote_address} 已认证")

    async def _handle_connect(self, client: ClientInfo, data: bytes) -> None:
        """处理 Connect 消息"""
        logger.info(f"客户端 {client.remote_address} 请求连接")

        # 发送连接状态响应
        # TODO: 实现完整的连接逻辑

    async def _handle_disconnect(self, client: ClientInfo, data: bytes) -> None:
        """处理 Disconnect 消息"""
        logger.info(f"客户端 {client.remote_address} 断开连接")

    async def _handle_subscribe_states(self, client: ClientInfo, data: bytes) -> None:
        """处理订阅状态消息"""
        logger.info(f"客户端 {client.remote_address} 订阅状态")
        # TODO: 实现状态订阅

    async def send_message(
        self,
        client: ClientInfo,
        msg_type: int,
        data: bytes = b"",
    ) -> None:
        """
        发送消息给客户端

        Args:
            client: 客户端信息
            msg_type: 消息类型
            data: 消息数据
        """
        try:
            header = bytes([msg_type])
            header += struct.pack(">H", len(data))
            message = header + data

            client.writer.write(message)
            await client.writer.drain()

        except Exception as e:
            logger.error(f"发送消息失败: {e}")

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


# 便捷函数
async def start_server(
    host: str = "0.0.0.0",
    port: int = ESPHomeServer.DEFAULT_PORT,
) -> ESPHomeServer:
    """
    启动 ESPHome API 服务器

    Args:
        host: 监听地址
        port: 监听端口

    Returns:
        ESPHomeServer: 服务器实例
    """
    server = ESPHomeServer(host, port)
    success = await server.start()

    if not success:
        raise RuntimeError("启动服务器失败")

    return server


if __name__ == "__main__":
    # 测试代码
    import asyncio

    logging.basicConfig(
        level=logging.INFO,
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
