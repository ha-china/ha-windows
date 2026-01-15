"""
Media Player Entity Module

参考 linux-voice-assistant 的 entity.py 实现
提供 MediaPlayer 实体给 Home Assistant
"""

import asyncio
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
    MediaPlayer 实体
    
    参考 linux-voice-assistant 的 MediaPlayerEntity 实现
    """

    def __init__(
        self,
        server: "ESPHomeProtocol",
        key: int,
        name: str,
        object_id: str,
    ):
        """
        初始化 MediaPlayer 实体
        
        Args:
            server: ESPHome 协议服务器
            key: 实体 key
            name: 实体名称
            object_id: 对象 ID
        """
        self.server = server
        self.key = key
        self.name = name
        self.object_id = object_id
        
        # 状态
        self.state = MediaPlayerState.IDLE
        self.volume = 1.0
        self.muted = False
        
        # 播放器（使用 server.state 中的播放器）
        self._playlist: List[str] = []
        self._done_callback: Optional[Callable] = None
        
        logger.info(f"MediaPlayer 实体初始化: {name}")

    def play(
        self,
        url: Union[str, List[str]],
        announcement: bool = False,
        done_callback: Optional[Callable[[], None]] = None,
    ) -> Iterable[message.Message]:
        """
        播放音频
        
        Args:
            url: 音频 URL 或 URL 列表
            announcement: 是否是播报
            done_callback: 播放完成回调
            
        Yields:
            状态更新消息
        """
        if isinstance(url, str):
            self._playlist = [url]
        else:
            self._playlist = list(url)
        
        self._done_callback = done_callback
        
        if announcement:
            # 播报模式
            if self.server.state.music_player.is_playing:
                # 暂停音乐，播放播报，然后恢复
                self.server.state.music_player.pause()
                self._play_next(
                    done_callback=lambda: self._call_all(
                        self.server.state.music_player.resume,
                        done_callback
                    )
                )
            else:
                # 直接播放播报
                self._play_next(
                    done_callback=lambda: self._call_all(
                        lambda: self._update_state_and_send(MediaPlayerState.IDLE),
                        done_callback
                    )
                )
        else:
            # 音乐模式
            self._play_next(
                done_callback=lambda: self._call_all(
                    lambda: self._update_state_and_send(MediaPlayerState.IDLE),
                    done_callback
                )
            )
        
        yield self._update_state(MediaPlayerState.PLAYING)

    def _play_next(self, done_callback: Optional[Callable] = None) -> None:
        """播放下一个 URL"""
        if not self._playlist:
            if done_callback:
                done_callback()
            return
        
        url = self._playlist.pop(0)
        logger.info(f"播放: {url}")
        
        def on_done():
            if self._playlist:
                self._play_next(done_callback)
            elif done_callback:
                done_callback()
        
        self.server.state.tts_player.play(url, done_callback=on_done)

    def _call_all(self, *funcs) -> None:
        """调用所有函数"""
        for func in funcs:
            if func:
                try:
                    func()
                except Exception as e:
                    logger.error(f"回调错误: {e}")

    def _update_state_and_send(self, new_state: MediaPlayerState) -> None:
        """更新状态并发送"""
        self.state = new_state
        self.server.send_messages([self._get_state_message()])

    def handle_message(self, msg: message.Message) -> Iterable[message.Message]:
        """
        处理消息
        
        Args:
            msg: 消息
            
        Yields:
            响应消息
        """
        if isinstance(msg, MediaPlayerCommandRequest) and msg.key == self.key:
            # 检查是否有 media_url
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
                # TODO: 实现静音
                yield self._update_state(self.state)
                
        elif isinstance(msg, ListEntitiesRequest):
            yield self.get_entity_definition()
            
        elif isinstance(msg, SubscribeHomeAssistantStatesRequest):
            yield self._get_state_message()

    def get_entity_definition(self) -> ListEntitiesMediaPlayerResponse:
        """获取实体定义"""
        return ListEntitiesMediaPlayerResponse(
            object_id=self.object_id,
            key=self.key,
            name=self.name,
            supports_pause=True,
        )

    def get_state(self) -> MediaPlayerStateResponse:
        """获取当前状态"""
        return self._get_state_message()

    def _update_state(self, new_state: MediaPlayerState) -> MediaPlayerStateResponse:
        """更新状态"""
        self.state = new_state
        return self._get_state_message()

    def _get_state_message(self) -> MediaPlayerStateResponse:
        """获取状态消息"""
        return MediaPlayerStateResponse(
            key=self.key,
            state=self.state,
            volume=self.volume,
            muted=self.muted,
        )
