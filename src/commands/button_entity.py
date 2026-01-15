"""
Button Entity Module
Exposes commands as button entities in Home Assistant
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
    """Single button entity"""
    
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
        """Get entity definition"""
        return ListEntitiesButtonResponse(
            object_id=self.object_id,
            key=self.key,
            name=self.name,
            icon=self.icon,
            disabled_by_default=False,
        )
    
    def press(self) -> Dict:
        """Press button"""
        if self.handler:
            return self.handler()
        return {'success': False, 'message': 'No handler'}


class ButtonEntityManager:
    """Button entity manager"""
    
    # Button definitions (key starts from 100 to avoid conflict with sensors)
    # Media control is handled by MediaPlayer entity, only system control buttons here
    BUTTON_DEFINITIONS = [
        # System control buttons
        {'key': 100, 'name': 'Shutdown', 'object_id': 'shutdown', 'icon': 'mdi:power', 'command': 'shutdown'},
        {'key': 101, 'name': 'Restart', 'object_id': 'restart', 'icon': 'mdi:restart', 'command': 'restart'},
        
        # Utility buttons
        {'key': 120, 'name': 'Screenshot', 'object_id': 'screenshot', 'icon': 'mdi:camera', 'command': 'screenshot'},
    ]
    
    def __init__(self, command_executor=None):
        """Initialize button manager"""
        self._buttons: Dict[int, ButtonEntity] = {}
        self._command_executor = command_executor
        
        # Create button entities
        self._create_buttons()
        
        logger.info(f"Button entity manager initialized, {len(self._buttons)} buttons total")
    
    def _create_buttons(self) -> None:
        """Create all button entities"""
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
        """Execute command"""
        if self._command_executor:
            return self._command_executor.execute(command)
        else:
            # Lazy load command executor
            from .command_executor import CommandExecutor
            self._command_executor = CommandExecutor()
            return self._command_executor.execute(command)
    
    def get_entity_definitions(self) -> List[ListEntitiesButtonResponse]:
        """Get all button entity definitions"""
        return [btn.get_entity_definition() for btn in self._buttons.values()]
    
    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """Handle button command message"""
        if isinstance(msg, ButtonCommandRequest):
            button = self._buttons.get(msg.key)
            if button:
                logger.info(f"Button pressed: {button.name} (key={msg.key})")
                result = button.press()
                logger.info(f"Command execution result: {result}")
            else:
                logger.warning(f"Unknown button key: {msg.key}")
        
        # Button commands don't need to return messages
        return []
