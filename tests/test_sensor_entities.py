"""Sensor tests using real Home Assistant classes, separate from stub-based tests.

Run with Python 3.13 and homeassistant==2025.6.3, pycares<5 installed:
python -m unittest discover -s tests -p 'test_sensor_entities.py'
"""

from dataclasses import replace
from importlib import import_module
from pathlib import Path
import sys
from types import ModuleType, SimpleNamespace
import unittest

from homeassistant.components.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.util.unit_system import METRIC_SYSTEM

# Load platforms without starting the integration's HTTP and recorder setup.
package = ModuleType("halthy_sensor_tests")
package.__path__ = [str(Path(__file__).resolve().parents[1] / "custom_components/halthy")]
sys.modules[package.__name__] = package
sensor_module = import_module(f"{package.__name__}.sensor")
runtime_module = import_module(f"{package.__name__}.runtime")


class SensorEntityTests(unittest.TestCase):
    def make_sensor(self, key, value, unit):
        state = runtime_module.HalthySensorState(
            unique_id=f"tester_{key}", metric_key=key, name="Body mass" if key == "body_mass" else key,
            state=value, unit=unit, icon=None, attributes={}, username="tester", device_id="phone",
        )
        runtime = runtime_module.IntegrationRuntime(
            configured_username="tester", app_username="tester", display_name="Tester",
            sensors={state.unique_id: state},
        )
        sensor = sensor_module.HalthySensor(runtime, "entry", state.unique_id)
        sensor.hass = SimpleNamespace(config=SimpleNamespace(units=METRIC_SYSTEM))
        return sensor, state

    def test_height_converts_values_and_keeps_raw_state(self):
        for value, unit, expected in ((1.785, "m", 178.5), (178.5, "cm", 178.5), (70, "in", 177.8)):
            with self.subTest(unit=unit):
                sensor, original = self.make_sensor("height", value, unit)
                self.assertAlmostEqual(sensor.native_value, expected)
                self.assertEqual(sensor.native_unit_of_measurement, "cm")
                self.assertEqual(sensor.suggested_unit_of_measurement, "cm")
                self.assertEqual(sensor.suggested_display_precision, 1)
                self.assertEqual(sensor.device_class, SensorDeviceClass.DISTANCE)
                self.assertEqual(sensor.state_class, SensorStateClass.MEASUREMENT)
                sensor._apply_state(original)
                self.assertAlmostEqual(sensor.native_value, expected)
                self.assertEqual((original.state, original.unit), (value, unit))

    def test_weight_name_and_identity(self):
        sensor, _ = self.make_sensor("body_mass", 75.25, "kg")
        self.assertEqual(sensor.name, "Weight")
        self.assertEqual(sensor.unique_id, "tester_body_mass")
        self.assertEqual(sensor._attr_suggested_object_id, "tester_body_mass")
        self.assertEqual(sensor.device_class, SensorDeviceClass.WEIGHT)
        self.assertEqual(sensor.native_value, 75.25)
        self.assertEqual(sensor.suggested_display_precision, 1)

    def test_user_unit_and_precision_survive_upload(self):
        for key, value, native_unit, selected_unit, expected in (
            ("height", 1.778, "m", "in", 70),
            ("body_mass", 75, "kg", "lb", 165.346697),
        ):
            with self.subTest(key=key):
                sensor, original = self.make_sensor(key, value, native_unit)
                sensor.registry_entry = SimpleNamespace(options={"sensor": {
                    "unit_of_measurement": selected_unit, "display_precision": 2,
                }})
                sensor._async_read_entity_options()
                self.assertEqual(sensor.unit_of_measurement, selected_unit)
                self.assertAlmostEqual(sensor.state, expected, places=5)
                sensor._apply_state(replace(original, state=value * 1.01))
                self.assertEqual(sensor.unit_of_measurement, selected_unit)
                self.assertAlmostEqual(sensor.state, expected * 1.01, places=5)
                self.assertEqual(sensor._sensor_option_display_precision, 2)

    def test_unrelated_metrics_and_invalid_units_are_not_reclassified(self):
        for key, unit in (("body_mass_index", "kg/m2"), ("height", None), ("body_mass", "invalid")):
            with self.subTest(key=key, unit=unit):
                sensor, _ = self.make_sensor(key, 20, unit)
                self.assertIsNone(sensor.device_class)
                self.assertEqual(sensor.native_value, 20)
                self.assertEqual(sensor.native_unit_of_measurement, unit)


if __name__ == "__main__":
    unittest.main()
