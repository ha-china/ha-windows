"""
WebUI Server
Starts a local aiohttp server and opens pages in the default browser
"""

import json
import logging
import threading
import webbrowser
from typing import Optional

logger = logging.getLogger(__name__)

STATUS_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Device Status</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #1a1a2e; color: #e0e0e0; display: flex; justify-content: center;
  align-items: center; min-height: 100vh; margin: 0;
}
.container { background: #16213e; border-radius: 16px; padding: 40px; width: 420px; box-shadow: 0 8px 32px rgba(0,0,0,0.3); }
h1 { font-size: 22px; margin-bottom: 28px; text-align: center; color: #fff; }
.info-row { display: flex; justify-content: space-between; padding: 14px 0; border-bottom: 1px solid #2a2a4a; }
.info-row:last-child { border-bottom: none; }
.label { color: #888; }
.value { color: #4fc3f7; font-weight: 500; }
.status-badge { display: inline-block; padding: 4px 14px; border-radius: 20px; font-size: 13px; background: #1b5e20; color: #81c784; }
</style>
</head>
<body>
<div class="container">
<h1>Device Status</h1>
<div class="info-row"><span class="label">Device</span><span class="value" id="device-name">--</span></div>
<div class="info-row"><span class="label">IP</span><span class="value" id="device-ip">--</span></div>
<div class="info-row"><span class="label">Port</span><span class="value" id="device-port">--</span></div>
<div class="info-row"><span class="label">Status</span><span class="status-badge" id="device-status">Running</span></div>
</div>
<script>
fetch('/api/status').then(r=>r.json()).then(d=>{
  document.getElementById('device-name').textContent = d.name;
  document.getElementById('device-ip').textContent = d.ip;
  document.getElementById('device-port').textContent = d.port;
});
</script>
</body>
</html>"""

ABOUT_HTML = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>About</title>
<style>
* { margin: 0; padding: 0; box-sizing: border-box; }
body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  background: #1a1a2e; color: #e0e0e0; display: flex; justify-content: center;
  align-items: center; min-height: 100vh; margin: 0;
}
.container { background: #16213e; border-radius: 16px; padding: 40px; width: 420px; text-align: center; box-shadow: 0 8px 32px rgba(0,0,0,0.3); }
.logo { font-size: 48px; margin-bottom: 12px; }
h1 { font-size: 22px; color: #fff; margin-bottom: 8px; }
.version { color: #4fc3f7; margin-bottom: 24px; }
.desc { color: #888; font-size: 14px; line-height: 1.6; margin-bottom: 24px; }
.repo { color: #4fc3f7; text-decoration: none; font-size: 14px; }
.repo:hover { text-decoration: underline; }
.copyright { color: #555; font-size: 12px; margin-top: 24px; }
</style>
</head>
<body>
<div class="container">
<div class="logo">🏠</div>
<h1>Home Assistant Windows</h1>
<div class="version" id="version">v--</div>
<p class="desc">Windows native client that emulates an ESPHome device for seamless Home Assistant integration.</p>
<a class="repo" href="https://github.com/ha-china/ha-windows" target="_blank">github.com/ha-china/ha-windows</a>
<div class="copyright">&copy; 2024 ha-china</div>
</div>
<script>
fetch('/api/version').then(r=>r.json()).then(d=>{ document.getElementById('version').textContent = 'v' + d.version; });
</script>
</body>
</html>"""


class WebUIServer:
    """WebUI server for settings, status, and about dialogs"""

    def __init__(self):
        self._app = None
        self._runner = None
        self._site = None
        self._port = 0
        self._thread: Optional[threading.Thread] = None
        self._status_info = {
            'name': 'Unknown',
            'ip': 'Unknown',
            'port': 'Unknown',
        }
        self._version = "0.0.0"

    def set_status_info(self, name: str, ip: str, port: str) -> None:
        """Set device status info"""
        self._status_info = {'name': name, 'ip': ip, 'port': port}

    def set_version(self, version: str) -> None:
        """Set app version"""
        self._version = version

    async def _start_server(self) -> int:
        """Start aiohttp server on a random port"""
        from aiohttp import web

        app = web.Application()

        async def handle_status(request):
            return web.json_response(self._status_info)

        async def handle_version(request):
            return web.json_response({'version': self._version})

        async def handle_status_page(request):
            return web.Response(text=STATUS_HTML, content_type='text/html; charset=utf-8')

        async def handle_about_page(request):
            return web.Response(text=ABOUT_HTML, content_type='text/html; charset=utf-8')

        app.router.add_get('/api/status', handle_status)
        app.router.add_get('/api/version', handle_version)
        app.router.add_get('/status', handle_status_page)
        app.router.add_get('/about', handle_about_page)

        self._app = app
        self._runner = web.AppRunner(app)
        await self._runner.setup()
        self._site = web.TCPSite(self._runner, '127.0.0.1', 0)
        await self._site.start()

        for sock in self._site._server.sockets:
            self._port = sock.getsockname()[1]
            break

        logger.info(f"WebUI server started on 127.0.0.1:{self._port}")
        return self._port

    def _run_server(self) -> None:
        """Run the server in the current thread"""
        import asyncio
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(self._start_server())
        loop.run_forever()

    def start(self) -> int:
        """Start the web server in background thread"""
        if self._thread and self._thread.is_alive():
            return self._port
        self._thread = threading.Thread(target=self._run_server, daemon=True)
        self._thread.start()
        import time
        time.sleep(0.5)
        return self._port

    def stop(self) -> None:
        """Stop the server"""
        if self._runner:
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                loop.run_until_complete(self._runner.cleanup())
            except Exception:
                pass

    @property
    def port(self) -> int:
        return self._port

    def open_status(self) -> None:
        """Open status page in default browser"""
        webbrowser.open(f'http://127.0.0.1:{self._port}/status')

    def open_about(self) -> None:
        """Open about page in default browser"""
        webbrowser.open(f'http://127.0.0.1:{self._port}/about')


_server_instance: Optional[WebUIServer] = None


def get_webui_server() -> WebUIServer:
    """Get WebUI server singleton"""
    global _server_instance
    if _server_instance is None:
        _server_instance = WebUIServer()
    return _server_instance