"""
Configuration Sensor Module

Provides text sensor entities for configuration settings like hotkey.
"""

import logging
from typing import List, Optional

from aioesphomeapi.api_pb2 import (
    ListEntitiesTextSensorResponse,
    TextSensorStateResponse,
)

logger = logging.getLogger(__name__)


class ConfigSensor:
    """Configuration text sensor entity"""

    def __init__(
        self,
        key: int,
        name: str,
        object_id: str,
        icon: str = "mdi:cog",
        state: str = "",
    ):
        self.key = key
        self.name = name
        self.object_id = object_id
        self.icon = icon
        self._state = state

    def get_entity_definition(self) -> ListEntitiesTextSensorResponse:
        """Get entity definition"""
        return ListEntitiesTextSensorResponse(
            object_id=self.object_id,
            key=self.key,
            name=self.name,
            icon=self.icon,
        )

    def get_state(self) -> TextSensorStateResponse:
        """Get current state"""
        return TextSensorStateResponse(
            key=self.key,
            state=self._state,
        )

    def set_state(self, state: str) -> None:
        """Set state"""
        self._state = state
        logger.debug(f"Config sensor {self.name} state updated: {state}")


class ConfigSensorManager:
    """Configuration sensor manager"""

    def __init__(self):
        """Initialize config sensor manager"""
        self._sensors = {}
        self._create_sensors()
        logger.info(f"Config sensor manager initialized, {len(self._sensors)} sensors total")

    def _create_sensors(self) -> None:
        """Create all config sensor entities"""
        # Hotkey configuration sensor
        hotkey_sensor = ConfigSensor(
            key=200,
            name="Voice Input Hotkey",
            object_id="voice_input_hotkey",
            icon="mdi:keyboard",
            state="",
        )
        self._sensors[200] = hotkey_sensor

    def get_entity_definitions(self) -> List[ListEntitiesTextSensorResponse]:
        """Get all entity definitions"""
        return [sensor.get_entity_definition() for sensor in self._sensors.values()]

    def get_states(self) -> List[TextSensorStateResponse]:
        """Get all states"""
        return [sensor.get_state() for sensor in self._sensors.values()]

    def set_hotkey(self, hotkey: str) -> None:
        """Set hotkey state"""
        if 200 in self._sensors:
            self._sensors[200].set_state(hotkey)

    def get_hotkey(self) -> str:
        """Get hotkey state"""
        if 200 in self._sensors:
            return self._sensors[200].get_state().state
        return ""