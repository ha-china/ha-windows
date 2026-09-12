"""ESPHome switch entity for tray-hidden (sensors-only) mode.

This switch is ALWAYS exposed, even in tray-hidden mode: turning it on
hides the tray icon and unloads voice assistant / Sendspin / remote
commands; turning it off is the only way to restore them (issue #11).
Switch state matches the mode flag directly: ON = icon hidden.
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
from google.protobuf import message


class TrayIconSwitchEntity:
    """Expose tray-hidden (sensors-only) mode as a switch (ON = icon hidden)."""

    def __init__(
        self,
        key: int,
        name: str,
        object_id: str,
        get_hidden: Callable[[], bool],
        set_hidden: Callable[[bool], None],
    ) -> None:
        self.key = key
        self.name = name
        self.object_id = object_id
        self._get_hidden = get_hidden
        self._set_hidden = set_hidden
        self._switch_state = self._get_hidden()

    def sync_with_state(self) -> None:
        self._switch_state = self._get_hidden()

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        if isinstance(msg, SwitchCommandRequest) and msg.key == self.key:
            self._switch_state = bool(msg.state)
            self._set_hidden(self._switch_state)
            yield SwitchStateResponse(key=self.key, state=self._switch_state)
        elif isinstance(msg, ListEntitiesRequest):
            # No entity_category: HA groups it under "Controls"
            yield ListEntitiesSwitchResponse(
                object_id=self.object_id,
                key=self.key,
                name=self.name,
                icon="mdi:eye-off",
            )
        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            self.sync_with_state()
            yield SwitchStateResponse(key=self.key, state=self._switch_state)
