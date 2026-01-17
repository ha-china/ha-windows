"""
Update Checker Module
Check for new versions from GitHub releases
"""

import logging
import json
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

LATEST_VERSION_URL = "https://github.com/ha-china/ha-windows/releases/latest/download/latest.json"
RELEASES_URL = "https://github.com/ha-china/ha-windows/releases"
LATEST_EXE_URL = "https://github.com/ha-china/ha-windows/releases/latest/download/HomeAssistantWindows.exe"


def get_current_version() -> str:
    """Get current version"""
    try:
        from src import __version__
        return __version__
    except ImportError:
        return "0.0.0"


def check_for_updates(timeout: int = 5) -> Optional[Tuple[bool, str, str]]:
    """
    Check for updates

    Args:
        timeout: Request timeout in seconds

    Returns:
        Tuple of (has_update, current_version, latest_version) or None if check failed
    """
    try:
        import urllib.request
        import ssl

        current_version = get_current_version()
        logger.info(f"Current version: {current_version}")

        # Create SSL context that doesn't verify (for compatibility)
        ssl_context = ssl.create_default_context()
        ssl_context.check_hostname = False
        ssl_context.verify_mode = ssl.CERT_NONE

        # Fetch latest version info
        request = urllib.request.Request(
            LATEST_VERSION_URL,
            headers={'User-Agent': 'HomeAssistantWindows/1.0'}
        )

        with urllib.request.urlopen(request, timeout=timeout, context=ssl_context) as response:
            data = json.loads(response.read().decode('utf-8'))
            latest_version = data.get('version', '0.0.0')

        logger.info(f"Latest version: {latest_version}")

        # Compare versions
        has_update = _compare_versions(current_version, latest_version)

        return (has_update, current_version, latest_version)

    except Exception as e:
        logger.warning(f"Failed to check for updates: {e}")
        return None


def _compare_versions(current: str, latest: str) -> bool:
    """
    Compare version strings

    Args:
        current: Current version (e.g., "0.1.0")
        latest: Latest version (e.g., "0.2.0")

    Returns:
        True if latest > current
    """
    try:
        # Parse version strings
        current_parts = [int(x) for x in current.split('.')]
        latest_parts = [int(x) for x in latest.split('.')]

        # Pad to same length
        max_len = max(len(current_parts), len(latest_parts))
        current_parts += [0] * (max_len - len(current_parts))
        latest_parts += [0] * (max_len - len(latest_parts))

        # Compare
        return latest_parts > current_parts

    except Exception as e:
        logger.error(f"Failed to compare versions: {e}")
        return False


def show_update_notification(current_version: str, latest_version: str) -> None:
    """
    Show update notification using Windows toast

    Args:
        current_version: Current version
        latest_version: Latest version
    """
    try:
        from windows_toasts import Toast, InteractableWindowsToaster, ToastButton
        import webbrowser

        toaster = InteractableWindowsToaster('Home Assistant Windows')

        # Create toast
        toast = Toast()
        toast.text_fields = [
            f'New Version Available: v{latest_version}',
            f'Current version: v{current_version}'
        ]

        # Add download button
        toast.AddAction(ToastButton('Download', arguments='download'))

        # Set click action to open download link
        def on_activated(args):
            webbrowser.open(LATEST_EXE_URL)

        toast.on_activated = on_activated

        # Show toast
        toaster.show_toast(toast)
        logger.info(f"Update notification shown: {current_version} -> {latest_version}")

    except Exception as e:
        logger.error(f"Failed to show update notification: {e}")


async def check_for_updates_async(timeout: int = 5) -> Optional[Tuple[bool, str, str]]:
    """
    Check for updates asynchronously

    Args:
        timeout: Request timeout in seconds

    Returns:
        Tuple of (has_update, current_version, latest_version) or None if check failed
    """
    import asyncio
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, check_for_updates, timeout)


if __name__ == "__main__":
    # Test
    logging.basicConfig(level=logging.INFO)

    result = check_for_updates()
    if result:
        has_update, current, latest = result
        print(f"Current: {current}")
        print(f"Latest: {latest}")
        print(f"Update available: {has_update}")

        if has_update:
            show_update_notification(current, latest)
    else:
        print("Failed to check for updates")
