"""ESPHome switch entity for the thinking sound option."""

from collections.abc import Iterable
from typing import Callable

from aioesphomeapi.api_pb2 import (
    ListEntitiesRequest,
    ListEntitiesSwitchResponse,
    SubscribeHomeAssistantStatesRequest,
    SwitchCommandRequest,
    SwitchStateResponse,
)
from aioesphomeapi.model import EntityCategory
from google.protobuf import message


class ThinkingSoundSwitchEntity:
    """Expose the thinking sound setting as a config switch."""

    def __init__(
        self,
        key: int,
        name: str,
        object_id: str,
        get_enabled: Callable[[], bool],
        set_enabled: Callable[[bool], None],
    ) -> None:
        self.key = key
        self.name = name
        self.object_id = object_id
        self._get_enabled = get_enabled
        self._set_enabled = set_enabled
        self._switch_state = self._get_enabled()

    def sync_with_state(self) -> None:
        self._switch_state = self._get_enabled()

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, SwitchCommandRequest) and msg.key == self.key:
            self._switch_state = bool(msg.state)
            self._set_enabled(self._switch_state)
            yield SwitchStateResponse(key=self.key, state=self._switch_state)
        elif isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesSwitchResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                entity_category=EntityCategory.CONFIG,
                icon="mdi:music-note",
            )
        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            self.sync_with_state()
            yield SwitchStateResponse(key=self.key, state=self._switch_state)
