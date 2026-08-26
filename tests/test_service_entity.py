"""
Tests for src/notify/service_entity.py

Focus:
- HA service dispatch (notify / run_command / open_url / set_volume / media)
- Regression: media services must forward bare commands (play_pause/next/previous)
  to CommandExecutor.execute - NOT "media:<cmd>" which the whitelist rejects.
"""

from unittest.mock import MagicMock, patch

import pytest

from aioesphomeapi.api_pb2 import ExecuteServiceRequest

from src.notify.service_entity import ServiceEntityManager


def make_arg(string_: str = "", int_: int = 0):
    arg = ExecuteServiceRequest().args.add()
    arg.string_ = string_
    arg.int_ = int_
    return arg


@pytest.fixture
def manager():
    mgr = ServiceEntityManager()
    mgr._command_executor = MagicMock()
    mgr._command_executor.execute.return_value = {"success": True, "message": "ok"}
    return mgr


class TestMediaServiceDispatch:
    """Regression tests for the HA media control services."""

    def test_media_play_pause_forwards_bare_command(self, manager):
        req = ExecuteServiceRequest(key=205)
        manager.handle_message(req)
        manager._command_executor.execute.assert_called_once_with("play_pause")

    def test_media_next_forwards_bare_command(self, manager):
        req = ExecuteServiceRequest(key=206)
        manager.handle_message(req)
        manager._command_executor.execute.assert_called_once_with("next")

    def test_media_previous_forwards_bare_command(self, manager):
        req = ExecuteServiceRequest(key=207)
        manager.handle_message(req)
        manager._command_executor.execute.assert_called_once_with("previous")

    def test_media_command_not_prefixed_with_media(self, manager):
        """The old bug sent "media:play_pause" which the whitelist rejected."""
        req = ExecuteServiceRequest(key=205)
        manager.handle_message(req)
        called_arg = manager._command_executor.execute.call_args[0][0]
        assert not called_arg.startswith("media:")


class TestRunCommandService:
    """run_command has its own SAFE_COMMANDS whitelist and spawns processes."""

    def test_whitelisted_command_is_spawned(self, manager):
        import subprocess

        manager._command_executor = None  # run_command does not use the executor
        req = ExecuteServiceRequest(key=202)
        arg = req.args.add()
        arg.string_ = "notepad"
        with patch.object(subprocess, "Popen") as mock_popen:
            manager.handle_message(req)
            mock_popen.assert_called_once()
            # shell=False always: parts list, never a shell string
            assert isinstance(mock_popen.call_args[0][0], list)
            assert mock_popen.call_args[1].get("shell") is False

    def test_non_whitelisted_command_rejected(self, manager):
        import subprocess

        manager._command_executor = None
        req = ExecuteServiceRequest(key=202)
        arg = req.args.add()
        arg.string_ = "definitely_not_allowed --evil"
        with patch.object(subprocess, "Popen") as mock_popen:
            manager.handle_message(req)
            mock_popen.assert_not_called()

    def test_empty_command_ignored(self, manager):
        manager._command_executor = None
        req = ExecuteServiceRequest(key=202)
        manager.handle_message(req)  # must not raise


class TestOpenUrlAndVolumeServices:
    def test_open_url(self, manager):
        req = ExecuteServiceRequest(key=203)
        arg = req.args.add()
        arg.string_ = "https://www.home-assistant.io"
        manager.handle_message(req)
        manager._command_executor.execute.assert_called_once_with(
            "url:https://www.home-assistant.io"
        )

    def test_set_volume(self, manager):
        req = ExecuteServiceRequest(key=204)
        arg = req.args.add()
        arg.int_ = 42
        manager.handle_message(req)
        manager._command_executor.execute.assert_called_once_with("volume:42")


class TestCommandExecutorWhitelist:
    """The run_command path must respect the CommandExecutor whitelist."""

    def test_unknown_command_rejected(self):
        from src.commands.command_executor import CommandExecutor

        executor = CommandExecutor()
        result = executor.execute("definitely_not_a_real_command")
        assert result["success"] is False

    def test_shell_injection_style_command_rejected(self):
        """First token must be whitelisted; "cmd /c ..." style input fails."""
        from src.commands.command_executor import CommandExecutor

        executor = CommandExecutor()
        result = executor.execute("some_unknown_tool --evil")
        assert result["success"] is False

    def test_whitelisted_command_dispatches_to_handler(self):
        from src.commands.command_executor import CommandExecutor

        executor = CommandExecutor()
        handler = MagicMock(return_value={"success": True, "message": "done"})
        executor._command_handlers["play_pause"] = handler

        result = executor.execute("play_pause")
        assert result["success"] is True
        handler.assert_called_once()

    def test_dangerous_commands_are_in_whitelist(self):
        from src.commands.command_executor import CommandExecutor

        for cmd in CommandExecutor.DANGEROUS_COMMANDS:
            assert cmd in CommandExecutor.ALLOWED_COMMANDS


class TestNotifyService:
    def test_notify_shows_notification(self, manager):
        with patch.object(manager._notification_handler, "show", return_value=True) as mock_show:
            req = ExecuteServiceRequest(key=200)
            a1 = req.args.add()
            a1.string_ = "Hello"
            a2 = req.args.add()
            a2.string_ = "World"

            manager.handle_message(req)

            mock_show.assert_called_once()
            notification = mock_show.call_args[0][0]
            assert notification.title == "Hello"
            assert notification.message == "World"


class TestServiceDefinitions:
    def test_all_services_have_unique_keys(self):
        keys = [s["key"] for s in ServiceEntityManager.SERVICE_DEFINITIONS]
        assert len(keys) == len(set(keys))

    def test_media_services_registered(self):
        names = {s["name"] for s in ServiceEntityManager.SERVICE_DEFINITIONS}
        assert {"media_play_pause", "media_next", "media_previous"} <= names
