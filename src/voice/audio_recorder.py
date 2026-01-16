"""
Audio Recording Module
Uses soundcard library to record microphone audio
"""

import asyncio
import logging
import threading
from typing import Optional, Callable
from queue import Queue

import numpy as np

# Fix numpy.fromstring deprecation for soundcard compatibility
if not hasattr(np, 'fromstring'):
    np.fromstring = lambda s, dtype=None, count=-1, sep='': np.frombuffer(s, dtype=dtype, count=count)

import soundcard

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class AudioRecorder:
    """Audio Recorder"""

    # Audio parameters
    SAMPLE_RATE = 16000  # 16kHz (ESPHome Voice Assistant standard)
    CHANNELS = 1  # Mono
    BLOCK_SIZE = 1024  # Samples per read

    def __init__(self, device: Optional[str] = None):
        """
        Initialize audio recorder

        Args:
            device: Audio device name (None = default microphone)
        """
        self.device = device
        self.mic = None
        self.is_recording = False
        self.audio_queue: Queue[bytes] = Queue()
        self.recording_thread: Optional[threading.Thread] = None

    @staticmethod
    def list_microphones() -> list[str]:
        """
        List all available microphones

        Returns:
            list[str]: List of microphone names
        """
        try:
            mics = soundcard.all_microphones()
            return [mic.name for mic in mics]
        except Exception as e:
            logger.error(f"Failed to get microphone list: {e}")
            return []

    def _get_microphone(self):
        """Get microphone device"""
        if self.device:
            # Find microphone by name
            mics = soundcard.all_microphones()
            for mic in mics:
                if mic.name == self.device:
                    return mic
            logger.warning(f"Specified microphone not found: {self.device}, using default microphone")

        # Use default microphone
        return soundcard.default_microphone()

    def start_recording(self, audio_callback: Optional[Callable[[bytes], None]] = None):
        """
        Start recording

        Args:
            audio_callback: Audio data callback function
        """
        if self.is_recording:
            logger.warning("Recording already in progress")
            return

        try:
            self.mic = self._get_microphone()
            logger.info(f"Using microphone: {self.mic.name}")

            self.is_recording = True

            # Start recording thread
            self.recording_thread = threading.Thread(
                target=self._record_loop,
                args=(audio_callback,),
                daemon=True
            )
            self.recording_thread.start()

            logger.info("Recording started")

        except Exception as e:
            logger.error(f"Failed to start recording: {e}")
            self.is_recording = False
            raise

    def stop_recording(self):
        """Stop recording"""
        if not self.is_recording:
            return

        self.is_recording = False

        # Wait for recording thread to finish
        if self.recording_thread:
            self.recording_thread.join(timeout=2.0)
            self.recording_thread = None

        logger.info("Recording stopped")

    def _record_loop(self, audio_callback: Optional[Callable[[bytes], None]]):
        """
        Recording loop (runs in separate thread)

        Args:
            audio_callback: Audio data callback function
        """
        # Initialize COM for this thread (required on Windows)
        try:
            import pythoncom
            pythoncom.CoInitialize()
        except ImportError:
            pass  # pythoncom not available, might work without it
        except Exception:
            pass

        try:
            with self.mic.recorder(
                samplerate=self.SAMPLE_RATE,
                channels=self.CHANNELS,
                blocksize=self.BLOCK_SIZE
            ) as recorder:
                while self.is_recording:
                    # Record audio block
                    audio_array = recorder.record(numframes=self.BLOCK_SIZE)

                    # Convert to 16-bit signed integer PCM format
                    audio_pcm = self._array_to_pcm(audio_array)

                    # Call callback function or put in queue
                    if audio_callback:
                        audio_callback(audio_pcm)
                    else:
                        self.audio_queue.put(audio_pcm)

        except Exception as e:
            logger.error(f"Recording loop error: {e}")
            self.is_recording = False

    def _array_to_pcm(self, audio_array: np.ndarray) -> bytes:
        """
        Convert NumPy audio array to PCM byte stream

        Args:
            audio_array: Audio array (float32, range -1.0 to 1.0)

        Returns:
            bytes: PCM format audio data (16-bit signed little-endian)
        """
        # Clip range to -1.0 to 1.0
        clipped = np.clip(audio_array, -1.0, 1.0)

        # Convert to 16-bit signed integer
        int16_data = (clipped * 32767.0).astype(np.int16)

        # Convert to byte stream (little-endian)
        return int16_data.tobytes()

    def get_audio_chunk(self, timeout: float = 1.0) -> Optional[bytes]:
        """
        Get audio chunk (blocking)

        Args:
            timeout: Timeout in seconds

        Returns:
            Optional[bytes]: Audio data, or None if timeout
        """
        try:
            return self.audio_queue.get(timeout=timeout)
        except Exception:
            return None

    async def get_audio_chunk_async(self) -> Optional[bytes]:
        """
        Get audio chunk asynchronously

        Returns:
            Optional[bytes]: Audio data
        """
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.get_audio_chunk)

    @staticmethod
    def create_silence(duration: float = 0.1) -> bytes:
        """
        Create silent audio

        Args:
            duration: Silence duration in seconds

        Returns:
            bytes: PCM format silence data
        """
        num_samples = int(AudioRecorder.SAMPLE_RATE * duration)
        silence = np.zeros(num_samples, dtype=np.int16)
        return silence.tobytes()


class AsyncAudioRecorder:
    """Async audio recorder wrapper"""

    def __init__(self, device: Optional[str] = None):
        """
        Initialize async audio recorder

        Args:
            device: Audio device name
        """
        self.recorder = AudioRecorder(device)
        self.audio_queue: asyncio.Queue[bytes] = asyncio.Queue()

    async def start_recording(self):
        """Start recording"""
        self.recorder.start_recording(self._on_audio_data)
        logger.info("Async recording started")

    def _on_audio_data(self, audio_data: bytes):
        """
        Audio data callback

        Args:
            audio_data: Audio data
        """
        # Called in recording thread, put data in async queue
        try:
            asyncio.run_coroutine_threadsafe(
                self.audio_queue.put(audio_data),
                asyncio.get_event_loop()
            )
        except Exception as e:
            logger.error(f"Audio data callback failed: {e}")

    def stop_recording(self):
        """Stop recording"""
        self.recorder.stop_recording()
        logger.info("Async recording stopped")

    async def get_audio_chunk(self) -> bytes:
        """
        Get audio chunk

        Returns:
            bytes: Audio data
        """
        return await self.audio_queue.get()


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    async def test_recording():
        """Test recording"""
        logger.info("Testing audio recorder")

        # List microphones
        mics = AudioRecorder.list_microphones()
        logger.info(f"Available microphones ({len(mics)}):")
        for i, mic in enumerate(mics, 1):
            logger.info(f"  {i}. {mic}")

        # Create recorder
        recorder = AsyncAudioRecorder()

        # Record for 5 seconds
        logger.info("\nStarting 5 second recording...")
        await recorder.start_recording()

        chunks = []
        end_time = asyncio.get_event_loop().time() + 5

        while asyncio.get_event_loop().time() < end_time:
            try:
                chunk = await asyncio.wait_for(
                    recorder.get_audio_chunk(),
                    timeout=0.5
                )
                if chunk:
                    chunks.append(chunk)
                    logger.debug(f"Received audio chunk: {len(chunk)} bytes")
            except asyncio.TimeoutError:
                break

        recorder.stop_recording()

        # Statistics
        total_bytes = sum(len(chunk) for chunk in chunks)
        total_seconds = total_bytes / 2 / 16000  # 16-bit, 16kHz
        logger.info("Recording complete:")
        logger.info(f"  Total bytes: {total_bytes}")
        logger.info(f"  Total duration: {total_seconds:.2f} seconds")
        logger.info(f"  Chunk count: {len(chunks)}")

    # Run test
    asyncio.run(test_recording())
