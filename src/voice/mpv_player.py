"""
Audio Player Module

Uses pygame for streaming audio playback from URLs.
Supports direct URL streaming without downloading first.
"""

import asyncio
import io
import logging
import os
import tempfile
import threading
import time
from typing import Optional, Dict, Callable
from enum import Enum

from src.i18n import get_i18n
from aioesphomeapi.api_pb2 import (
    ListEntitiesMediaPlayerResponse,
    MediaPlayerStateResponse,
    MediaPlayerSupportedFormat,
    MediaPlayerCommandRequest,
    MediaPlayerState,
)

logger = logging.getLogger(__name__)
_i18n = get_i18n()

# Import volume controller from models
from src.core.models import get_volume_controller

# Try to import pygame for streaming playback
_pygame_available = False
try:
    import pygame
    pygame.mixer.init()
    _pygame_available = True
    logger.info("pygame available for streaming audio playback")
except ImportError:
    logger.warning("pygame not available, falling back to winsound (no streaming)")
except Exception as e:
    logger.warning(f"pygame init failed: {e}, falling back to winsound")


class PlaybackState(Enum):
    """Playback state"""
    STOPPED = "stopped"
    PLAYING = "playing"
    PAUSED = "paused"


class AudioPlayer:
    """
    Audio player with streaming URL support.

    Uses pygame for streaming playback, falls back to winsound for local files.
    Supports duck/unduck for volume control during voice assistant interactions.
    """

    def __init__(self, audio_device: Optional[str] = None):
        """
        Initialize audio player

        Args:
            audio_device: Audio output device name (None = default device)
        """
        self._playing = False
        self.state = PlaybackState.STOPPED
        self._current_sound = None
        self._done_callback: Optional[Callable] = None
        self._play_thread: Optional[threading.Thread] = None
        self._volume_controller = get_volume_controller()
        logger.info(f"Audio player initialized (pygame={_pygame_available})")

    def play_url(self, url: str, announcement: bool = False) -> None:
        """
        Play audio URL or file path (supports streaming)

        Args:
            url: Audio URL or file path
            announcement: Whether it's an announcement
        """
        try:
            logger.info(f"Playing audio: {url}")

            # For HTTP URLs, use streaming playback
            if url.startswith(('http://', 'https://')):
                self._play_url_stream(url)
            # For local files
            elif url.startswith('file://') or url.startswith(('C:', 'D:', 'E:', 'F:', '\\', '/')):
                # Extract file path
                if url.startswith('file://'):
                    file_path = url[7:]
                else:
                    file_path = url

                if _pygame_available:
                    self._play_with_pygame(file_path)
                else:
                    self._play_wav_file(file_path)
            else:
                logger.warning(f"Unsupported URL scheme: {url}")

            self.state = PlaybackState.PLAYING

        except Exception as e:
            logger.error(f"Playback failed: {e}")
            self.state = PlaybackState.STOPPED
            raise

    def _play_url_stream(self, url: str) -> None:
        """
        Stream audio from URL using pygame (no full download needed)

        Args:
            url: HTTP/HTTPS audio URL
        """
        if not _pygame_available:
            logger.warning("pygame not available, cannot stream URL directly")
            # Fall back to download-then-play
            self._download_and_play(url)
            return

        try:
            import urllib.request

            # pygame.mixer.music can stream from URL
            # Use urllib to create a streaming connection
            logger.info(f"Streaming audio from URL: {url}")

            # For pygame, we need to download to a temp file but we can start
            # playing while still downloading using chunked approach
            # However, pygame.mixer.music.load() can accept URLs directly in some cases

            # Try direct URL loading first (works for some URLs)
            try:
                pygame.mixer.music.load(url)
                pygame.mixer.music.play()
                self._playing = True
                logger.info("Started streaming playback via pygame.mixer.music")
                return
            except Exception as e:
                logger.debug(f"Direct URL load failed: {e}, trying chunked download")

            # Fall back to chunked streaming download
            self._stream_with_chunks(url)

        except Exception as e:
            logger.error(f"URL streaming failed: {e}")
            raise

    def _stream_with_chunks(self, url: str) -> None:
        """
        Stream audio by downloading in chunks and playing as soon as possible

        Args:
            url: Audio URL
        """
        import urllib.request

        try:
            # Create temp file for streaming
            suffix = ".mp3" if ".mp3" in url else ".wav"
            tmp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
            tmp_path = tmp_file.name

            # Download with streaming
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=30) as response:
                # Read first chunk to start playback quickly
                first_chunk = response.read(32768)  # 32KB initial chunk
                tmp_file.write(first_chunk)
                tmp_file.flush()

                # Start playback immediately with first chunk
                # (for WAV files, header is in first chunk)
                def start_playback():
                    time.sleep(0.1)  # Small delay for file write
                    try:
                        pygame.mixer.music.load(tmp_path)
                        pygame.mixer.music.play()
                        self._playing = True
                        logger.info("Started playback while downloading")
                    except Exception as e:
                        logger.debug(f"Early playback failed: {e}")

                playback_thread = threading.Thread(target=start_playback, daemon=True)
                playback_thread.start()

                # Continue downloading rest of file
                while True:
                    chunk = response.read(8192)
                    if not chunk:
                        break
                    tmp_file.write(chunk)
                    tmp_file.flush()

            tmp_file.close()

            # If playback hasn't started yet, start it now
            if not self._playing:
                pygame.mixer.music.load(tmp_path)
                pygame.mixer.music.play()
                self._playing = True

            # Schedule cleanup
            def cleanup():
                # Wait for playback to finish
                while pygame.mixer.music.get_busy():
                    time.sleep(0.5)
                time.sleep(0.5)
                try:
                    os.unlink(tmp_path)
                except:
                    pass

            threading.Thread(target=cleanup, daemon=True).start()

        except Exception as e:
            logger.error(f"Chunked streaming failed: {e}")
            raise

    def _download_and_play(self, url: str) -> None:
        """
        Download full file then play (fallback when streaming not available)

        Args:
            url: Audio URL
        """
        import urllib.request

        suffix = ".mp3" if ".mp3" in url else ".wav"
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            urllib.request.urlretrieve(url, tmp.name)
            tmp_path = tmp.name

        self._play_wav_file(tmp_path)

        # Cleanup
        def cleanup():
            time.sleep(3)
            try:
                os.unlink(tmp_path)
            except:
                pass

        threading.Thread(target=cleanup, daemon=True).start()

    def _play_with_pygame(self, file_path: str) -> None:
        """Play audio file using pygame"""
        try:
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            pygame.mixer.music.load(file_path)
            pygame.mixer.music.play()
            self._playing = True
            logger.info(f"Playing with pygame: {file_path}")

        except Exception as e:
            logger.error(f"pygame playback failed: {e}")
            raise

    def _play_wav_file(self, file_path: str) -> None:
        """Play WAV file using winsound"""
        try:
            import winsound

            # Check if file exists
            if not os.path.exists(file_path):
                raise FileNotFoundError(f"File not found: {file_path}")

            # Play asynchronously
            winsound.PlaySound(file_path, winsound.SND_FILENAME | winsound.SND_ASYNC)

        except ImportError:
            logger.error("winsound not available (not Windows?)")
            raise
        except Exception as e:
            logger.error(f"winsound playback failed: {e}")
            raise

    def play_audio_data(self, audio_data: bytes, format: str = "wav") -> None:
        """
        Play audio data directly

        Args:
            audio_data: Audio binary data
            format: Audio format (wav, mp3, etc.)
        """
        try:
            if _pygame_available:
                # Use pygame to play from memory
                audio_io = io.BytesIO(audio_data)
                pygame.mixer.music.load(audio_io)
                pygame.mixer.music.play()
                self._playing = True
                logger.info(f"Playing audio data with pygame (size={len(audio_data)})")
            else:
                # Fall back to temp file approach
                suffix = f".{format}"
                with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                    tmp.write(audio_data)
                    tmp_path = tmp.name

                logger.info(f"Playing audio data via temp file (size={len(audio_data)})")
                self._play_wav_file(tmp_path)

                # Cleanup temp file
                def cleanup():
                    time.sleep(2)
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass

                threading.Thread(target=cleanup, daemon=True).start()

        except Exception as e:
            logger.error(f"Failed to play audio data: {e}")
            raise

    def stop(self) -> None:
        """Stop playback"""
        try:
            if _pygame_available:
                pygame.mixer.music.stop()
            else:
                import winsound
                winsound.PlaySound(None, winsound.SND_PURGE)

            self.state = PlaybackState.STOPPED
            self._playing = False
            logger.debug("Playback stopped")

        except Exception as e:
            logger.error(f"Failed to stop playback: {e}")

    def pause(self) -> None:
        """Pause playback"""
        if _pygame_available:
            pygame.mixer.music.pause()
            self.state = PlaybackState.PAUSED
            logger.debug("Playback paused")
        else:
            logger.warning("Pause not supported by winsound")

    def resume(self) -> None:
        """Resume playback"""
        if _pygame_available:
            pygame.mixer.music.unpause()
            self.state = PlaybackState.PLAYING
            logger.debug("Playback resumed")
        else:
            logger.warning("Resume not supported by winsound")

    def cleanup(self) -> None:
        """Cleanup resources"""
        self.stop()
        logger.debug("Audio player cleaned up")

    def play(self, url: str, done_callback: Optional[Callable] = None) -> None:
        """
        Play audio URL with optional completion callback (compatible with models.py interface)

        Args:
            url: Audio URL or file path
            done_callback: Callback to invoke when playback finishes
        """
        self._done_callback = done_callback
        
        # Play in background thread to support callback
        self._play_thread = threading.Thread(
            target=self._play_with_callback,
            args=(url,),
            daemon=True
        )
        self._play_thread.start()

    def _play_with_callback(self, url: str) -> None:
        """Play audio and invoke callback when done"""
        try:
            self.play_url(url)
            
            # Wait for playback to complete
            if _pygame_available:
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
            else:
                time.sleep(2)  # Estimate for winsound
            
        except Exception as e:
            logger.error(f"Playback error: {e}")
        finally:
            self._playing = False
            self.state = PlaybackState.STOPPED
            if self._done_callback:
                try:
                    self._done_callback()
                except Exception as e:
                    logger.error(f"Error in done callback: {e}")
                finally:
                    self._done_callback = None

    @property
    def is_playing(self) -> bool:
        """Check if currently playing"""
        if _pygame_available:
            return pygame.mixer.music.get_busy()
        return self._playing

    def duck(self) -> None:
        """Lower system volume (duck)"""
        self._volume_controller.duck()

    def unduck(self) -> None:
        """Restore system volume (unduck)"""
        self._volume_controller.unduck()


class AsyncAudioPlayer:
    """Async wrapper for audio player"""

    def __init__(self, audio_device: Optional[str] = None):
        """Initialize async audio player"""
        self.player = AudioPlayer(audio_device)
        self._playback_done = asyncio.Event()

    async def play_url(
        self,
        url: str,
        announcement: bool = False,
        wait: bool = True
    ) -> None:
        """
        Play audio URL

        Args:
            url: Audio URL
            announcement: Whether it's an announcement
            wait: Whether to wait for playback to complete
        """
        self._playback_done.clear()

        loop = asyncio.get_event_loop()
        await loop.run_in_executor(
            None,
            lambda: self.player.play_url(url, announcement)
        )

        if wait:
            await self._wait_for_playback_end()

    async def play_file(self, file_path: str, wait: bool = True) -> None:
        """Play local audio file"""
        await self.play_url(file_path, wait=wait)

    async def stop(self) -> None:
        """Stop playback"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.player.stop)
        self._playback_done.set()

    async def pause(self) -> None:
        """Pause playback"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.player.pause)

    async def resume(self) -> None:
        """Resume playback"""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self.player.resume)

    async def _wait_for_playback_end(self, timeout: float = 30.0) -> None:
        """Wait for playback to end"""
        try:
            if _pygame_available:
                # Wait for pygame to finish playing
                start_time = time.time()
                while pygame.mixer.music.get_busy():
                    if time.time() - start_time > timeout:
                        logger.warning("Playback timeout reached")
                        break
                    await asyncio.sleep(0.2)
            else:
                # For winsound, just wait a reasonable time
                await asyncio.sleep(2)
        except Exception as e:
            logger.warning(f"Wait for playback end error: {e}")

    def cleanup(self) -> None:
        """Cleanup resources"""
        self.player.cleanup()


# Convenience functions
def play_audio_url(url: str, announcement: bool = False) -> None:
    """Play audio URL (synchronous)"""
    player = AudioPlayer()
    try:
        player.play_url(url, announcement)
    finally:
        player.cleanup()


async def play_audio_url_async(
    url: str,
    announcement: bool = False,
    wait: bool = True
) -> None:
    """Play audio URL (asynchronous)"""
    player = AsyncAudioPlayer()
    try:
        await player.play_url(url, announcement, wait)
    finally:
        player.cleanup()


class ESPHomeVoicePlayer:
    """
    ESPHome Voice Assistant Player

    Handles TTS audio playback for ESPHome Voice Assistant.
    Uses Windows native APIs - no external dependencies.
    """

    def __init__(self):
        """Initialize ESPHome voice player"""
        self._player: Optional[AudioPlayer] = None
        self._lock = threading.Lock()
        self._voice_status = "Idle"
        logger.info("ESPHome voice player initialized")

    def play_tts_audio(self, audio_data: bytes, format: str = "wav") -> Dict:
        """
        Play TTS audio data

        Args:
            audio_data: Audio binary data
            format: Audio format (wav, mp3, etc.)

        Returns:
            Dict with success status
        """
        try:
            if self._player is None:
                self._player = AudioPlayer()

            with self._lock:
                self._player.play_audio_data(audio_data, format=format)

            logger.info(_i18n.t('tts_play_started'))
            self._voice_status = "Speaking"

            return {"success": True, "finished": True}

        except Exception as e:
            logger.error(_i18n.t('tts_play_failed') + f": {e}")
            self._voice_status = "Error"
            return {"success": False, "finished": True, "error": str(e)}

    async def reset_status(self):
        """Reset voice status to Idle after a delay"""
        await asyncio.sleep(1)
        self._voice_status = "Idle"

    def get_status(self) -> str:
        """Get current voice status"""
        return self._voice_status

    def cleanup(self):
        """Cleanup resources"""
        if self._player:
            self._player.cleanup()
            self._player = None
        logger.info("ESPHome voice player cleaned up")


# ESPHome media player key
MEDIA_PLAYER_KEY = 100


def get_media_player_entity_definition() -> ListEntitiesMediaPlayerResponse:
    """
    Get media player entity definition for ESPHome

    Returns:
        ListEntitiesMediaPlayerResponse: Entity definition
    """
    return ListEntitiesMediaPlayerResponse(
        object_id="media_player",
        key=MEDIA_PLAYER_KEY,
        name="Media Player",
        icon="mdi:speaker",
        supports_pause=False,
        supported_formats=[
            MediaPlayerSupportedFormat(
                format="wav",
                purpose=0  # ANNOUNCEMENT_PURPOSE
            ),
            MediaPlayerSupportedFormat(
                format="mp3",
                purpose=0  # ANNOUNCEMENT_PURPOSE
            ),
        ],
    )


def get_media_player_state() -> MediaPlayerStateResponse:
    """
    Get current media player state

    Returns:
        MediaPlayerStateResponse: Current state
    """
    return MediaPlayerStateResponse(
        key=MEDIA_PLAYER_KEY,
        state=MediaPlayerState.MEDIA_PLAYER_STATE_IDLE,
        volume=1.0,
        muted=False
    )


async def handle_media_player_command(player: ESPHomeVoicePlayer, msg: MediaPlayerCommandRequest) -> None:
    """
    Handle media player command from Home Assistant

    Args:
        player: ESPHome voice player instance
        msg: Media player command request
    """
    logger.info(f"Received media player command: {msg.command}")
    logger.info(f"  has media_url: {msg.HasField('media_url')}")
    if msg.HasField('media_url'):
        logger.info(f"  media_url: {msg.media_url}")
    logger.info(f"  has volume: {msg.HasField('volume')}")
    if msg.HasField('volume'):
        logger.info(f"  volume: {msg.volume}")

    if msg.command == 0:  # Unknown/No command
        # Try to play if media_url is provided
        if msg.HasField('media_url'):
            logger.info(f"Command 0 but has media_url, trying to play: {msg.media_url}")
            await _play_audio_from_url(player, msg.media_url)
        else:
            logger.info("Command 0 and no media_url, ignoring")
    elif msg.command == 1:  # Play
        if msg.HasField('media_url'):
            logger.info(f"Playing audio URL: {msg.media_url}")
            await _play_audio_from_url(player, msg.media_url)
        else:
            logger.info("Play command but no media_url")
    elif msg.command == 2:  # Pause
        logger.info("Pause playback (not supported)")
        # Pause not supported by winsound
    elif msg.command == 3:  # Stop
        logger.info("Stop playback")
        player.cleanup()
    elif msg.command == 4:  # Mute
        logger.info("Mute")
        # Mute not supported by winsound
    elif msg.command == 5:  # Volume
        if msg.HasField('volume'):
            logger.info(f"Set volume: {msg.volume}")
            # Volume control not supported by winsound
    else:
        logger.info(f"Unknown command: {msg.command}")


async def _play_audio_from_url(player: ESPHomeVoicePlayer, url: str) -> None:
    """
    Play audio from URL (streaming)

    Args:
        player: ESPHome voice player instance
        url: Audio URL
    """
    try:
        # Use the AudioPlayer's streaming capability
        audio_player = AudioPlayer()
        loop = asyncio.get_event_loop()

        # Play URL with streaming support
        await loop.run_in_executor(None, lambda: audio_player.play_url(url))

        # Wait for playback to complete
        if _pygame_available:
            while pygame.mixer.music.get_busy():
                await asyncio.sleep(0.2)
        else:
            await asyncio.sleep(2)

        audio_player.cleanup()

    except Exception as e:
        logger.error(f"Failed to play audio: {e}")


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    import sys

    async def test_player():
        """Test audio player"""
        logger.info("Testing audio player")

        if len(sys.argv) > 1:
            url = sys.argv[1]
        else:
            logger.info("\nUsage: python mpv_player.py <audio file>")
            return

        logger.info(f"\nPlaying: {url}")
        player = AsyncAudioPlayer()

        try:
            await player.play_url(url, wait=True)
            logger.info("Playback complete")
        finally:
            player.cleanup()

    # Run test
    asyncio.run(test_player())
