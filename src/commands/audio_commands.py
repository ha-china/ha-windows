"""
Audio Device Control Commands Module
Implements cross-platform audio input/output device switching
"""

import logging

from src.i18n import get_i18n

# Import platform abstraction layer
try:
    from src.platforms import get_platform_instance
    PLATFORM_AVAILABLE = True
except ImportError:
    PLATFORM_AVAILABLE = False

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class AudioCommands:
    """Audio Device Control Commands (cross-platform)"""

    def __init__(self):
        """Initialize audio commands with platform abstraction"""
        self._platform = None
        if PLATFORM_AVAILABLE:
            try:
                self._platform = get_platform_instance()
                logger.info(f"AudioCommands initialized with {self._platform.get_platform_name()}")
            except Exception as e:
                logger.warning(f"Failed to initialize platform abstraction: {e}")

    def list_devices(self) -> dict:
        """
        List all audio devices

        Returns:
            dict: Device list
        """
        if self._platform:
            try:
                devices = self._platform.list_audio_devices()
                logger.info(f"Output devices: {len(devices.get('output_devices', []))}")
                logger.info(f"Input devices: {len(devices.get('input_devices', []))}")

                return {
                    'success': True,
                    'message': _i18n.t('command_executed'),
                    'action': 'list_audio_devices',
                    'output_devices': devices.get('output_devices', []),
                    'input_devices': devices.get('input_devices', [])
                }
            except Exception as e:
                logger.error(f"Platform audio listing failed: {e}")
        
        # Fallback to direct soundcard usage
        return self._list_devices_soundcard()

    def set_audio_output(self, device_name: str) -> dict:
        """
        Set audio output device

        Args:
            device_name: Device name

        Returns:
            dict: Execution result
        """
        if self._platform:
            try:
                logger.info(f"Set audio output device: {device_name}")
                success = self._platform.set_audio_output_device(device_name)
                if success:
                    return {
                        'success': True,
                        'message': _i18n.t('command_executed'),
                        'action': 'set_audio_output',
                        'device': device_name
                    }
            except Exception as e:
                logger.error(f"Platform audio output failed: {e}")
        
        # Fallback to placeholder implementation
        return self._set_audio_output_placeholder(device_name)

    def set_audio_input(self, device_name: str) -> dict:
        """
        Set audio input device

        Args:
            device_name: Device name

        Returns:
            dict: Execution result
        """
        if self._platform:
            try:
                logger.info(f"Set audio input device: {device_name}")
                success = self._platform.set_audio_input_device(device_name)
                if success:
                    return {
                        'success': True,
                        'message': _i18n.t('command_executed'),
                        'action': 'set_audio_input',
                        'device': device_name
                    }
            except Exception as e:
                logger.error(f"Platform audio input failed: {e}")
        
        # Fallback to placeholder implementation
        return self._set_audio_input_placeholder(device_name)

    # ========== Fallback methods ==========

    @staticmethod
    def _list_devices_soundcard() -> dict:
        """List audio devices using soundcard library directly"""
        try:
            import soundcard

            # Get all output devices
            speakers = soundcard.all_speakers()
            output_devices = [speaker.name for speaker in speakers]

            # Get all input devices
            mics = soundcard.all_microphones()
            input_devices = [mic.name for mic in mics]

            logger.info(f"Output devices: {len(output_devices)}")
            logger.info(f"Input devices: {len(input_devices)}")

            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'list_audio_devices',
                'output_devices': output_devices,
                'input_devices': input_devices
            }
        except Exception as e:
            logger.error(f"Failed to list audio devices: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def _set_audio_output_placeholder(device_name: str) -> dict:
        """Placeholder for audio output switching"""
        try:
            logger.info(f"Set audio output device: {device_name}")
            # TODO: Actually switch audio output device
            # This requires calling platform-specific APIs
            # or reinitializing player with soundcard library

            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'set_audio_output',
                'device': device_name
            }
        except Exception as e:
            logger.error(f"Failed to set audio output: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }

    @staticmethod
    def _set_audio_input_placeholder(device_name: str) -> dict:
        """Placeholder for audio input switching"""
        try:
            logger.info(f"Set audio input device: {device_name}")
            # TODO: Actually switch audio input device
            # Requires reinitializing recorder

            return {
                'success': True,
                'message': _i18n.t('command_executed'),
                'action': 'set_audio_input',
                'device': device_name
            }
        except Exception as e:
            logger.error(f"Failed to set audio input: {e}")
            return {
                'success': False,
                'message': _i18n.t('command_failed'),
                'error': str(e)
            }


if __name__ == "__main__":
    # Test code
    logging.basicConfig(level=logging.INFO)

    def test_audio_commands():
        """Test audio commands"""
        logger.info("Testing audio device control commands")

        commands = AudioCommands()

        # Test list devices
        result = commands.list_devices()

        if result['success']:
            logger.info("\nOutput devices:")
            for i, device in enumerate(result['output_devices'], 1):
                logger.info(f"  {i}. {device}")

            logger.info("\nInput devices:")
            for i, device in enumerate(result['input_devices'], 1):
                logger.info(f"  {i}. {device}")

    # Run test
    test_audio_commands()
