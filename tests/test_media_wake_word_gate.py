"""Playback must suppress wake words only while audio is actually playing."""

import ast
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest


@pytest.fixture
def is_media_playing():
    # Load the real method without importing main's audio/UI dependencies or
    # configuring application logging. No microphone or speakers are needed.
    path = Path(__file__).resolve().parents[1] / "src" / "main.py"
    tree = ast.parse(path.read_text(encoding="utf-8"))
    client = next(node for node in tree.body if isinstance(node, ast.ClassDef) and node.name == "HomeAssistantWindows")
    method = next(node for node in client.body if isinstance(node, ast.FunctionDef) and node.name == "_is_media_playing")
    namespace = {}
    exec(compile(ast.Module(body=[method], type_ignores=[]), str(path), "exec"), namespace)
    return namespace[method.name]


@pytest.mark.parametrize(
    "music_playing,sendspin_playing,expected",
    [
        (False, None, False),
        (False, False, False),
        (False, True, True),
        (True, None, True),
        (True, False, True),
    ],
)
def test_media_gate(is_media_playing, music_playing, sendspin_playing, expected):
    receiver = None if sendspin_playing is None else SimpleNamespace(is_playing=Mock(return_value=sendspin_playing))
    client = SimpleNamespace(
        api_server=SimpleNamespace(state=SimpleNamespace(music_player=SimpleNamespace(is_playing=music_playing))),
        sendspin=receiver,
    )

    assert is_media_playing(client) is expected
    if receiver is not None and not music_playing:
        receiver.is_playing.assert_called_once_with()
