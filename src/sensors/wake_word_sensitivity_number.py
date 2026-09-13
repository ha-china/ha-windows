"""ESPHome number entity for the wake word sensitivity slider."""

from collections.abc import Iterable
from typing import Callable

from aioesphomeapi.api_pb2 import (
    ListEntitiesNumberResponse,
    ListEntitiesRequest,
    NumberCommandRequest,
    NumberStateResponse,
    SubscribeHomeAssistantStatesRequest,
)
from aioesphomeapi.model import EntityCategory, NumberMode
from google.protobuf import message


class WakeWordSensitivityNumberEntity:
    """Expose wake word sensitivity as a config slider (0.0-1.0)."""

    def __init__(
        self,
        key: int,
        name: str,
        object_id: str,
        get_sensitivity: Callable[[], float],
        set_sensitivity: Callable[[float], None],
    ) -> None:
        self.key = key
        self.name = name
        self.object_id = object_id
        self._get_sensitivity = get_sensitivity
        self._set_sensitivity = set_sensitivity
        self._number_state = self._get_sensitivity()

    def sync_with_state(self) -> None:
        self._number_state = self._get_sensitivity()

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, NumberCommandRequest) and msg.key == self.key:
            self._number_state = max(0.0, min(1.0, float(msg.state)))
            self._set_sensitivity(self._number_state)
            yield NumberStateResponse(key=self.key, state=self._number_state)
        elif isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesNumberResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                min_value=0.0,
                max_value=1.0,
                step=0.01,
                mode=NumberMode.SLIDER,
                entity_category=EntityCategory.CONFIG,
                icon="mdi:account-voice",
            )
        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            self.sync_with_state()
            yield NumberStateResponse(key=self.key, state=self._number_state)
