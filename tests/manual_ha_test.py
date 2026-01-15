"""
Manual Testing Script for Home Assistant Integration

Task 16.2: 在真实 Home Assistant 环境中测试
- 连接真实 HA 实例
- 验证所有功能正常工作

This script helps verify the Windows client works with a real Home Assistant instance.
Run this script and follow the prompts to test each feature.

Usage:
    python tests/manual_ha_test.py [--port PORT] [--name NAME]

Prerequisites:
    1. Home Assistant instance running on the same network
    2. ESPHome integration installed in Home Assistant
    3. All dependencies installed (pip install -r requirements.txt)
"""

import argparse
import asyncio
import logging
import sys
import time
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.esphome_protocol import ESPHomeServer, create_default_state
from src.core.mdns_discovery import MDNSBroadcaster, DeviceInfo
from src.core.models import AudioPlayer

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ManualTestRunner:
    """Manual test runner for Home Assistant integration."""
    
    def __init__(self, device_name: str, port: int):
        self.device_name = device_name
        self.port = port
        self.server: ESPHomeServer = None
        self.broadcaster: MDNSBroadcaster = None
        self.connected = False
        
    async def setup(self):
        """Set up the ESPHome server and mDNS broadcaster."""
        print("\n" + "=" * 60)
        print("Home Assistant Windows Client - Manual Test")
        print("=" * 60)
        
        # Create server
        print(f"\n[1/3] Starting ESPHome API server on port {self.port}...")
        self.server = ESPHomeServer(
            host="0.0.0.0",
            port=self.port,
            device_name=self.device_name,
        )
        success = await self.server.start()
        if not success:
            print("❌ Failed to start server")
            return False
        print("✅ Server started")
        
        # Create mDNS broadcaster
        print(f"\n[2/3] Registering mDNS service...")
        device_info = DeviceInfo(name=self.device_name)
        self.broadcaster = MDNSBroadcaster(device_info)
        success = await self.broadcaster.register_service(self.port)
        if not success:
            print("❌ Failed to register mDNS service")
            return False
        print("✅ mDNS service registered")
        
        print(f"\n[3/3] Ready for Home Assistant connection")
        print(f"   Device name: {self.device_name}")
        print(f"   Port: {self.port}")
        
        return True
    
    async def wait_for_connection(self, timeout: int = 60):
        """Wait for Home Assistant to connect."""
        print(f"\n⏳ Waiting for Home Assistant to connect (timeout: {timeout}s)...")
        print("   In Home Assistant:")
        print("   1. Go to Settings > Devices & Services")
        print("   2. Click 'Add Integration'")
        print("   3. Search for 'ESPHome'")
        print(f"   4. The device '{self.device_name}' should be discovered")
        print("")
        
        start_time = time.time()
        while time.time() - start_time < timeout:
            if self.server.protocol and self.server.protocol._transport:
                self.connected = True
                print("✅ Home Assistant connected!")
                return True
            await asyncio.sleep(1)
        
        print("❌ Connection timeout")
        return False
    
    async def run_tests(self):
        """Run manual tests with user interaction."""
        if not self.connected:
            print("❌ Not connected to Home Assistant")
            return
        
        print("\n" + "=" * 60)
        print("Manual Test Checklist")
        print("=" * 60)
        
        tests = [
            ("Device Discovery", "Verify the device appears in Home Assistant ESPHome integration"),
            ("Sensor Entities", "Check that CPU, Memory, Disk, Network sensors appear in HA"),
            ("MediaPlayer Entity", "Verify MediaPlayer entity is visible in HA"),
            ("Voice Assistant", "Test voice commands (if wake word detection is set up)"),
            ("Announcements", "Send a TTS announcement from HA to the Windows client"),
            ("Volume Control", "Adjust volume from HA MediaPlayer controls"),
            ("Connection Stability", "Verify connection remains stable over time"),
        ]
        
        print("\nPlease verify each test manually in Home Assistant:\n")
        
        for i, (test_name, description) in enumerate(tests, 1):
            print(f"  [{i}] {test_name}")
            print(f"      {description}")
            print("")
        
        print("Press Ctrl+C when done testing to stop the server.")
        
        # Keep running until interrupted
        try:
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            print("\n\nStopping test server...")
    
    async def cleanup(self):
        """Clean up resources."""
        if self.broadcaster:
            await self.broadcaster.unregister_service()
        if self.server:
            await self.server.stop()
        print("✅ Cleanup complete")


async def main():
    parser = argparse.ArgumentParser(
        description="Manual testing script for Home Assistant integration"
    )
    parser.add_argument(
        '--name',
        default='HA_Windows_Test',
        help='Device name (default: HA_Windows_Test)'
    )
    parser.add_argument(
        '--port',
        type=int,
        default=6053,
        help='API port (default: 6053)'
    )
    args = parser.parse_args()
    
    runner = ManualTestRunner(args.name, args.port)
    
    try:
        if not await runner.setup():
            return 1
        
        if await runner.wait_for_connection(timeout=120):
            await runner.run_tests()
        
    except KeyboardInterrupt:
        print("\n\nInterrupted by user")
    finally:
        await runner.cleanup()
    
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
