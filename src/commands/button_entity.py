"""
Button 实体模块
将命令暴露为 Home Assistant 中的按钮实体
"""

import logging
from collections.abc import Iterable
from typing import Dict, List, Optional, Callable

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (
    ListEntitiesButtonResponse,
    ButtonCommandRequest,
)
from google.protobuf import message

logger = logging.getLogger(__name__)


class ButtonEntity:
    """单个按钮实体"""
    
    def __init__(
        self,
        key: int,
        name: str,
        object_id: str,
        icon: str = "mdi:button-pointer",
        command: str = "",
        handler: Optional[Callable] = None,
    ):
        self.key = key
        self.name = name
        self.object_id = object_id
        self.icon = icon
        self.command = command
        self.handler = handler
    
    def get_entity_definition(self) -> ListEntitiesButtonResponse:
        """获取实体定义"""
        return ListEntitiesButtonResponse(
            object_id=self.object_id,
            key=self.key,
            name=self.name,
            icon=self.icon,
            disabled_by_default=False,
        )
    
    def press(self) -> Dict:
        """按下按钮"""
        if self.handler:
            return self.handler()
        return {'success': False, 'message': 'No handler'}


class ButtonEntityManager:
    """按钮实体管理器"""
    
    # 按钮定义（key 从 100 开始，避免与传感器冲突）
    # 媒体控制通过 MediaPlayer 实体处理，这里只保留系统控制按钮
    BUTTON_DEFINITIONS = [
        # 系统控制按钮
        {'key': 100, 'name': '关机', 'object_id': 'shutdown', 'icon': 'mdi:power', 'command': 'shutdown'},
        {'key': 101, 'name': '重启', 'object_id': 'restart', 'icon': 'mdi:restart', 'command': 'restart'},
        {'key': 102, 'name': '睡眠', 'object_id': 'sleep', 'icon': 'mdi:sleep', 'command': 'sleep'},
        {'key': 103, 'name': '休眠', 'object_id': 'hibernate', 'icon': 'mdi:power-sleep', 'command': 'hibernate'},
        {'key': 104, 'name': '锁定', 'object_id': 'lock', 'icon': 'mdi:lock', 'command': 'lock'},
        {'key': 105, 'name': '注销', 'object_id': 'logoff', 'icon': 'mdi:logout', 'command': 'logoff'},
        
        # 实用工具按钮
        {'key': 120, 'name': '截图', 'object_id': 'screenshot', 'icon': 'mdi:camera', 'command': 'screenshot'},
    ]
    
    def __init__(self, command_executor=None):
        """初始化按钮管理器"""
        self._buttons: Dict[int, ButtonEntity] = {}
        self._command_executor = command_executor
        
        # 创建按钮实体
        self._create_buttons()
        
        logger.info(f"按钮实体管理器初始化完成，共 {len(self._buttons)} 个按钮")
    
    def _create_buttons(self) -> None:
        """创建所有按钮实体"""
        for btn_def in self.BUTTON_DEFINITIONS:
            button = ButtonEntity(
                key=btn_def['key'],
                name=btn_def['name'],
                object_id=btn_def['object_id'],
                icon=btn_def['icon'],
                command=btn_def['command'],
                handler=lambda cmd=btn_def['command']: self._execute_command(cmd),
            )
            self._buttons[btn_def['key']] = button
    
    def _execute_command(self, command: str) -> Dict:
        """执行命令"""
        if self._command_executor:
            return self._command_executor.execute(command)
        else:
            # 懒加载命令执行器
            from .command_executor import CommandExecutor
            self._command_executor = CommandExecutor()
            return self._command_executor.execute(command)
    
    def get_entity_definitions(self) -> List[ListEntitiesButtonResponse]:
        """获取所有按钮实体定义"""
        return [btn.get_entity_definition() for btn in self._buttons.values()]
    
    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """处理按钮命令消息"""
        if isinstance(msg, ButtonCommandRequest):
            button = self._buttons.get(msg.key)
            if button:
                logger.info(f"按钮按下: {button.name} (key={msg.key})")
                result = button.press()
                logger.info(f"命令执行结果: {result}")
            else:
                logger.warning(f"未知按钮 key: {msg.key}")
        
        # Button 命令不需要返回消息
        return []
