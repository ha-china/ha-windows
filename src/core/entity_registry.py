"""
Entity registry / service routing mixin

Behavior-preserving extraction from ESPHomeProtocol (see esphome_protocol.py).
Methods run on the composed protocol instance and share its ``self`` state.
"""

import asyncio
import logging
from typing import Callable, Dict, List, Optional

from collections.abc import Iterable

from aioesphomeapi.api_pb2 import (
    ButtonCommandRequest,
    DeviceInfoRequest,
    DeviceInfoResponse,
    ExecuteServiceRequest,
    ListEntitiesDoneResponse,
    ListEntitiesRequest,
    MediaPlayerCommandRequest,
    SubscribeHomeAssistantStatesRequest,
    SwitchCommandRequest,
)
from aioesphomeapi.model import VoiceAssistantFeature
from google.protobuf import message

from src.core.models import get_user_data_dir
from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class EntityRegistryMixin:
    """Entity list responses, service dispatch and periodic state pushes."""

    def _cancel_state_updates(self) -> None:
        """Cancel background state update task."""
        if self._state_update_task is not None:
            self._state_update_task.cancel()
            self._state_update_task = None

    def _ensure_state_updates_started(self) -> None:
        """Start periodic state updates once Home Assistant subscribes."""
        if self._loop is None or self._state_update_task is not None:
            return
        self._state_update_task = self._loop.create_task(self._state_update_loop())

    async def _state_update_loop(self) -> None:
        """Push sensor and config states periodically to Home Assistant."""
        try:
            while self._transport is not None:
                await asyncio.sleep(self.STATE_UPDATE_INTERVAL)
                if self._transport is None:
                    break
                self._send_current_states()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            logger.error(f"State update loop failed: {e}")
        finally:
            self._state_update_task = None

    def _send_current_states(self) -> None:
        """Send the current set of states to Home Assistant."""
        if self._monitor is None:
            return

        messages = list(self._monitor.get_esp_sensor_states())

        if self._media_player_entity is not None:
            messages.append(self._media_player_entity.get_state())

        if self._config_sensor_manager is not None:
            messages.extend(self._config_sensor_manager.get_states())

        # Tray icon switch state is served in every mode
        if self._tray_icon_entity is not None:
            messages.extend(self._tray_icon_entity.handle_message(SubscribeHomeAssistantStatesRequest()))

        if messages:
            self.send_messages(messages)

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """Handle entity-related messages"""
        if isinstance(msg, DeviceInfoRequest):
            # Get version from src.__init__
            try:
                from src import __version__

                version = __version__
            except Exception:
                version = "unknown"

            yield DeviceInfoResponse(
                uses_password=False,
                name=self.state.name,
                friendly_name=self.state.friendly_name,
                project_name="ha-china.ha-windows",
                mac_address=self.state.mac_address,
                project_version=version,
                esphome_version=self.state.esphome_version,
                manufacturer=self.state.manufacturer,
                model=self.state.model,
                voice_assistant_feature_flags=(
                    (
                        VoiceAssistantFeature.VOICE_ASSISTANT
                        | VoiceAssistantFeature.API_AUDIO
                        | VoiceAssistantFeature.ANNOUNCE
                        | VoiceAssistantFeature.START_CONVERSATION
                        | VoiceAssistantFeature.TIMERS
                    )
                    if self._remote_features_enabled()
                    else 0
                ),
            )
        elif isinstance(
            msg,
            (
                ListEntitiesRequest,
                SubscribeHomeAssistantStatesRequest,
                MediaPlayerCommandRequest,
                ButtonCommandRequest,
                ExecuteServiceRequest,
                SwitchCommandRequest,
            ),
        ):
            # Handle entity messages
            yield from self._handle_entity_message(msg)

            if isinstance(msg, ListEntitiesRequest):
                yield ListEntitiesDoneResponse()

    def _handle_entity_message(self, msg: message.Message) -> Iterable[message.Message]:
        """Handle entity messages"""
        # Get Windows Monitor
        if self._monitor is None:
            from src.sensors.windows_monitor import WindowsMonitor

            self._monitor = WindowsMonitor()

        # Tray icon switch: ALWAYS available - in sensors-only mode it is the
        # only way to restore the hidden features (issue #11/#12).
        # Switch state == mode flag: ON = icon hidden.
        if self._tray_icon_entity is None:
            from src.sensors.tray_icon_switch import TrayIconSwitchEntity

            self._tray_icon_entity = TrayIconSwitchEntity(
                key=700,
                name=_i18n.t("tray_hide_switch"),
                object_id="tray_icon",
                get_hidden=lambda: getattr(self.state.preferences, "tray_icon_hidden", False),
                set_hidden=self._set_tray_hidden_and_push,
            )

        enabled = self._remote_features_enabled()
        if enabled:
            # Get MediaPlayer entity
            if self._media_player_entity is None:
                from src.sensors.media_player import MediaPlayerEntity

                self._media_player_entity = MediaPlayerEntity(
                    server=self,
                    key=300,
                    name="Media Player",
                    object_id="windows_media_player",
                )

            # Get button manager
            if self._button_manager is None:
                from src.commands.button_entity import ButtonEntityManager

                self._button_manager = ButtonEntityManager()

            # Get service manager
            if self._service_manager is None:
                from src.notify.service_entity import ServiceEntityManager

                self._service_manager = ServiceEntityManager()
                # Set hotkey callback
                self._service_manager.set_hotkey_callback(self._on_hotkey_changed)
                if self._ha_host:
                    self._service_manager.set_ha_host(self._ha_host)

            # Get config sensor manager
            if self._config_sensor_manager is None:
                from src.sensors.config_sensor import ConfigSensorManager

                self._config_sensor_manager = ConfigSensorManager()
                # Update hotkey state from preferences
                self._config_sensor_manager.set_hotkey(self.state.preferences.voice_input_hotkey)

            if self._thinking_sound_entity is None:
                from src.sensors.thinking_sound_switch import ThinkingSoundSwitchEntity

                self._thinking_sound_entity = ThinkingSoundSwitchEntity(
                    key=500,
                    name="Thinking Sound",
                    object_id="thinking_sound",
                    get_enabled=lambda: self.state.thinking_sound_enabled,
                    set_enabled=self._set_thinking_sound_enabled,
                )

            if self._mic_mute_entity is None:
                from src.sensors.mic_mute_switch import MicMuteSwitchEntity

                self._mic_mute_entity = MicMuteSwitchEntity(
                    key=600,
                    name="Microphone Mute",
                    object_id="microphone_mute",
                    get_muted=lambda: self.state.preferences.muted,
                    set_muted=self._set_muted,
                )

            # Get hotkey manager
            if self._hotkey_manager is None:
                from src.core.hotkey_manager import get_hotkey_manager

                self._hotkey_manager = get_hotkey_manager()
                # Set hotkey callback
                if self._hotkey_manager.is_available():
                    self._hotkey_manager.set_hotkey(
                        self.state.preferences.voice_input_hotkey, self._on_voice_input_trigger
                    )

        if isinstance(msg, ListEntitiesRequest):
            # Send sensor entity definitions
            for entity_def in self._monitor.get_esp_entity_definitions():
                if not isinstance(entity_def, ListEntitiesDoneResponse):
                    yield entity_def
            # Tray icon switch is served in every mode
            yield from self._tray_icon_entity.handle_message(msg)
            if not enabled:
                return
            # Send MediaPlayer entity definition
            yield self._media_player_entity.get_entity_definition()
            # Send button entity definitions
            for btn_def in self._button_manager.get_entity_definitions():
                yield btn_def
            # Send service entity definitions
            for svc_def in self._service_manager.get_entity_definitions():
                yield svc_def
            # Send config sensor entity definitions
            for cfg_def in self._config_sensor_manager.get_entity_definitions():
                yield cfg_def
            yield from self._thinking_sound_entity.handle_message(msg)
            yield from self._mic_mute_entity.handle_message(msg)

        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            # Send sensor states
            yield from self._monitor.get_esp_sensor_states()
            yield from self._tray_icon_entity.handle_message(msg)
            if not enabled:
                self._ensure_state_updates_started()
                return
            yield self._media_player_entity.get_state()
            yield from self._config_sensor_manager.get_states()
            yield from self._thinking_sound_entity.handle_message(msg)
            yield from self._mic_mute_entity.handle_message(msg)
            self._ensure_state_updates_started()

        elif isinstance(msg, MediaPlayerCommandRequest):
            # Handle MediaPlayer command
            if self._media_player_entity is not None:
                yield from self._media_player_entity.handle_message(msg)

        elif isinstance(msg, ButtonCommandRequest):
            # Handle button command
            if self._button_manager is not None:
                yield from self._button_manager.handle_message(msg)

        elif isinstance(msg, ExecuteServiceRequest):
            # Handle service execution
            if self._service_manager is not None:
                yield from self._service_manager.handle_message(msg)

        elif isinstance(msg, SwitchCommandRequest):
            # Tray icon switch works in every mode
            yield from self._tray_icon_entity.handle_message(msg)
            if self._thinking_sound_entity is not None:
                yield from self._thinking_sound_entity.handle_message(msg)
            if self._mic_mute_entity is not None:
                yield from self._mic_mute_entity.handle_message(msg)

    # ========== Message Sending ==========
