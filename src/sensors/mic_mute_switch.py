"""ESPHome switch entity for the microphone mute toggle."""

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


class MicMuteSwitchEntity:
    """Expose microphone mute as a config switch."""

    def __init__(
        self,
        key: int,
        name: str,
        object_id: str,
        get_muted: Callable[[], bool],
        set_muted: Callable[[bool], None],
    ) -> None:
        self.key = key
        self.name = name
        self.object_id = object_id
        self._get_muted = get_muted
        self._set_muted = set_muted
        self._switch_state = self._get_muted()

    def sync_with_state(self) -> None:
        self._switch_state = self._get_muted()

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, SwitchCommandRequest) and msg.key == self.key:
            self._switch_state = bool(msg.state)
            self._set_muted(self._switch_state)
            yield SwitchStateResponse(key=self.key, state=self._switch_state)
        elif isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesSwitchResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                entity_category=EntityCategory.CONFIG,
                icon="mdi:microphone-off",
            )
        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            self.sync_with_state()
            yield SwitchStateResponse(key=self.key, state=self._switch_state)