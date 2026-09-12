"""ESPHome switch entity for the tray icon (sensors-only mode) toggle.

This switch is ALWAYS exposed, even in tray-hidden mode: turning it off
hides the tray icon and unloads voice assistant / Sendspin / remote
commands; turning it on is the only way to restore them (issue #11).
"""

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


class TrayIconSwitchEntity:
    """Expose tray icon visibility as a config switch (ON = icon shown)."""

    def __init__(
        self,
        key: int,
        name: str,
        object_id: str,
        get_visible: Callable[[], bool],
        set_visible: Callable[[bool], None],
    ) -> None:
        self.key = key
        self.name = name
        self.object_id = object_id
        self._get_visible = get_visible
        self._set_visible = set_visible
        self._switch_state = self._get_visible()

    def sync_with_state(self) -> None:
        self._switch_state = self._get_visible()

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, SwitchCommandRequest) and msg.key == self.key:
            self._switch_state = bool(msg.state)
            self._set_visible(self._switch_state)
            yield SwitchStateResponse(key=self.key, state=self._switch_state)
        elif isinstance(msg, ListEntitiesRequest):
            yield ListEntitiesSwitchResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                entity_category=EntityCategory.CONFIG,
                icon="mdi:eye",
            )
        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            self.sync_with_state()
            yield SwitchStateResponse(key=self.key, state=self._switch_state)
