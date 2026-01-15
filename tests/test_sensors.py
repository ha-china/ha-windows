"""
Property-Based Tests for Sensor Functionality

Tests Property 11: Sensor Entity Definitions
Tests Property 12: Sensor Value Validity

Validates: Requirements 5.1, 5.2
"""

import logging
import re
from typing import Dict, List, Optional, Tuple
from unittest.mock import MagicMock, patch

import pytest
from hypothesis import given, strategies as st, settings, assume

from aioesphomeapi.api_pb2 import (
    ListEntitiesDoneResponse,
    ListEntitiesTextSensorResponse,
    TextSensorStateResponse,
)

from src.sensors.windows_monitor import WindowsMonitor, SENSOR_KEYS


# =============================================================================
# Strategies for generating test data
# =============================================================================

# Strategy for generating CPU usage percentages (0-100)
cpu_percent_strategy = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Strategy for generating memory usage percentages (0-100)
memory_percent_strategy = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Strategy for generating disk usage percentages (0-100)
disk_percent_strategy = st.floats(min_value=0.0, max_value=100.0, allow_nan=False, allow_infinity=False)

# Strategy for generating battery level (0-100)
battery_level_strategy = st.integers(min_value=0, max_value=100)

# Strategy for generating battery charging status
battery_charging_strategy = st.booleans()

# Strategy for generating network bytes (non-negative)
network_bytes_strategy = st.integers(min_value=0, max_value=10**12)

# Strategy for generating complete system info
system_info_strategy = st.fixed_dictionaries({
    'cpu': st.fixed_dictionaries({
        'cpu_percent': cpu_percent_strategy,
        'cpu_count': st.integers(min_value=1, max_value=128),
    }),
    'memory': st.fixed_dictionaries({
        'percent': memory_percent_strategy,
        'total': st.integers(min_value=1, max_value=10**12),
        'used': st.integers(min_value=0, max_value=10**12),
    }),
    'disk': st.fixed_dictionaries({
        'C:\\': st.fixed_dictionaries({
            'percent': disk_percent_strategy,
            'total': st.integers(min_value=1, max_value=10**13),
            'used': st.integers(min_value=0, max_value=10**13),
        })
    }),
    'network': st.fixed_dictionaries({
        'bytes_sent': network_bytes_strategy,
        'bytes_recv': network_bytes_strategy,
    }),
})

# Strategy for system info with battery
system_info_with_battery_strategy = st.fixed_dictionaries({
    'cpu': st.fixed_dictionaries({
        'cpu_percent': cpu_percent_strategy,
        'cpu_count': st.integers(min_value=1, max_value=128),
    }),
    'memory': st.fixed_dictionaries({
        'percent': memory_percent_strategy,
        'total': st.integers(min_value=1, max_value=10**12),
        'used': st.integers(min_value=0, max_value=10**12),
    }),
    'disk': st.fixed_dictionaries({
        'C:\\': st.fixed_dictionaries({
            'percent': disk_percent_strategy,
            'total': st.integers(min_value=1, max_value=10**13),
            'used': st.integers(min_value=0, max_value=10**13),
        })
    }),
    'battery': st.fixed_dictionaries({
        'percent': battery_level_strategy,
        'power_plugged': battery_charging_strategy,
    }),
    'network': st.fixed_dictionaries({
        'bytes_sent': network_bytes_strategy,
        'bytes_recv': network_bytes_strategy,
    }),
})


# =============================================================================
# Property 11: Sensor Entity Definitions
# For any ListEntitiesRequest, the Windows_Client SHALL respond with entity
# definitions for all configured sensors (CPU, memory, disk, network, and
# battery if available).
# Validates: Requirements 5.1, 5.3, 5.4, 5.5, 5.6, 5.7
# =============================================================================

class TestSensorEntityDefinitions:
    """
    Property 11: Sensor Entity Definitions
    
    **Feature: ha-windows-client, Property 11: Sensor Entity Definitions**
    **Validates: Requirements 5.1, 5.3, 5.4, 5.5, 5.6, 5.7**
    """

    @given(system_info=system_info_strategy)
    @settings(max_examples=100, deadline=None)
    def test_entity_definitions_include_required_sensors(self, system_info: Dict):
        """
        Property 11: For any system configuration, entity definitions SHALL
        include CPU, memory, disk (if C: exists), and network sensors.
        
        **Feature: ha-windows-client, Property 11: Sensor Entity Definitions**
        **Validates: Requirements 5.1, 5.3, 5.4, 5.5, 5.7**
        """
        monitor = WindowsMonitor()
        
        # Mock get_all_info to return our generated system info
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            entities = monitor.discover_esp_entities()
        
        # Extract object_ids from entities
        object_ids = [e[0] for e in entities]
        
        # Property: CPU sensor is always included
        assert "cpu_usage" in object_ids, \
            "CPU usage sensor should always be included"
        
        # Property: Memory sensor is always included
        assert "memory_usage" in object_ids, \
            "Memory usage sensor should always be included"
        
        # Property: Disk sensor is included when C: drive exists
        if 'C:\\' in system_info.get('disk', {}):
            assert "disk_usage" in object_ids, \
                "Disk usage sensor should be included when C: drive exists"
        
        # Property: Network sensor is always included
        assert "network_status" in object_ids, \
            "Network status sensor should always be included"

    @given(system_info=system_info_with_battery_strategy)
    @settings(max_examples=100, deadline=None)
    def test_entity_definitions_include_battery_when_available(self, system_info: Dict):
        """
        Property 11: When battery info is available, entity definitions SHALL
        include battery status and battery level sensors.
        
        **Feature: ha-windows-client, Property 11: Sensor Entity Definitions**
        **Validates: Requirements 5.6**
        """
        monitor = WindowsMonitor()
        
        # Mock get_all_info to return system info with battery
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            entities = monitor.discover_esp_entities()
        
        # Extract object_ids from entities
        object_ids = [e[0] for e in entities]
        
        # Property: Battery sensors are included when battery info exists
        assert "battery_status" in object_ids, \
            "Battery status sensor should be included when battery exists"
        assert "battery_level" in object_ids, \
            "Battery level sensor should be included when battery exists"

    @given(system_info=system_info_strategy)
    @settings(max_examples=100, deadline=None)
    def test_entity_definitions_have_unique_keys(self, system_info: Dict):
        """
        Property 11: All entity definitions SHALL have unique keys.
        
        **Feature: ha-windows-client, Property 11: Sensor Entity Definitions**
        **Validates: Requirements 5.1**
        """
        monitor = WindowsMonitor()
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            entities = monitor.discover_esp_entities()
        
        # Extract keys from entities
        keys = [e[3] for e in entities]
        
        # Property: All keys are unique
        assert len(keys) == len(set(keys)), \
            f"Entity keys should be unique, got duplicates: {keys}"

    @given(system_info=system_info_strategy)
    @settings(max_examples=100, deadline=None)
    def test_entity_definitions_have_valid_structure(self, system_info: Dict):
        """
        Property 11: All entity definitions SHALL have valid structure
        (object_id, name, icon, key).
        
        **Feature: ha-windows-client, Property 11: Sensor Entity Definitions**
        **Validates: Requirements 5.1**
        """
        monitor = WindowsMonitor()
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            entities = monitor.discover_esp_entities()
        
        for entity in entities:
            # Property: Each entity is a tuple of 4 elements
            assert len(entity) == 4, \
                f"Entity should have 4 elements, got {len(entity)}"
            
            object_id, name, icon, key = entity
            
            # Property: object_id is a non-empty string
            assert isinstance(object_id, str) and object_id, \
                f"object_id should be non-empty string, got {object_id}"
            
            # Property: name is a non-empty string
            assert isinstance(name, str) and name, \
                f"name should be non-empty string, got {name}"
            
            # Property: icon starts with "mdi:"
            assert isinstance(icon, str) and icon.startswith("mdi:"), \
                f"icon should start with 'mdi:', got {icon}"
            
            # Property: key is a positive integer
            assert isinstance(key, int) and key > 0, \
                f"key should be positive integer, got {key}"

    @given(system_info=system_info_strategy)
    @settings(max_examples=100, deadline=None)
    def test_get_esp_entity_definitions_returns_protobuf_messages(self, system_info: Dict):
        """
        Property 11: get_esp_entity_definitions SHALL return valid protobuf
        messages ending with ListEntitiesDoneResponse.
        
        **Feature: ha-windows-client, Property 11: Sensor Entity Definitions**
        **Validates: Requirements 5.1**
        """
        monitor = WindowsMonitor()
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            monitor.discover_esp_entities()
            definitions = monitor.get_esp_entity_definitions()
        
        # Property: definitions is a non-empty list
        assert isinstance(definitions, list) and len(definitions) > 0, \
            "Entity definitions should be a non-empty list"
        
        # Property: Last element is ListEntitiesDoneResponse
        assert isinstance(definitions[-1], ListEntitiesDoneResponse), \
            "Last element should be ListEntitiesDoneResponse"
        
        # Property: All other elements are ListEntitiesTextSensorResponse
        for i, definition in enumerate(definitions[:-1]):
            assert isinstance(definition, ListEntitiesTextSensorResponse), \
                f"Element {i} should be ListEntitiesTextSensorResponse"

    def test_sensor_keys_are_predefined(self):
        """
        Property 11: All sensor keys SHALL be predefined in SENSOR_KEYS.
        
        **Feature: ha-windows-client, Property 11: Sensor Entity Definitions**
        **Validates: Requirements 5.1**
        """
        # Property: SENSOR_KEYS contains expected sensors
        expected_sensors = ["cpu_usage", "memory_usage", "disk_usage", 
                          "battery_status", "battery_level", "network_status"]
        
        for sensor in expected_sensors:
            assert sensor in SENSOR_KEYS, \
                f"SENSOR_KEYS should contain '{sensor}'"
        
        # Property: All keys are unique positive integers
        keys = list(SENSOR_KEYS.values())
        assert len(keys) == len(set(keys)), \
            "All sensor keys should be unique"
        assert all(isinstance(k, int) and k > 0 for k in keys), \
            "All sensor keys should be positive integers"


# =============================================================================
# Property 12: Sensor Value Validity
# For any sensor value reported, the value SHALL be within valid range
# (0-100 for percentages, valid enum for status).
# Validates: Requirements 5.2
# =============================================================================

class TestSensorValueValidity:
    """
    Property 12: Sensor Value Validity
    
    **Feature: ha-windows-client, Property 12: Sensor Value Validity**
    **Validates: Requirements 5.2**
    """

    @given(cpu_percent=cpu_percent_strategy)
    @settings(max_examples=100, deadline=None)
    def test_cpu_usage_value_in_valid_range(self, cpu_percent: float):
        """
        Property 12: CPU usage value SHALL be in range 0-100%.
        
        **Feature: ha-windows-client, Property 12: Sensor Value Validity**
        **Validates: Requirements 5.2**
        """
        monitor = WindowsMonitor()
        
        system_info = {
            'cpu': {'cpu_percent': cpu_percent},
            'memory': {'percent': 50.0},
            'disk': {'C:\\': {'percent': 50.0}},
            'network': {'bytes_sent': 1000, 'bytes_recv': 1000},
        }
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            monitor.discover_esp_entities()
            states = monitor.get_esp_sensor_states()
        
        # Find CPU state
        cpu_state = None
        for state in states:
            if state.key == SENSOR_KEYS["cpu_usage"]:
                cpu_state = state
                break
        
        assert cpu_state is not None, "CPU state should be present"
        
        # Extract numeric value from state string (e.g., "50.0%")
        value_str = cpu_state.state.rstrip('%')
        value = float(value_str)
        
        # Property: CPU value is in valid range
        assert 0.0 <= value <= 100.0, \
            f"CPU usage {value} should be in range 0-100"

    @given(memory_percent=memory_percent_strategy)
    @settings(max_examples=100, deadline=None)
    def test_memory_usage_value_in_valid_range(self, memory_percent: float):
        """
        Property 12: Memory usage value SHALL be in range 0-100%.
        
        **Feature: ha-windows-client, Property 12: Sensor Value Validity**
        **Validates: Requirements 5.2**
        """
        monitor = WindowsMonitor()
        
        system_info = {
            'cpu': {'cpu_percent': 50.0},
            'memory': {'percent': memory_percent},
            'disk': {'C:\\': {'percent': 50.0}},
            'network': {'bytes_sent': 1000, 'bytes_recv': 1000},
        }
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            monitor.discover_esp_entities()
            states = monitor.get_esp_sensor_states()
        
        # Find memory state
        memory_state = None
        for state in states:
            if state.key == SENSOR_KEYS["memory_usage"]:
                memory_state = state
                break
        
        assert memory_state is not None, "Memory state should be present"
        
        # Extract numeric value from state string
        value_str = memory_state.state.rstrip('%')
        value = float(value_str)
        
        # Property: Memory value is in valid range
        assert 0.0 <= value <= 100.0, \
            f"Memory usage {value} should be in range 0-100"

    @given(disk_percent=disk_percent_strategy)
    @settings(max_examples=100, deadline=None)
    def test_disk_usage_value_in_valid_range(self, disk_percent: float):
        """
        Property 12: Disk usage value SHALL be in range 0-100%.
        
        **Feature: ha-windows-client, Property 12: Sensor Value Validity**
        **Validates: Requirements 5.2**
        """
        monitor = WindowsMonitor()
        
        system_info = {
            'cpu': {'cpu_percent': 50.0},
            'memory': {'percent': 50.0},
            'disk': {'C:\\': {'percent': disk_percent}},
            'network': {'bytes_sent': 1000, 'bytes_recv': 1000},
        }
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            monitor.discover_esp_entities()
            states = monitor.get_esp_sensor_states()
        
        # Find disk state
        disk_state = None
        for state in states:
            if state.key == SENSOR_KEYS["disk_usage"]:
                disk_state = state
                break
        
        assert disk_state is not None, "Disk state should be present"
        
        # Extract numeric value from state string
        value_str = disk_state.state.rstrip('%')
        value = float(value_str)
        
        # Property: Disk value is in valid range
        assert 0.0 <= value <= 100.0, \
            f"Disk usage {value} should be in range 0-100"

    @given(battery_level=battery_level_strategy)
    @settings(max_examples=100, deadline=None)
    def test_battery_level_value_in_valid_range(self, battery_level: int):
        """
        Property 12: Battery level value SHALL be in range 0-100%.
        
        **Feature: ha-windows-client, Property 12: Sensor Value Validity**
        **Validates: Requirements 5.2**
        """
        monitor = WindowsMonitor()
        
        system_info = {
            'cpu': {'cpu_percent': 50.0},
            'memory': {'percent': 50.0},
            'disk': {'C:\\': {'percent': 50.0}},
            'battery': {'percent': battery_level, 'power_plugged': True},
            'network': {'bytes_sent': 1000, 'bytes_recv': 1000},
        }
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            monitor.discover_esp_entities()
            states = monitor.get_esp_sensor_states()
        
        # Find battery level state
        battery_state = None
        for state in states:
            if state.key == SENSOR_KEYS["battery_level"]:
                battery_state = state
                break
        
        assert battery_state is not None, "Battery level state should be present"
        
        # Extract numeric value from state string
        value_str = battery_state.state.rstrip('%')
        value = float(value_str)
        
        # Property: Battery level is in valid range
        assert 0 <= value <= 100, \
            f"Battery level {value} should be in range 0-100"

    @given(power_plugged=battery_charging_strategy)
    @settings(max_examples=100, deadline=None)
    def test_battery_status_value_is_valid_enum(self, power_plugged: bool):
        """
        Property 12: Battery status value SHALL be a valid enum
        (Charging or Discharging).
        
        **Feature: ha-windows-client, Property 12: Sensor Value Validity**
        **Validates: Requirements 5.2**
        """
        monitor = WindowsMonitor()
        
        system_info = {
            'cpu': {'cpu_percent': 50.0},
            'memory': {'percent': 50.0},
            'disk': {'C:\\': {'percent': 50.0}},
            'battery': {'percent': 50, 'power_plugged': power_plugged},
            'network': {'bytes_sent': 1000, 'bytes_recv': 1000},
        }
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            monitor.discover_esp_entities()
            states = monitor.get_esp_sensor_states()
        
        # Find battery status state
        battery_status = None
        for state in states:
            if state.key == SENSOR_KEYS["battery_status"]:
                battery_status = state
                break
        
        assert battery_status is not None, "Battery status state should be present"
        
        # Property: Battery status is valid enum
        valid_statuses = {"Charging", "Discharging"}
        assert battery_status.state in valid_statuses, \
            f"Battery status '{battery_status.state}' should be in {valid_statuses}"
        
        # Property: Status matches power_plugged value
        expected_status = "Charging" if power_plugged else "Discharging"
        assert battery_status.state == expected_status, \
            f"Battery status should be '{expected_status}' when power_plugged={power_plugged}"

    @given(bytes_sent=network_bytes_strategy, bytes_recv=network_bytes_strategy)
    @settings(max_examples=100, deadline=None)
    def test_network_status_value_is_valid_enum(self, bytes_sent: int, bytes_recv: int):
        """
        Property 12: Network status value SHALL be a valid enum
        (Online or Offline).
        
        **Feature: ha-windows-client, Property 12: Sensor Value Validity**
        **Validates: Requirements 5.2**
        """
        monitor = WindowsMonitor()
        
        system_info = {
            'cpu': {'cpu_percent': 50.0},
            'memory': {'percent': 50.0},
            'disk': {'C:\\': {'percent': 50.0}},
            'network': {'bytes_sent': bytes_sent, 'bytes_recv': bytes_recv},
        }
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            monitor.discover_esp_entities()
            states = monitor.get_esp_sensor_states()
        
        # Find network status state
        network_status = None
        for state in states:
            if state.key == SENSOR_KEYS["network_status"]:
                network_status = state
                break
        
        assert network_status is not None, "Network status state should be present"
        
        # Property: Network status is valid enum
        valid_statuses = {"Online", "Offline"}
        assert network_status.state in valid_statuses, \
            f"Network status '{network_status.state}' should be in {valid_statuses}"

    @given(system_info=system_info_strategy)
    @settings(max_examples=100, deadline=None)
    def test_all_states_are_text_sensor_responses(self, system_info: Dict):
        """
        Property 12: All sensor states SHALL be TextSensorStateResponse objects.
        
        **Feature: ha-windows-client, Property 12: Sensor Value Validity**
        **Validates: Requirements 5.2**
        """
        monitor = WindowsMonitor()
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            monitor.discover_esp_entities()
            states = monitor.get_esp_sensor_states()
        
        # Property: All states are TextSensorStateResponse
        for state in states:
            assert isinstance(state, TextSensorStateResponse), \
                f"State should be TextSensorStateResponse, got {type(state)}"

    @given(system_info=system_info_strategy)
    @settings(max_examples=100, deadline=None)
    def test_state_keys_match_entity_keys(self, system_info: Dict):
        """
        Property 12: All state keys SHALL match defined entity keys.
        
        **Feature: ha-windows-client, Property 12: Sensor Value Validity**
        **Validates: Requirements 5.2**
        """
        monitor = WindowsMonitor()
        
        with patch.object(monitor, 'get_all_info', return_value=system_info):
            monitor.discover_esp_entities()
            definitions = monitor.get_esp_entity_definitions()
            states = monitor.get_esp_sensor_states()
        
        # Get entity keys (excluding ListEntitiesDoneResponse)
        entity_keys = {d.key for d in definitions[:-1]}
        
        # Get state keys
        state_keys = {s.key for s in states}
        
        # Property: All state keys are in entity keys
        assert state_keys.issubset(entity_keys), \
            f"State keys {state_keys} should be subset of entity keys {entity_keys}"


# =============================================================================
# Additional edge case tests
# =============================================================================

class TestSensorEdgeCases:
    """Edge case tests for sensor functionality"""

    def test_monitor_initialization(self):
        """
        WindowsMonitor SHALL initialize without errors.
        """
        monitor = WindowsMonitor()
        assert monitor is not None

    def test_discover_entities_is_idempotent(self):
        """
        Calling discover_esp_entities multiple times SHALL return
        consistent results.
        """
        monitor = WindowsMonitor()
        
        entities1 = monitor.discover_esp_entities()
        entities2 = monitor.discover_esp_entities()
        
        # Property: Results are consistent
        assert entities1 == entities2, \
            "discover_esp_entities should return consistent results"

    def test_get_entity_count_matches_entities(self):
        """
        get_esp_entity_count SHALL return the correct count.
        """
        monitor = WindowsMonitor()
        
        entities = monitor.discover_esp_entities()
        count = monitor.get_esp_entity_count()
        
        assert count == len(entities), \
            f"Entity count {count} should match entities length {len(entities)}"

    def test_states_without_discovery_triggers_discovery(self):
        """
        Calling get_esp_sensor_states without prior discovery SHALL
        trigger entity discovery.
        """
        monitor = WindowsMonitor()
        
        # Call states without discovery
        states = monitor.get_esp_sensor_states()
        
        # Property: States are returned (discovery was triggered)
        assert isinstance(states, list), \
            "get_esp_sensor_states should return a list"

    def test_extra_states_are_included(self):
        """
        Extra states passed to get_esp_sensor_states SHALL be included
        in the response.
        """
        monitor = WindowsMonitor()
        monitor.discover_esp_entities()
        
        # Add a custom entity to the map for testing
        monitor._entity_map["custom_sensor"] = ("Custom Sensor", "mdi:test", 99)
        
        states = monitor.get_esp_sensor_states(custom_sensor="test_value")
        
        # Find custom state
        custom_state = None
        for state in states:
            if state.key == 99:
                custom_state = state
                break
        
        assert custom_state is not None, "Custom state should be present"
        assert custom_state.state == "test_value", \
            f"Custom state value should be 'test_value', got '{custom_state.state}'"
