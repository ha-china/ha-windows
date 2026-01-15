"""
Audio Device Control Commands Module
Implements audio input/output device switching
"""

import logging

from src.i18n import get_i18n

logger = logging.getLogger(__name__)
_i18n = get_i18n()


class AudioCommands:
    """Audio Device Control Commands"""

    @staticmethod
    def list_devices() -> dict:
        """
        List all audio devices

        Returns:
            dict: Device list
        """
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
    def set_audio_output(device_name: str) -> dict:
        """
        Set audio output device

        Args:
            device_name: Device name

        Returns:
            dict: Execution result
        """
        try:
            logger.info(f"Set audio output device: {device_name}")

            # TODO: Actually switch audio output device
            # This requires calling Windows API
            # or reinitializing player with soundcard library

            # Currently just logging
            # Actual use requires integration with MPV player

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
    def set_audio_input(device_name: str) -> dict:
        """
        Set audio input device

        Args:
            device_name: Device name

        Returns:
            dict: Execution result
        """
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
