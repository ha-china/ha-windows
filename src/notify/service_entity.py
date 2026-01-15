"""
服务实体模块
将通知等功能暴露为 Home Assistant 中的服务
"""

import logging
from collections.abc import Iterable
from typing import Dict, List, Optional

# pylint: disable=no-name-in-module
from aioesphomeapi.api_pb2 import (
    ListEntitiesServicesResponse,
    ListEntitiesServicesArgument,
    ExecuteServiceRequest,
)
from aioesphomeapi.model import UserServiceArgType
from google.protobuf import message

from .toast_notification import NotificationHandler

logger = logging.getLogger(__name__)


class ServiceEntityManager:
    """服务实体管理器"""
    
    # 服务定义（key 从 200 开始）
    SERVICE_DEFINITIONS = [
        {
            'key': 200,
            'name': 'notify',
            'args': [
                {'name': 'title', 'type': UserServiceArgType.STRING},
                {'name': 'message', 'type': UserServiceArgType.STRING},
            ],
        },
        {
            'key': 201,
            'name': 'notify_with_image',
            'args': [
                {'name': 'title', 'type': UserServiceArgType.STRING},
                {'name': 'message', 'type': UserServiceArgType.STRING},
                {'name': 'image_url', 'type': UserServiceArgType.STRING},
            ],
        },
        {
            'key': 202,
            'name': 'launch_app',
            'args': [
                {'name': 'app_name', 'type': UserServiceArgType.STRING},
            ],
        },
        {
            'key': 203,
            'name': 'open_url',
            'args': [
                {'name': 'url', 'type': UserServiceArgType.STRING},
            ],
        },
        {
            'key': 204,
            'name': 'set_volume',
            'args': [
                {'name': 'volume', 'type': UserServiceArgType.INT},
            ],
        },
        {
            'key': 205,
            'name': 'media_play_pause',
            'args': [],
        },
        {
            'key': 206,
            'name': 'media_next',
            'args': [],
        },
        {
            'key': 207,
            'name': 'media_previous',
            'args': [],
        },
    ]
    
    def __init__(self):
        """初始化服务管理器"""
        self._notification_handler = NotificationHandler()
        self._command_executor = None
        
        logger.info(f"服务实体管理器初始化完成，共 {len(self.SERVICE_DEFINITIONS)} 个服务")
    
    def get_entity_definitions(self) -> List[ListEntitiesServicesResponse]:
        """获取所有服务实体定义"""
        definitions = []
        
        for svc_def in self.SERVICE_DEFINITIONS:
            args = [
                ListEntitiesServicesArgument(
                    name=arg['name'],
                    type=arg['type'],
                )
                for arg in svc_def['args']
            ]
            
            definitions.append(
                ListEntitiesServicesResponse(
                    name=svc_def['name'],
                    key=svc_def['key'],
                    args=args,
                )
            )
        
        return definitions
    
    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """处理服务执行消息"""
        if isinstance(msg, ExecuteServiceRequest):
            # 解析参数
            args = {}
            
            # 获取服务定义
            svc_def = next(
                (s for s in self.SERVICE_DEFINITIONS if s['key'] == msg.key),
                None
            )
            
            if svc_def:
                for i, arg in enumerate(msg.args):
                    if i < len(svc_def['args']):
                        arg_name = svc_def['args'][i]['name']
                        arg_type = svc_def['args'][i]['type']
                        
                        # 根据类型获取参数值
                        try:
                            if arg_type == UserServiceArgType.STRING:
                                args[arg_name] = arg.string_
                            elif arg_type == UserServiceArgType.INT:
                                args[arg_name] = arg.int_
                            elif arg_type == UserServiceArgType.FLOAT:
                                args[arg_name] = arg.float_
                            elif arg_type == UserServiceArgType.BOOL:
                                args[arg_name] = arg.bool_
                        except Exception as e:
                            logger.warning(f"解析参数 {arg_name} 失败: {e}")
            
            logger.info(f"执行服务: key={msg.key}, args={args}")
            
            # 执行服务
            if msg.key == 200:  # notify
                self._handle_notify(args)
            elif msg.key == 201:  # notify_with_image
                self._handle_notify_with_image(args)
            elif msg.key == 202:  # launch_app
                self._handle_launch_app(args)
            elif msg.key == 203:  # open_url
                self._handle_open_url(args)
            elif msg.key == 204:  # set_volume
                self._handle_set_volume(args)
            elif msg.key == 205:  # media_play_pause
                self._handle_media_command('play_pause')
            elif msg.key == 206:  # media_next
                self._handle_media_command('next')
            elif msg.key == 207:  # media_previous
                self._handle_media_command('previous')
            else:
                logger.warning(f"未知服务 key: {msg.key}")
        
        # 服务执行不需要返回消息
        return []
    
    def _handle_notify(self, args: Dict) -> None:
        """处理通知服务"""
        title = args.get('title', 'Home Assistant')
        message = args.get('message', '')
        
        self._notification_handler.show_simple(title, message)
        logger.info(f"显示通知: {title} - {message}")
    
    def _handle_notify_with_image(self, args: Dict) -> None:
        """处理带图片的通知服务"""
        title = args.get('title', 'Home Assistant')
        message = args.get('message', '')
        image_url = args.get('image_url', '')
        
        self._notification_handler.show(title, message, image_url=image_url)
        logger.info(f"显示通知（带图片）: {title} - {message}")
    
    def _handle_launch_app(self, args: Dict) -> None:
        """处理启动应用服务"""
        app_name = args.get('app_name', '')
        if not app_name:
            logger.warning("启动应用服务缺少 app_name 参数")
            return
        
        if self._command_executor is None:
            from src.commands.command_executor import CommandExecutor
            self._command_executor = CommandExecutor()
        
        result = self._command_executor.execute(f"launch:{app_name}")
        logger.info(f"启动应用: {app_name}, 结果: {result}")
    
    def _handle_open_url(self, args: Dict) -> None:
        """处理打开 URL 服务"""
        url = args.get('url', '')
        if not url:
            logger.warning("打开 URL 服务缺少 url 参数")
            return
        
        if self._command_executor is None:
            from src.commands.command_executor import CommandExecutor
            self._command_executor = CommandExecutor()
        
        result = self._command_executor.execute(f"url:{url}")
        logger.info(f"打开 URL: {url}, 结果: {result}")
    
    def _handle_set_volume(self, args: Dict) -> None:
        """处理设置音量服务"""
        volume = args.get('volume', 50)
        
        if self._command_executor is None:
            from src.commands.command_executor import CommandExecutor
            self._command_executor = CommandExecutor()
        
        result = self._command_executor.execute(f"volume:{volume}")
        logger.info(f"设置音量: {volume}, 结果: {result}")
    
    def _handle_media_command(self, command: str) -> None:
        """处理媒体控制命令"""
        if self._command_executor is None:
            from src.commands.command_executor import CommandExecutor
            self._command_executor = CommandExecutor()
        
        result = self._command_executor.execute(command)
        logger.info(f"媒体命令: {command}, 结果: {result}")
