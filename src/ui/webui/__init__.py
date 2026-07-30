"""
WebUI Module
Web-based settings, status, and about dialogs using aiohttp + webview
"""

from .server import WebUIServer, get_webui_server

__all__ = ["WebUIServer", "get_webui_server"]