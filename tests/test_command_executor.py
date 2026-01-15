"""
Property-Based Tests for Command Execution Functionality

Tests Property 13: Command Whitelist Enforcement
Tests Property 14: Command Result Reporting

Validates: Requirements 6.4, 6.5
"""

import logging
from typing import Dict
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, strategies as st, settings, assume

# Import the command executor module
from src.commands.command_executor import CommandExecutor


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for generating valid whitelisted commands
whitelisted_command_strategy = st.sampled_from(list(CommandExecutor.ALLOWED_COMMANDS))

# Strategy for generating invalid/non-whitelisted commands
# Generate random strings that are NOT in the whitelist
invalid_command_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=('L', 'N'),
        whitelist_characters='_'
    ),
    min_size=1,
    max_size=50
).filter(lambda x: x.strip() and x not in CommandExecutor.ALLOWED_COMMANDS)

# Strategy for generating dangerous commands
dangerous_command_strategy = st.sampled_from(list(CommandExecutor.DANGEROUS_COMMANDS))

# Strategy for generating safe (non-dangerous) whitelisted commands
safe_command_strategy = st.sampled_from(
    list(CommandExecutor.ALLOWED_COMMANDS - CommandExecutor.DANGEROUS_COMMANDS)
)

# Strategy for generating command arguments
command_arg_strategy = st.one_of(
    st.none(),
    st.text(
        alphabet=st.characters(
            whitelist_categories=('L', 'N', 'P'),
            whitelist_characters=' _-./\\'
        ),
        min_size=1,
        max_size=100
    ).filter(lambda x: x.strip() and ':' not in x)
)


# =============================================================================
# Property 13: Command Whitelist Enforcement
# For any dangerous command (shutdown, restart), the Windows_Client SHALL only
# execute if the command is in the whitelist.
# Validates: Requirements 6.4
# =============================================================================

class TestCommandWhitelistEnforcement:
    """
    Property 13: Command Whitelist Enforcement
    
    **Feature: ha-windows-client, Property 13: Command Whitelist Enforcement**
    **Validates: Requirements 6.4**
    """

    @given(command=invalid_command_strategy)
    @settings(max_examples=100, deadline=None)
    def test_non_whitelisted_commands_are_rejected(self, command: str):
        """
        Property 13: For any command NOT in the whitelist, the executor SHALL
        reject the command and return success=False.
        
        **Feature: ha-windows-client, Property 13: Command Whitelist Enforcement**
        **Validates: Requirements 6.4**
        """
        executor = CommandExecutor()
        
        # Execute the non-whitelisted command
        result = executor.execute(command)
        
        # Property: non-whitelisted commands are rejected
        assert result['success'] is False, \
            f"Non-whitelisted command '{command}' should be rejected"
        assert 'error' in result or 'message' in result, \
            "Rejected command should include error or message"

    @given(command=whitelisted_command_strategy)
    @settings(max_examples=100, deadline=None)
    def test_whitelisted_commands_are_allowed(self, command: str):
        """
        Property 13: For any command in the whitelist, the executor SHALL
        allow the command (not reject based on whitelist).
        
        **Feature: ha-windows-client, Property 13: Command Whitelist Enforcement**
        **Validates: Requirements 6.4**
        """
        executor = CommandExecutor()
        
        # Mock the actual command handlers to avoid side effects
        # We only want to test that the whitelist check passes
        mock_handler = MagicMock(return_value={'success': True, 'message': 'OK'})
        executor._command_handlers[command] = mock_handler
        
        # Execute the whitelisted command
        result = executor.execute(command)
        
        # Property: whitelisted commands pass the whitelist check
        # (they may fail for other reasons, but not due to whitelist)
        if not result['success']:
            # If it failed, it should NOT be because of whitelist rejection
            error_msg = result.get('error', '')
            assert '白名单' not in error_msg and 'whitelist' not in error_msg.lower(), \
                f"Whitelisted command '{command}' should not be rejected by whitelist"

    @given(command=dangerous_command_strategy)
    @settings(max_examples=100, deadline=None)
    def test_dangerous_commands_are_in_whitelist(self, command: str):
        """
        Property 13: All dangerous commands SHALL be in the whitelist
        (they require confirmation but are allowed).
        
        **Feature: ha-windows-client, Property 13: Command Whitelist Enforcement**
        **Validates: Requirements 6.4**
        """
        executor = CommandExecutor()
        
        # Property: dangerous commands are subset of allowed commands
        assert command in executor.ALLOWED_COMMANDS, \
            f"Dangerous command '{command}' should be in ALLOWED_COMMANDS"
        
        # Property: dangerous commands are recognized as dangerous
        assert command in executor.DANGEROUS_COMMANDS, \
            f"Command '{command}' should be in DANGEROUS_COMMANDS"

    def test_whitelist_is_non_empty(self):
        """
        Property 13: The command whitelist SHALL contain at least one command.
        
        **Feature: ha-windows-client, Property 13: Command Whitelist Enforcement**
        **Validates: Requirements 6.4**
        """
        executor = CommandExecutor()
        
        assert len(executor.ALLOWED_COMMANDS) > 0, \
            "ALLOWED_COMMANDS whitelist should not be empty"

    def test_dangerous_commands_subset_of_allowed(self):
        """
        Property 13: DANGEROUS_COMMANDS SHALL be a subset of ALLOWED_COMMANDS.
        
        **Feature: ha-windows-client, Property 13: Command Whitelist Enforcement**
        **Validates: Requirements 6.4**
        """
        executor = CommandExecutor()
        
        assert executor.DANGEROUS_COMMANDS.issubset(executor.ALLOWED_COMMANDS), \
            "DANGEROUS_COMMANDS should be a subset of ALLOWED_COMMANDS"


# =============================================================================
# Property 14: Command Result Reporting
# For any command execution, the Windows_Client SHALL report success or
# failure status.
# Validates: Requirements 6.5
# =============================================================================

class TestCommandResultReporting:
    """
    Property 14: Command Result Reporting
    
    **Feature: ha-windows-client, Property 14: Command Result Reporting**
    **Validates: Requirements 6.5**
    """

    @given(command=whitelisted_command_strategy)
    @settings(max_examples=100, deadline=None)
    def test_result_contains_success_field(self, command: str):
        """
        Property 14: For any command execution, the result SHALL contain
        a 'success' field with a boolean value.
        
        **Feature: ha-windows-client, Property 14: Command Result Reporting**
        **Validates: Requirements 6.5**
        """
        executor = CommandExecutor()
        
        # Mock the handler to avoid actual execution
        mock_handler = MagicMock(return_value={'success': True, 'message': 'OK'})
        executor._command_handlers[command] = mock_handler
        
        result = executor.execute(command)
        
        # Property: result contains 'success' field
        assert 'success' in result, \
            f"Result for command '{command}' should contain 'success' field"
        assert isinstance(result['success'], bool), \
            f"'success' field should be boolean, got {type(result['success'])}"

    @given(command=invalid_command_strategy)
    @settings(max_examples=100, deadline=None)
    def test_rejected_command_reports_failure(self, command: str):
        """
        Property 14: For any rejected command, the result SHALL report
        success=False.
        
        **Feature: ha-windows-client, Property 14: Command Result Reporting**
        **Validates: Requirements 6.5**
        """
        executor = CommandExecutor()
        
        result = executor.execute(command)
        
        # Property: rejected commands report failure
        assert 'success' in result, \
            "Result should contain 'success' field"
        assert result['success'] is False, \
            f"Rejected command '{command}' should report success=False"

    @given(command=whitelisted_command_strategy)
    @settings(max_examples=100, deadline=None)
    def test_result_contains_message_field(self, command: str):
        """
        Property 14: For any command execution, the result SHALL contain
        a 'message' field.
        
        **Feature: ha-windows-client, Property 14: Command Result Reporting**
        **Validates: Requirements 6.5**
        """
        executor = CommandExecutor()
        
        # Mock the handler to return a proper result
        mock_handler = MagicMock(return_value={
            'success': True,
            'message': 'Command executed'
        })
        executor._command_handlers[command] = mock_handler
        
        result = executor.execute(command)
        
        # Property: result contains 'message' field
        assert 'message' in result, \
            f"Result for command '{command}' should contain 'message' field"

    @given(command=safe_command_strategy)
    @settings(max_examples=100, deadline=None)
    def test_successful_command_reports_success(self, command: str):
        """
        Property 14: For any successfully executed command, the result SHALL
        report success=True.
        
        **Feature: ha-windows-client, Property 14: Command Result Reporting**
        **Validates: Requirements 6.5**
        """
        executor = CommandExecutor()
        
        # Mock the handler to simulate successful execution
        mock_handler = MagicMock(return_value={
            'success': True,
            'message': 'Command executed successfully'
        })
        executor._command_handlers[command] = mock_handler
        
        result = executor.execute(command)
        
        # Property: successful execution reports success=True
        assert result['success'] is True, \
            f"Successfully executed command '{command}' should report success=True"

    @given(command=safe_command_strategy)
    @settings(max_examples=100, deadline=None)
    def test_failed_command_reports_failure_with_error(self, command: str):
        """
        Property 14: For any failed command execution, the result SHALL
        report success=False and include error information.
        
        **Feature: ha-windows-client, Property 14: Command Result Reporting**
        **Validates: Requirements 6.5**
        """
        executor = CommandExecutor()
        
        # Mock the handler to simulate failed execution
        mock_handler = MagicMock(return_value={
            'success': False,
            'message': 'Command failed',
            'error': 'Simulated error'
        })
        executor._command_handlers[command] = mock_handler
        
        result = executor.execute(command)
        
        # Property: failed execution reports success=False
        assert result['success'] is False, \
            f"Failed command '{command}' should report success=False"

    @given(command=safe_command_strategy)
    @settings(max_examples=100, deadline=None)
    def test_exception_in_handler_reports_failure(self, command: str):
        """
        Property 14: When a command handler raises an exception, the result
        SHALL report success=False and include error information.
        
        **Feature: ha-windows-client, Property 14: Command Result Reporting**
        **Validates: Requirements 6.5**
        """
        executor = CommandExecutor()
        
        # Mock the handler to raise an exception
        mock_handler = MagicMock(side_effect=Exception("Test exception"))
        executor._command_handlers[command] = mock_handler
        
        result = executor.execute(command)
        
        # Property: exception results in failure report
        assert result['success'] is False, \
            f"Command '{command}' that raised exception should report success=False"
        assert 'error' in result or 'message' in result, \
            "Failed command should include error information"

    def test_result_is_dict(self):
        """
        Property 14: Command execution result SHALL always be a dictionary.
        
        **Feature: ha-windows-client, Property 14: Command Result Reporting**
        **Validates: Requirements 6.5**
        """
        executor = CommandExecutor()
        
        # Test with valid command
        result = executor.execute("volume:50")
        assert isinstance(result, dict), \
            "Result should be a dictionary"
        
        # Test with invalid command
        result = executor.execute("invalid_command_xyz")
        assert isinstance(result, dict), \
            "Result for invalid command should also be a dictionary"


# =============================================================================
# Additional edge case tests
# =============================================================================

class TestCommandExecutorEdgeCases:
    """Edge case tests for command executor functionality"""

    def test_command_with_arguments(self):
        """
        Commands with arguments SHALL be parsed correctly.
        """
        executor = CommandExecutor()
        
        # Mock the volume handler
        mock_handler = MagicMock(return_value={'success': True, 'message': 'OK'})
        executor._command_handlers['volume'] = mock_handler
        
        result = executor.execute("volume:75")
        
        # Handler should be called with the argument
        mock_handler.assert_called_once_with("75")

    def test_command_without_arguments(self):
        """
        Commands without arguments SHALL be executed correctly.
        """
        executor = CommandExecutor()
        
        # Mock the play_pause handler
        mock_handler = MagicMock(return_value={'success': True, 'message': 'OK'})
        executor._command_handlers['play_pause'] = mock_handler
        
        result = executor.execute("play_pause")
        
        # Handler should be called without arguments
        mock_handler.assert_called_once_with()

    def test_list_available_commands(self):
        """
        list_available_commands() SHALL return all whitelisted commands.
        """
        executor = CommandExecutor()
        
        commands = executor.list_available_commands()
        
        assert isinstance(commands, list), \
            "list_available_commands should return a list"
        assert set(commands) == executor.ALLOWED_COMMANDS, \
            "list_available_commands should return all ALLOWED_COMMANDS"

    def test_empty_command_string(self):
        """
        Empty command string SHALL be rejected.
        """
        executor = CommandExecutor()
        
        result = executor.execute("")
        
        assert result['success'] is False, \
            "Empty command should be rejected"

    def test_whitespace_only_command(self):
        """
        Whitespace-only command SHALL be rejected.
        """
        executor = CommandExecutor()
        
        result = executor.execute("   ")
        
        assert result['success'] is False, \
            "Whitespace-only command should be rejected"
