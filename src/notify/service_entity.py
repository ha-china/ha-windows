"""
Service Entity Module
Exposes notification and other features as services in Home Assistant
"""

import logging
from collections.abc import Iterable
from typing import Dict, List

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
    """Service entity manager"""

    # Service definitions (key starts from 200)
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
        """Initialize service manager"""
        self._notification_handler = NotificationHandler()
        self._command_executor = None

        logger.info(f"Service entity manager initialized, {len(self.SERVICE_DEFINITIONS)} services total")

    def get_entity_definitions(self) -> List[ListEntitiesServicesResponse]:
        """Get all service entity definitions"""
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
        """Handle service execution message"""
        if isinstance(msg, ExecuteServiceRequest):
            # Parse arguments
            args = {}

            # Get service definition
            svc_def = next(
                (s for s in self.SERVICE_DEFINITIONS if s['key'] == msg.key),
                None
            )

            if svc_def:
                for i, arg in enumerate(msg.args):
                    if i < len(svc_def['args']):
                        arg_name = svc_def['args'][i]['name']
                        arg_type = svc_def['args'][i]['type']

                        # Get argument value based on type
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
                            logger.warning(f"Failed to parse argument {arg_name}: {e}")

            logger.info(f"Executing service: key={msg.key}, args={args}")

            # Execute service
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
                logger.warning(f"Unknown service key: {msg.key}")

        # Service execution doesn't need to return messages
        return []

    def _handle_notify(self, args: Dict) -> None:
        """Handle notification service"""
        title = args.get('title', 'Home Assistant')
        message = args.get('message', '')

        self._notification_handler.show_simple(title, message)
        logger.info(f"Showing notification: {title} - {message}")

    def _handle_notify_with_image(self, args: Dict) -> None:
        """Handle notification with image service"""
        title = args.get('title', 'Home Assistant')
        message = args.get('message', '')
        image_url = args.get('image_url', '')

        self._notification_handler.show(title, message, image_url=image_url)
        logger.info(f"Showing notification (with image): {title} - {message}")

    def _handle_launch_app(self, args: Dict) -> None:
        """Handle launch app service"""
        app_name = args.get('app_name', '')
        if not app_name:
            logger.warning("Launch app service missing app_name parameter")
            return

        if self._command_executor is None:
            from src.commands.command_executor import CommandExecutor
            self._command_executor = CommandExecutor()

        result = self._command_executor.execute(f"launch:{app_name}")
        logger.info(f"Launch app: {app_name}, result: {result}")

    def _handle_open_url(self, args: Dict) -> None:
        """Handle open URL service"""
        url = args.get('url', '')
        if not url:
            logger.warning("Open URL service missing url parameter")
            return

        if self._command_executor is None:
            from src.commands.command_executor import CommandExecutor
            self._command_executor = CommandExecutor()

        result = self._command_executor.execute(f"url:{url}")
        logger.info(f"Open URL: {url}, result: {result}")

    def _handle_set_volume(self, args: Dict) -> None:
        """Handle set volume service"""
        volume = args.get('volume', 50)

        if self._command_executor is None:
            from src.commands.command_executor import CommandExecutor
            self._command_executor = CommandExecutor()

        result = self._command_executor.execute(f"volume:{volume}")
        logger.info(f"Set volume: {volume}, result: {result}")

    def _handle_media_command(self, command: str) -> None:
        """Handle media control command"""
        if self._command_executor is None:
            from src.commands.command_executor import CommandExecutor
            self._command_executor = CommandExecutor()

        result = self._command_executor.execute(command)
        logger.info(f"Media command: {command}, result: {result}")
