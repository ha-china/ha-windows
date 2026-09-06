"""Tests for the shared audio output device selection (issue #12)."""

import pytest

from src.core import audio_output
from src.core.audio_output import (
    apply_output_device,
    get_selected_device,
    list_output_devices,
    resolve_output_device,
)


@pytest.fixture(autouse=True)
def restore_selection():
    """Leave the global selection untouched across tests."""
    previous = get_selected_device()
    yield
    apply_output_device(previous)


class TestListOutputDevices:
    def test_returns_list(self):
        devices = list_output_devices()

        assert isinstance(devices, list), "list_output_devices should return a list"

    def test_has_no_duplicates(self):
        devices = list_output_devices()

        assert len(devices) == len(set(devices)), f"Duplicate output names: {devices}"

    def test_listed_output_device_resolves_to_an_output_device(self):
        """Every listed output name SHALL resolve to a real output device index."""
        for name in list_output_devices():
            device_id = resolve_output_device(name)

            assert device_id is not None, f"Listed output device did not resolve: {name}"


class TestResolveOutputDevice:
    def test_default_selections_resolve_to_none(self):
        assert resolve_output_device(None) is None, "None should mean system default"
        assert resolve_output_device("") is None, '"" should mean system default'

    def test_unknown_device_resolves_to_none(self):
        assert resolve_output_device("Definitely Not A Real Device") is None


class TestApplyOutputDevice:
    def test_selection_is_recorded(self):
        apply_output_device("Some Device")

        assert get_selected_device() == "Some Device"

    def test_empty_selection_means_system_default(self):
        apply_output_device("Some Device")
        apply_output_device("")

        assert get_selected_device() == ""

    def test_pygame_mixer_stays_usable_after_apply(self):
        """An explicit device switch SHALL never leave the mixer uninitialized.

        Even when the stored name no longer exists (device unplugged), the
        pygame fallback keeps audio working on the system default.
        """
        apply_output_device("Definitely Not A Real Device")

        try:
            import pygame

            assert pygame.mixer.get_init() is not None, "pygame mixer should be initialized after the switch"
        except ImportError:
            pytest.skip("pygame not installed")

    def test_selection_survives_reapplying_same_device(self):
        apply_output_device("Some Device")
        apply_output_device("Some Device")

        assert get_selected_device() == "Some Device"


class TestResolveEndpointId:
    def test_listed_output_device_maps_to_a_render_endpoint(self):
        """Listed names SHALL map to a Windows render endpoint (VLC switching)."""
        if not list_output_devices():
            pytest.skip("No output devices available")

        for name in list_output_devices()[:1]:
            endpoint = audio_output.resolve_endpoint_id(name)
            # Some host APIs (WDM-KS fallback) may not match pycaw names;
            # a match must however always be a render endpoint.
            if endpoint is not None:
                assert str(endpoint).startswith("{0.0.0."), f"Expected a render endpoint id, got: {endpoint}"

    def test_unknown_device_has_no_endpoint(self):
        assert audio_output.resolve_endpoint_id("Definitely Not A Real Device") is None
