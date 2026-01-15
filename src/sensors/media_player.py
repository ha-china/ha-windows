"""
Media Player Entity Module

References linux-voice-assistant's entity.py implementation
Provides MediaPlayer entity for Home Assistant
"""

import logging
from typing import Callable, Iterable, List, Optional, Union, TYPE_CHECKING

from aioesphomeapi.api_pb2 import (
    ListEntitiesMediaPlayerResponse,
    MediaPlayerStateResponse,
    MediaPlayerCommandRequest,
    ListEntitiesRequest,
    SubscribeHomeAssistantStatesRequest,
)
from aioesphomeapi.model import MediaPlayerCommand, MediaPlayerState
from google.protobuf import message

if TYPE_CHECKING:
    from src.core.esphome_protocol import ESPHomeProtocol

logger = logging.getLogger(__name__)


class MediaPlayerEntity:
    """
    MediaPlayer Entity

    References linux-voice-assistant's MediaPlayerEntity implementation
    """

    def __init__(
        self,
        server: "ESPHomeProtocol",
        key: int,
        name: str,
        object_id: str,
    ):
        """
        Initialize MediaPlayer entity

        Args:
            server: ESPHome protocol server
            key: Entity key
            name: Entity name
            object_id: Object ID
        """
        self.server = server
        self.key = key
        self.name = name
        self.object_id = object_id

        # State
        self.state = MediaPlayerState.IDLE
        self.volume = 1.0
        self.muted = False

        # Player (uses player from server.state)
        self._playlist: List[str] = []
        self._done_callback: Optional[Callable] = None

        logger.info(f"MediaPlayer entity initialized: {name}")

    def play(
        self,
        url: Union[str, List[str]],
        announcement: bool = False,
        done_callback: Optional[Callable[[], None]] = None,
    ) -> Iterable[message.Message]:
        """
        Play audio

        Args:
            url: Audio URL or URL list
            announcement: Whether it's an announcement
            done_callback: Playback completion callback

        Yields:
            State update messages
        """
        if isinstance(url, str):
            self._playlist = [url]
        else:
            self._playlist = list(url)

        self._done_callback = done_callback

        if announcement:
            # Announcement mode
            if self.server.state.music_player.is_playing:
                # Pause music, play announcement, then resume
                self.server.state.music_player.pause()
                self._play_next(
                    done_callback=lambda: self._call_all(
                        self.server.state.music_player.resume,
                        done_callback
                    )
                )
            else:
                # Play announcement directly
                self._play_next(
                    done_callback=lambda: self._call_all(
                        lambda: self._update_state_and_send(MediaPlayerState.IDLE),
                        done_callback
                    )
                )
        else:
            # Music mode
            self._play_next(
                done_callback=lambda: self._call_all(
                    lambda: self._update_state_and_send(MediaPlayerState.IDLE),
                    done_callback
                )
            )

        yield self._update_state(MediaPlayerState.PLAYING)

    def _play_next(self, done_callback: Optional[Callable] = None) -> None:
        """Play next URL"""
        if not self._playlist:
            if done_callback:
                done_callback()
            return

        url = self._playlist.pop(0)
        logger.info(f"Playing: {url}")

        def on_done():
            if self._playlist:
                self._play_next(done_callback)
            elif done_callback:
                done_callback()

        self.server.state.tts_player.play(url, done_callback=on_done)

    def _call_all(self, *funcs) -> None:
        """Call all functions"""
        for func in funcs:
            if func:
                try:
                    func()
                except Exception as e:
                    logger.error(f"Callback error: {e}")

    def _update_state_and_send(self, new_state: MediaPlayerState) -> None:
        """Update state and send"""
        self.state = new_state
        self.server.send_messages([self._get_state_message()])

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """
        Handle message

        Args:
            msg: Message

        Yields:
            Response messages
        """
        if isinstance(msg, MediaPlayerCommandRequest) and msg.key == self.key:
            # Check if has media_url
            if msg.has_media_url:
                announcement = msg.has_announcement and msg.announcement
                yield from self.play(msg.media_url, announcement=announcement)
            elif msg.has_command:
                if msg.command == MediaPlayerCommand.PAUSE:
                    self.server.state.music_player.pause()
                    yield self._update_state(MediaPlayerState.PAUSED)
                elif msg.command == MediaPlayerCommand.PLAY:
                    self.server.state.music_player.resume()
                    yield self._update_state(MediaPlayerState.PLAYING)
                elif msg.command == MediaPlayerCommand.STOP:
                    self.server.state.music_player.stop()
                    self.server.state.tts_player.stop()
                    yield self._update_state(MediaPlayerState.IDLE)
            elif msg.has_volume:
                volume = int(msg.volume * 100)
                self.server.state.music_player.set_volume(volume)
                self.server.state.tts_player.set_volume(volume)
                self.volume = msg.volume
                yield self._update_state(self.state)
            elif msg.has_mute:
                self.muted = msg.mute
                # TODO: Implement mute
                yield self._update_state(self.state)

        elif isinstance(msg, ListEntitiesRequest):
            yield self.get_entity_definition()

        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            yield self._get_state_message()

    def get_entity_definition(self) -> ListEntitiesMediaPlayerResponse:
        """Get entity definition"""
        return ListEntitiesMediaPlayerResponse(
            object_id=self.object_id,
            key=self.key,
            name=self.name,
            supports_pause=True,
        )

    def get_state(self) -> MediaPlayerStateResponse:
        """Get current state"""
        return self._get_state_message()

    def _update_state(self, new_state: MediaPlayerState) -> MediaPlayerStateResponse:
        """Update state"""
        self.state = new_state
        return self._get_state_message()

    def _get_state_message(self) -> MediaPlayerStateResponse:
        """Get state message"""
        return MediaPlayerStateResponse(
            key=self.key,
            state=self.state,
            volume=self.volume,
            muted=self.muted,
        )
