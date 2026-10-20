"""Tests for the opt-in local event stream (--event-port)."""

import asyncio
import json
import os
import sys
import threading
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from src.core import event_stream
from src.core.event_stream import MAX_TEXT_LENGTH, PROTOCOL_VERSION, EventStreamServer


async def _read_message(reader: asyncio.StreamReader) -> dict:
    line = await asyncio.wait_for(reader.readline(), timeout=2)
    assert line.endswith(b"\n")
    return json.loads(line.decode("utf-8"))


async def _start_server(**kwargs) -> EventStreamServer:
    server = EventStreamServer(0, device_name="test-pc", version="9.9.9", **kwargs)
    assert await server.start()
    return server


async def _connect(server: EventStreamServer):
    reader, writer = await asyncio.open_connection(server.host, server.port)
    hello = await _read_message(reader)
    return reader, writer, hello


async def _wait_for_clients(server: EventStreamServer, count: int) -> None:
    for _ in range(100):
        if server.client_count == count:
            return
        await asyncio.sleep(0.01)
    raise AssertionError(f"expected {count} clients, have {server.client_count}")


class TestEventStreamServer:
    async def test_binds_localhost_only(self):
        server = await _start_server()
        try:
            assert server.host == "127.0.0.1"
            assert server.port > 0
        finally:
            await server.stop()

    async def test_hello_on_connect(self):
        server = await _start_server()
        try:
            _, writer, hello = await _connect(server)
            assert hello["type"] == "hello"
            assert hello["v"] == PROTOCOL_VERSION
            assert hello["protocol"] == PROTOCOL_VERSION
            assert hello["device"] == "test-pc"
            assert hello["version"] == "9.9.9"
            assert hello["phase"] == "idle"
            assert isinstance(hello["ts"], float)
            writer.close()
        finally:
            await server.stop()

    async def test_hello_reports_last_phase(self):
        server = await _start_server()
        try:
            server.publish("phase", phase="thinking")
            _, writer, hello = await _connect(server)
            assert hello["phase"] == "thinking"
            writer.close()
        finally:
            await server.stop()

    async def test_publish_reaches_all_clients(self):
        server = await _start_server()
        try:
            r1, w1, _ = await _connect(server)
            r2, w2, _ = await _connect(server)
            await _wait_for_clients(server, 2)
            server.publish("tts", text="It is 21 degrees outside.")
            for reader in (r1, r2):
                msg = await _read_message(reader)
                assert msg["type"] == "tts"
                assert msg["text"] == "It is 21 degrees outside."
            w1.close()
            w2.close()
        finally:
            await server.stop()

    async def test_publish_from_another_thread(self):
        server = await _start_server()
        try:
            reader, writer, _ = await _connect(server)
            await _wait_for_clients(server, 1)
            thread = threading.Thread(target=server.publish, args=("wake_word",), kwargs={"phrase": "Jarvis"})
            thread.start()
            thread.join()
            msg = await _read_message(reader)
            assert msg["type"] == "wake_word"
            assert msg["phrase"] == "Jarvis"
            writer.close()
        finally:
            await server.stop()

    async def test_non_ascii_text_is_utf8(self):
        server = await _start_server()
        try:
            reader, writer, _ = await _connect(server)
            await _wait_for_clients(server, 1)
            server.publish("stt", text="打开客厅的灯")
            msg = await _read_message(reader)
            assert msg["text"] == "打开客厅的灯"
            writer.close()
        finally:
            await server.stop()

    async def test_long_text_is_truncated(self):
        server = await _start_server()
        try:
            reader, writer, _ = await _connect(server)
            await _wait_for_clients(server, 1)
            server.publish("tts", text="x" * (MAX_TEXT_LENGTH + 500))
            msg = await _read_message(reader)
            assert len(msg["text"]) == MAX_TEXT_LENGTH
            writer.close()
        finally:
            await server.stop()

    async def test_client_input_is_ignored(self):
        server = await _start_server()
        try:
            reader, writer, _ = await _connect(server)
            await _wait_for_clients(server, 1)
            writer.write(b'{"type": "anything"}\n')
            await writer.drain()
            server.publish("phase", phase="listening")
            msg = await _read_message(reader)
            assert msg["type"] == "phase"
            writer.close()
        finally:
            await server.stop()

    async def test_disconnected_client_is_removed(self):
        server = await _start_server()
        try:
            _, writer, _ = await _connect(server)
            await _wait_for_clients(server, 1)
            writer.close()
            await _wait_for_clients(server, 0)
            server.publish("phase", phase="idle")  # must not raise
        finally:
            await server.stop()

    async def test_hello_write_failure_is_cleaned_up(self):
        """A client that cannot even receive the hello is dropped, not leaked."""
        server = await _start_server()
        try:
            reader = MagicMock()
            reader.read = AsyncMock(side_effect=AssertionError("read must not be reached"))
            writer = MagicMock()
            writer.write = MagicMock(side_effect=ConnectionError("reset before hello"))
            await server._handle_client(reader, writer)
            assert server.client_count == 0
            writer.close.assert_called()
        finally:
            await server.stop()

    async def test_stop_disconnects_clients(self):
        server = await _start_server()
        reader, _, _ = await _connect(server)
        await _wait_for_clients(server, 1)
        await server.stop()
        assert not server.is_running
        assert await asyncio.wait_for(reader.read(), timeout=2) == b""

    async def test_port_in_use_returns_false(self):
        first = await _start_server()
        try:
            second = EventStreamServer(first.port)
            assert await second.start() is False
            assert not second.is_running
        finally:
            await first.stop()

    def test_publish_before_start_is_noop(self):
        EventStreamServer(0).publish("phase", phase="idle")


class TestModulePublish:
    def test_publish_without_server_is_noop(self):
        event_stream.set_server(None)
        event_stream.publish("phase", phase="idle")

    async def test_publish_uses_registered_server(self):
        server = await _start_server()
        event_stream.set_server(server)
        try:
            reader, writer, _ = await _connect(server)
            await _wait_for_clients(server, 1)
            event_stream.publish("announce", text="Dinner is ready")
            msg = await _read_message(reader)
            assert msg["type"] == "announce"
            assert msg["text"] == "Dinner is ready"
            writer.close()
        finally:
            event_stream.set_server(None)
            await server.stop()

    def test_publish_swallows_server_errors(self):
        class Broken:
            def publish(self, *args, **kwargs):
                raise RuntimeError("boom")

        event_stream.set_server(Broken())
        try:
            event_stream.publish("phase", phase="idle")
        finally:
            event_stream.set_server(None)


class _Recorder:
    """Stands in for the server so protocol hooks can be checked without sockets."""

    def __init__(self):
        self.events = []

    def publish(self, event_type, **fields):
        self.events.append((event_type, fields))


@pytest.fixture
def recorder():
    rec = _Recorder()
    event_stream.set_server(rec)
    yield rec
    event_stream.set_server(None)


class TestProtocolHooks:
    def _protocol(self):
        from src.core.esphome_protocol import ESPHomeProtocol
        from src.core.models import create_default_state

        return ESPHomeProtocol(create_default_state("test_device"))

    def test_pipeline_error_is_published(self, recorder):
        from aioesphomeapi.model import VoiceAssistantEventType

        protocol = self._protocol()
        protocol.handle_voice_event(
            VoiceAssistantEventType.VOICE_ASSISTANT_ERROR, {"code": "intent-failed", "message": "Agent offline"}
        )
        assert ("error", {"code": "intent-failed", "message": "Agent offline"}) in recorder.events

    def test_no_speech_is_published_as_info(self, recorder, monkeypatch):
        from aioesphomeapi.model import VoiceAssistantEventType

        protocol = self._protocol()
        monkeypatch.setattr(protocol, "_dump_debug_audio", lambda reason: None)
        protocol.handle_voice_event(VoiceAssistantEventType.VOICE_ASSISTANT_ERROR, {"code": "stt-no-text-recognized"})
        info = [fields for kind, fields in recorder.events if kind == "info"]
        assert info and info[0]["code"] == "stt-no-text-recognized"
        assert info[0]["text"]

    def test_benign_timeout_is_not_published(self, recorder):
        from aioesphomeapi.model import VoiceAssistantEventType

        protocol = self._protocol()
        protocol.handle_voice_event(VoiceAssistantEventType.VOICE_ASSISTANT_ERROR, {"code": "timeout"})
        assert [kind for kind, _ in recorder.events if kind in ("error", "info")] == []


@pytest.mark.parametrize("phase", ["idle", "listening", "thinking", "replying", "error", "not_ready"])
async def test_phase_values_round_trip(phase):
    server = await _start_server()
    try:
        reader, writer, _ = await _connect(server)
        await _wait_for_clients(server, 1)
        server.publish("phase", phase=phase)
        msg = await _read_message(reader)
        assert msg["phase"] == phase
        writer.close()
    finally:
        await server.stop()
