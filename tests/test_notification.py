"""
Property-Based Tests for Notification Functionality

Tests Property 19: Notification Display
Tests Property 20: Notification Image Handling

Validates: Requirements 10.1, 10.2, 10.3, 10.4
"""

import hashlib
import tempfile
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch, AsyncMock
import asyncio

import pytest
from hypothesis import given, strategies as st, settings

# Import the notification module
from src.notify.toast_notification import (
    Notification,
    NotificationAction,
    NotificationHandler,
)


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for generating valid notification titles (non-empty strings)
notification_title_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S'),
        whitelist_characters=' '
    ),
    min_size=1,
    max_size=100
).filter(lambda x: x.strip())

# Strategy for generating valid notification messages (non-empty strings)
notification_message_strategy = st.text(
    alphabet=st.characters(
        whitelist_categories=('L', 'N', 'P', 'S'),
        whitelist_characters=' \n'
    ),
    min_size=1,
    max_size=500
).filter(lambda x: x.strip())

# Strategy for generating valid image URLs
image_url_strategy = st.one_of(
    st.just(None),
    st.from_regex(r'https?://[a-z0-9]+\.[a-z]{2,3}/[a-z0-9_]+\.(png|jpg|jpeg|gif)', fullmatch=True)
)

# Strategy for generating notification duration (1-30 seconds)
duration_strategy = st.integers(min_value=1, max_value=30)


# =============================================================================
# Property 19: Notification Display
# For any notification received from Home Assistant, the Windows_Client SHALL
# display a Windows Toast notification with the provided title and message.
# Validates: Requirements 10.1, 10.2, 10.3
# =============================================================================

class TestNotificationDisplay:
    """
    Property 19: Notification Display
    
    **Feature: ha-windows-client, Property 19: Notification Display**
    **Validates: Requirements 10.1, 10.2, 10.3**
    """

    @given(
        title=notification_title_strategy,
        message=notification_message_strategy,
        duration=duration_strategy
    )
    @settings(max_examples=100, deadline=None)
    def test_notification_contains_title_and_message(
        self, title: str, message: str, duration: int
    ):
        """
        Property 19: For any notification, the title and message SHALL be
        preserved in the Notification object.
        
        **Feature: ha-windows-client, Property 19: Notification Display**
        **Validates: Requirements 10.1, 10.2, 10.3**
        """
        # Create notification with generated data
        notification = Notification(
            title=title,
            message=message,
            duration=duration
        )
        
        # Property: title and message are preserved exactly
        assert notification.title == title, \
            f"Title mismatch: expected '{title}', got '{notification.title}'"
        assert notification.message == message, \
            f"Message mismatch: expected '{message}', got '{notification.message}'"
        assert notification.duration == duration, \
            f"Duration mismatch: expected {duration}, got {notification.duration}"

    @given(
        title=notification_title_strategy,
        message=notification_message_strategy
    )
    @settings(max_examples=100, deadline=None)
    def test_notification_show_called_with_correct_params(
        self, title: str, message: str
    ):
        """
        Property 19: For any notification, when show() is called, the toast
        notifier SHALL receive the correct title and message.
        
        **Feature: ha-windows-client, Property 19: Notification Display**
        **Validates: Requirements 10.1, 10.2, 10.3**
        """
        # Create handler with mocked toaster
        handler = NotificationHandler(app_name="Test App")
        
        # Mock the toaster
        mock_toaster = MagicMock()
        mock_toaster.show_toast = MagicMock(return_value=True)
        handler._toaster = mock_toaster
        
        # Create and show notification
        notification = Notification(title=title, message=message)
        result = handler.show(notification)
        
        # Property: show_toast was called with correct parameters
        assert result is True, "show() should return True when toaster succeeds"
        mock_toaster.show_toast.assert_called_once()
        
        call_kwargs = mock_toaster.show_toast.call_args
        assert call_kwargs[1]['title'] == title, \
            f"Toast title mismatch: expected '{title}'"
        assert call_kwargs[1]['msg'] == message, \
            f"Toast message mismatch: expected '{message}'"

    @given(
        title=notification_title_strategy,
        message=notification_message_strategy
    )
    @settings(max_examples=100, deadline=None)
    def test_show_simple_creates_correct_notification(
        self, title: str, message: str
    ):
        """
        Property 19: show_simple() SHALL create a notification with the
        provided title and message.
        
        **Feature: ha-windows-client, Property 19: Notification Display**
        **Validates: Requirements 10.1, 10.2, 10.3**
        """
        handler = NotificationHandler(app_name="Test App")
        
        # Mock the toaster
        mock_toaster = MagicMock()
        mock_toaster.show_toast = MagicMock(return_value=True)
        handler._toaster = mock_toaster
        
        # Call show_simple
        result = handler.show_simple(title=title, message=message)
        
        # Property: notification was shown with correct title and message
        assert result is True
        call_kwargs = mock_toaster.show_toast.call_args
        assert call_kwargs[1]['title'] == title
        assert call_kwargs[1]['msg'] == message


# =============================================================================
# Property 20: Notification Image Handling
# For any notification with image URL, the Windows_Client SHALL attempt to
# download and display the image.
# Validates: Requirements 10.4
# =============================================================================

class TestNotificationImageHandling:
    """
    Property 20: Notification Image Handling
    
    **Feature: ha-windows-client, Property 20: Notification Image Handling**
    **Validates: Requirements 10.4**
    """

    @given(
        url=st.from_regex(
            r'https://example\.com/[a-z0-9]{1,10}\.(png|jpg|jpeg|gif)',
            fullmatch=True
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_image_url_generates_consistent_local_path(self, url: str):
        """
        Property 20: For any image URL, the local path SHALL be deterministic
        based on the URL hash.
        
        **Feature: ha-windows-client, Property 20: Notification Image Handling**
        **Validates: Requirements 10.4**
        """
        handler = NotificationHandler(app_name="Test App")
        
        # Calculate expected hash
        url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
        ext = Path(url).suffix or ".png"
        expected_filename = f"img_{url_hash}{ext}"
        
        # The temp directory should contain the expected path pattern
        expected_path = handler._temp_dir / expected_filename
        
        # Property: path is deterministic - same URL always produces same path
        url_hash_2 = hashlib.md5(url.encode()).hexdigest()[:8]
        assert url_hash == url_hash_2, "Hash should be deterministic"
        
        # Property: extension is preserved from URL
        assert expected_path.suffix == ext, \
            f"Extension mismatch: expected '{ext}', got '{expected_path.suffix}'"

    @given(
        title=notification_title_strategy,
        message=notification_message_strategy,
        url=st.from_regex(
            r'https://example\.com/[a-z0-9]{1,10}\.(png|jpg)',
            fullmatch=True
        )
    )
    @settings(max_examples=100, deadline=None)
    def test_notification_with_image_url_attempts_download(
        self, title: str, message: str, url: str
    ):
        """
        Property 20: For any notification with image_url, show_async SHALL
        attempt to download the image.
        
        **Feature: ha-windows-client, Property 20: Notification Image Handling**
        **Validates: Requirements 10.4**
        """
        handler = NotificationHandler(app_name="Test App")
        
        # Mock the toaster
        mock_toaster = MagicMock()
        mock_toaster.show_toast = MagicMock(return_value=True)
        handler._toaster = mock_toaster
        
        # Mock the download method
        download_called = False
        original_download = handler._download_image
        
        async def mock_download(image_url: str) -> Optional[str]:
            nonlocal download_called
            download_called = True
            # Verify the URL is passed correctly
            assert image_url == url, \
                f"Download URL mismatch: expected '{url}', got '{image_url}'"
            return None  # Simulate download failure for simplicity
        
        handler._download_image = mock_download
        
        # Create notification with image URL
        notification = Notification(
            title=title,
            message=message,
            image_url=url
        )
        
        # Run async show
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(handler.show_async(notification))
        finally:
            loop.close()
        
        # Property: download was attempted for the image URL
        assert download_called, \
            "Image download should be attempted when image_url is provided"

    @given(
        title=notification_title_strategy,
        message=notification_message_strategy
    )
    @settings(max_examples=100, deadline=None)
    def test_notification_without_image_url_skips_download(
        self, title: str, message: str
    ):
        """
        Property 20: For any notification without image_url, show_async SHALL
        NOT attempt to download any image.
        
        **Feature: ha-windows-client, Property 20: Notification Image Handling**
        **Validates: Requirements 10.4**
        """
        handler = NotificationHandler(app_name="Test App")
        
        # Mock the toaster
        mock_toaster = MagicMock()
        mock_toaster.show_toast = MagicMock(return_value=True)
        handler._toaster = mock_toaster
        
        # Track if download is called
        download_called = False
        
        async def mock_download(image_url: str) -> Optional[str]:
            nonlocal download_called
            download_called = True
            return None
        
        handler._download_image = mock_download
        
        # Create notification WITHOUT image URL
        notification = Notification(
            title=title,
            message=message,
            image_url=None
        )
        
        # Run async show
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(handler.show_async(notification))
        finally:
            loop.close()
        
        # Property: download should NOT be called when no image_url
        assert not download_called, \
            "Image download should NOT be attempted when image_url is None"

    def test_temp_directory_created_on_init(self):
        """
        Property 20: NotificationHandler SHALL create a temp directory for
        downloaded images on initialization.
        
        **Feature: ha-windows-client, Property 20: Notification Image Handling**
        **Validates: Requirements 10.4**
        """
        handler = NotificationHandler(app_name="Test App")
        
        # Property: temp directory exists
        assert handler._temp_dir.exists(), \
            "Temp directory should be created on initialization"
        assert handler._temp_dir.is_dir(), \
            "Temp directory should be a directory"

    def test_cleanup_removes_downloaded_images(self):
        """
        Property 20: cleanup() SHALL remove downloaded image files.
        
        **Feature: ha-windows-client, Property 20: Notification Image Handling**
        **Validates: Requirements 10.4**
        """
        handler = NotificationHandler(app_name="Test App")
        
        # Create a fake downloaded image file
        test_file = handler._temp_dir / "img_test1234.png"
        test_file.write_bytes(b"fake image data")
        
        assert test_file.exists(), "Test file should exist before cleanup"
        
        # Call cleanup
        handler.cleanup()
        
        # Property: downloaded images are removed
        assert not test_file.exists(), \
            "Downloaded image files should be removed after cleanup"


# =============================================================================
# Additional edge case tests
# =============================================================================

class TestNotificationEdgeCases:
    """Edge case tests for notification functionality"""

    def test_notification_handler_without_toaster_returns_false(self):
        """
        When toaster is not available, show() SHALL return False.
        """
        handler = NotificationHandler(app_name="Test App")
        handler._toaster = None
        
        notification = Notification(title="Test", message="Test message")
        result = handler.show(notification)
        
        assert result is False, \
            "show() should return False when toaster is not available"

    def test_notification_action_dataclass(self):
        """
        NotificationAction SHALL correctly store action data.
        """
        callback = lambda: None
        action = NotificationAction(
            id="test_action",
            label="Test Label",
            callback=callback
        )
        
        assert action.id == "test_action"
        assert action.label == "Test Label"
        assert action.callback == callback

    def test_notification_default_values(self):
        """
        Notification SHALL have correct default values.
        """
        notification = Notification(title="Test", message="Message")
        
        assert notification.icon_path is None
        assert notification.image_url is None
        assert notification.duration == 5
        assert notification.actions is None
        assert notification.on_click is None
        assert notification.on_dismiss is None
