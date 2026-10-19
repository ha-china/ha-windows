"""
Local event stream for custom overlays and integrations.

Opt-in with ``--event-port PORT``. While enabled, voice assistant events are
streamed as newline-delimited JSON (one object per line, UTF-8) over TCP,
bound to 127.0.0.1 only. The stream is read-only: anything a client sends is
ignored. Any number of clients may connect; each first receives a ``hello``
message with the current phase, then live events.

Every message has ``v`` (protocol version), ``type`` and ``ts`` (Unix time in
seconds). Types in protocol version 1:

    hello      device, version, protocol, phase
    phase      phase: idle | listening | thinking | replying | error | not_ready
    wake_word  phrase
    stt        text   (what the user said)
    tts        text   (the assistant's reply)
    announce   text   (an announcement pushed from Home Assistant)
    info       code, text
    error      code, message

Consumers should ignore unknown types and fields so the protocol can grow.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, Optional, Set

logger = logging.getLogger(__name__)

PROTOCOL_VERSION = 1
LOCALHOST = "127.0.0.1"

# Keep each line bounded, and drop clients that stop reading instead of
# buffering for them forever.
MAX_TEXT_LENGTH = 4000
MAX_CLIENT_BUFFER = 256 * 1024
_TEXT_FIELDS = ("text", "message", "phrase")


class EventStreamServer:
    """Broadcast voice assistant events to local TCP clients as JSON lines."""

    def __init__(self, port: int, device_name: str = "", version: str = "", host: str = LOCALHOST):
        self.host = host
        self.port = port
        self.device_name = device_name
        self.version = version
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._server: Optional[asyncio.base_events.Server] = None
        self._writers: Set[asyncio.StreamWriter] = set()
        self._phase = "idle"

    @property
    def is_running(self) -> bool:
        return self._server is not None

    @property
    def client_count(self) -> int:
        return len(self._writers)

    async def start(self) -> bool:
        """Start listening. Returns False (and logs) if the port is unavailable."""
        self._loop = asyncio.get_running_loop()
        try:
            self._server = await asyncio.start_server(self._handle_client, self.host, self.port)
        except OSError as e:
            logger.error(f"Event stream could not listen on {self.host}:{self.port}: {e}")
            self._server = None
            return False
        sockets = self._server.sockets or []
        if sockets:
            self.port = sockets[0].getsockname()[1]
        logger.info(f"Event stream listening on {self.host}:{self.port}")
        return True

    async def stop(self) -> None:
        """Stop listening and disconnect all clients."""
        server, self._server = self._server, None
        for writer in list(self._writers):
            self._drop(writer)
        if server is not None:
            server.close()
            try:
                await server.wait_closed()
            except Exception as e:
                logger.debug(f"Event stream close error: {e}")

    def publish(self, event_type: str, **fields: Any) -> None:
        """Queue an event for all clients. Safe to call from any thread."""
        loop = self._loop
        if loop is None or self._server is None or loop.is_closed():
            return
        if event_type == "phase" and isinstance(fields.get("phase"), str):
            self._phase = fields["phase"]
        data = self._encode(event_type, fields)
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        if running is loop:
            self._broadcast(data)
            return
        try:
            loop.call_soon_threadsafe(self._broadcast, data)
        except RuntimeError:
            # Loop closed between the check and the call (shutdown race)
            pass

    # ------------------------------------------------------------------ internals

    def _encode(self, event_type: str, fields: dict) -> bytes:
        message = {"v": PROTOCOL_VERSION, "type": event_type, "ts": round(time.time(), 3)}
        for key, value in fields.items():
            if key in _TEXT_FIELDS and isinstance(value, str) and len(value) > MAX_TEXT_LENGTH:
                value = value[:MAX_TEXT_LENGTH]
            message[key] = value
        return (json.dumps(message, ensure_ascii=False, default=str) + "\n").encode("utf-8")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        self._writers.add(writer)
        logger.info(f"Event stream client connected ({len(self._writers)} total)")
        writer.write(
            self._encode(
                "hello",
                {
                    "device": self.device_name,
                    "version": self.version,
                    "protocol": PROTOCOL_VERSION,
                    "phase": self._phase,
                },
            )
        )
        try:
            # Input is ignored; reading only detects the client going away.
            while await reader.read(4096):
                pass
        except (ConnectionError, OSError):
            pass
        finally:
            self._drop(writer)
            logger.info(f"Event stream client disconnected ({len(self._writers)} left)")

    def _broadcast(self, data: bytes) -> None:
        for writer in list(self._writers):
            try:
                if writer.is_closing():
                    self._drop(writer)
                    continue
                if writer.transport.get_write_buffer_size() > MAX_CLIENT_BUFFER:
                    logger.warning("Event stream client is not reading; disconnecting it")
                    self._drop(writer)
                    continue
                writer.write(data)
            except Exception as e:
                logger.debug(f"Event stream write failed: {e}")
                self._drop(writer)

    def _drop(self, writer: asyncio.StreamWriter) -> None:
        self._writers.discard(writer)
        try:
            writer.close()
        except Exception:
            pass


# Module-level access so components without a reference to the server
# (conversation handling, announcements) can publish. A no-op when disabled.
_server: Optional[EventStreamServer] = None


def set_server(server: Optional[EventStreamServer]) -> None:
    """Register (or clear with None) the server used by publish()."""
    global _server
    _server = server


def publish(event_type: str, **fields: Any) -> None:
    """Publish an event if the event stream is enabled. Never raises."""
    server = _server
    if server is None:
        return
    try:
        server.publish(event_type, **fields)
    except Exception as e:
        logger.debug(f"Event stream publish failed: {e}")
