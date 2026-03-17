"""Unit tests for statistics import helpers."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone
import importlib.util
import pathlib
import sys
import types
import unittest


def _install_homeassistant_stubs() -> None:
    if "aiohttp" not in sys.modules:
        aiohttp_module = types.ModuleType("aiohttp")
        web_module = types.SimpleNamespace(
            Request=type("Request", (), {}),
            Response=type("Response", (), {}),
            json_response=lambda *args, **kwargs: {"args": args, "kwargs": kwargs},
        )
        aiohttp_module.web = web_module
        sys.modules["aiohttp"] = aiohttp_module

    if "homeassistant" not in sys.modules:
        sys.modules["homeassistant"] = types.ModuleType("homeassistant")

    const_module = sys.modules.setdefault(
        "homeassistant.const",
        types.ModuleType("homeassistant.const"),
    )
    if not hasattr(const_module, "Platform"):
        const_module.Platform = type("Platform", (), {"SENSOR": "sensor"})
    if not hasattr(const_module, "UnitOfTemperature"):
        const_module.UnitOfTemperature = type(
            "UnitOfTemperature",
            (),
            {"CELSIUS": "°C", "FAHRENHEIT": "°F"},
        )

    if "homeassistant.components" not in sys.modules:
        sys.modules["homeassistant.components"] = types.ModuleType("homeassistant.components")

    http_module = sys.modules.setdefault(
        "homeassistant.components.http",
        types.ModuleType("homeassistant.components.http"),
    )
    if not hasattr(http_module, "KEY_HASS"):
        http_module.KEY_HASS = "hass"
    if not hasattr(http_module, "HomeAssistantView"):
        http_module.HomeAssistantView = type("HomeAssistantView", (), {})

    recorder_statistics_module = sys.modules.setdefault(
        "homeassistant.components.recorder.statistics",
        types.ModuleType("homeassistant.components.recorder.statistics"),
    )
    if not hasattr(recorder_statistics_module, "async_add_external_statistics"):

        async def _default_add_external_statistics(_hass, _metadata, _rows):
            return None

        recorder_statistics_module.async_add_external_statistics = _default_add_external_statistics

    recorder_models_module = sys.modules.setdefault(
        "homeassistant.components.recorder.models.statistics",
        types.ModuleType("homeassistant.components.recorder.models.statistics"),
    )
    if not hasattr(recorder_models_module, "StatisticMeanType"):
        recorder_models_module.StatisticMeanType = type(
            "StatisticMeanType",
            (),
            {"ARITHMETIC": 1},
        )
    if not hasattr(recorder_models_module, "StatisticMetaData"):

        class _StatisticMetaData:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        recorder_models_module.StatisticMetaData = _StatisticMetaData
    if not hasattr(recorder_models_module, "StatisticData"):

        class _StatisticData:
            def __init__(self, **kwargs):
                for key, value in kwargs.items():
                    setattr(self, key, value)

        recorder_models_module.StatisticData = _StatisticData

    if "homeassistant.helpers" not in sys.modules:
        sys.modules["homeassistant.helpers"] = types.ModuleType("homeassistant.helpers")

    entity_registry_module = sys.modules.setdefault(
        "homeassistant.helpers.entity_registry",
        types.ModuleType("homeassistant.helpers.entity_registry"),
    )
    if not hasattr(entity_registry_module, "async_get"):
        entity_registry_module.async_get = lambda _hass: None
    if not hasattr(entity_registry_module, "async_entries_for_config_entry"):
        entity_registry_module.async_entries_for_config_entry = lambda _registry, _entry_id: []

    dispatcher_module = sys.modules.setdefault(
        "homeassistant.helpers.dispatcher",
        types.ModuleType("homeassistant.helpers.dispatcher"),
    )
    if not hasattr(dispatcher_module, "async_dispatcher_send"):
        dispatcher_module.async_dispatcher_send = lambda *_args, **_kwargs: None

    storage_module = sys.modules.setdefault(
        "homeassistant.helpers.storage",
        types.ModuleType("homeassistant.helpers.storage"),
    )
    if not hasattr(storage_module, "Store"):

        class _Store:
            def __init__(self, *_args, **_kwargs):
                return

            async def async_load(self):
                return None

            def async_delay_save(self, *_args, **_kwargs):
                return

        storage_module.Store = _Store

    config_entries_module = sys.modules.setdefault(
        "homeassistant.config_entries",
        types.ModuleType("homeassistant.config_entries"),
    )
    if not hasattr(config_entries_module, "ConfigEntry"):
        config_entries_module.ConfigEntry = type("ConfigEntry", (), {})

    core_module = sys.modules.setdefault(
        "homeassistant.core",
        types.ModuleType("homeassistant.core"),
    )
    if not hasattr(core_module, "HomeAssistant"):
        core_module.HomeAssistant = type("HomeAssistant", (), {})


def _load_integration_module():
    _install_homeassistant_stubs()

    package_name = "halthy_testpkg_stats"
    if package_name not in sys.modules:
        package = types.ModuleType(package_name)
        package.__path__ = []  # type: ignore[attr-defined]
        sys.modules[package_name] = package

    base_path = pathlib.Path(__file__).resolve().parents[1]
    for module_base in ("const", "naming", "units"):
        module_name = f"{package_name}.{module_base}"
        if module_name in sys.modules:
            continue
        module_path = base_path / f"{module_base}.py"
        spec = importlib.util.spec_from_file_location(module_name, module_path)
        assert spec and spec.loader
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)

    module_name = f"{package_name}.bridge"
    if module_name in sys.modules:
        return sys.modules[module_name]

    module_path = base_path / "__init__.py"
    spec = importlib.util.spec_from_file_location(module_name, module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module

    # Python 3.9 does not support dataclass(slots=True), so ignore this kwarg while loading.
    original_dataclass = dataclasses.dataclass

    def _compat_dataclass(*args, **kwargs):
        kwargs.pop("slots", None)
        return original_dataclass(*args, **kwargs)

    dataclasses.dataclass = _compat_dataclass  # type: ignore[assignment]
    try:
        spec.loader.exec_module(module)
    finally:
        dataclasses.dataclass = original_dataclass  # type: ignore[assignment]
    return module


BRIDGE = _load_integration_module()


class StatisticsHelpersTests(unittest.TestCase):
    def test_prepare_statistics_uses_top_of_hour_buckets(self) -> None:
        runtime = BRIDGE.IntegrationRuntime(
            configured_username="tester",
            app_username="tester",
            display_name="Tester",
        )
        statistic_id = BRIDGE._statistics_id_for_metric("tester", "heart_rate")
        candidates = [
            {
                "statistic_id": statistic_id,
                "name": "Heart rate",
                "unit": "bpm",
                "start": datetime(2026, 3, 1, 10, 6, tzinfo=timezone.utc),
                "value": 61.0,
            },
            {
                "statistic_id": statistic_id,
                "name": "Heart rate",
                "unit": "bpm",
                "start": datetime(2026, 3, 1, 10, 42, tzinfo=timezone.utc),
                "value": 67.0,
            },
        ]

        batches, _cursor_updates = BRIDGE._prepare_statistics_imports_for_runtime(
            runtime, candidates
        )
        self.assertEqual(len(batches), 1)
        _metadata, rows = batches[0]
        self.assertEqual(len(rows), 1)
        start = getattr(rows[0], "start")
        self.assertEqual(start.minute, 0)
        self.assertEqual(start.second, 0)
        self.assertEqual(start.microsecond, 0)

    def test_statistics_metadata_includes_unit_class(self) -> None:
        statistic_id = BRIDGE._statistics_id_for_metric("tester", "heart_rate")
        metadata = BRIDGE._statistics_metadata(statistic_id, "Heart rate", "bpm")
        self.assertIsNotNone(metadata)
        self.assertTrue(hasattr(metadata, "unit_class"))
        self.assertIsNone(getattr(metadata, "unit_class"))

    def test_prepare_statistics_does_not_advance_cursor(self) -> None:
        runtime = BRIDGE.IntegrationRuntime(
            configured_username="tester",
            app_username="tester",
            display_name="Tester",
        )
        statistic_id = BRIDGE._statistics_id_for_metric("tester", "heart_rate")
        previous_cursor = "2026-03-01T10:00:00+00:00"
        runtime.statistics_cursors[statistic_id] = previous_cursor

        candidates = [
            {
                "statistic_id": statistic_id,
                "name": "Heart rate",
                "unit": "bpm",
                "start": datetime(2026, 3, 1, 10, 6, tzinfo=timezone.utc),
                "value": 61.0,
            }
        ]
        batches, cursor_updates = BRIDGE._prepare_statistics_imports_for_runtime(runtime, candidates)

        self.assertEqual(runtime.statistics_cursors.get(statistic_id), previous_cursor)
        self.assertEqual(len(batches), 1)
        self.assertIn(statistic_id, cursor_updates)
        self.assertEqual(
            cursor_updates[statistic_id].latest_imported_at,
            datetime(2026, 3, 1, 10, 6, tzinfo=timezone.utc),
        )

    def test_commit_statistics_updates_only_successful_series(self) -> None:
        runtime = BRIDGE.IntegrationRuntime(
            configured_username="tester",
            app_username="tester",
            display_name="Tester",
        )
        successful_statistic_id = BRIDGE._statistics_id_for_metric("tester", "heart_rate")
        failed_statistic_id = BRIDGE._statistics_id_for_metric("tester", "oxygen_saturation")
        legacy_id = "tester_heart_rate"
        runtime.statistics_cursors[legacy_id] = "2026-03-01T09:30:00+00:00"
        runtime.statistics_cursors[failed_statistic_id] = "2026-03-01T09:00:00+00:00"

        cursor_updates = {
            successful_statistic_id: BRIDGE.StatisticsCursorUpdate(
                latest_imported_at=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
                legacy_statistic_ids=(legacy_id,),
            ),
            failed_statistic_id: BRIDGE.StatisticsCursorUpdate(
                latest_imported_at=datetime(2026, 3, 1, 10, 5, tzinfo=timezone.utc),
                legacy_statistic_ids=(),
            ),
        }
        BRIDGE._commit_statistics_cursor_updates(
            runtime=runtime,
            cursor_updates=cursor_updates,
            successful_statistic_ids={successful_statistic_id},
        )

        self.assertEqual(
            runtime.statistics_cursors.get(successful_statistic_id),
            "2026-03-01T10:00:00+00:00",
        )
        self.assertNotIn(legacy_id, runtime.statistics_cursors)
        self.assertEqual(
            runtime.statistics_cursors.get(failed_statistic_id),
            "2026-03-01T09:00:00+00:00",
        )

    def test_commit_statistics_never_rolls_cursor_back(self) -> None:
        runtime = BRIDGE.IntegrationRuntime(
            configured_username="tester",
            app_username="tester",
            display_name="Tester",
        )
        statistic_id = BRIDGE._statistics_id_for_metric("tester", "heart_rate")
        runtime.statistics_cursors[statistic_id] = "2026-03-01T12:00:00+00:00"

        cursor_updates = {
            statistic_id: BRIDGE.StatisticsCursorUpdate(
                latest_imported_at=datetime(2026, 3, 1, 11, 0, tzinfo=timezone.utc),
                legacy_statistic_ids=(),
            )
        }
        BRIDGE._commit_statistics_cursor_updates(
            runtime=runtime,
            cursor_updates=cursor_updates,
            successful_statistic_ids={statistic_id},
        )

        self.assertEqual(
            runtime.statistics_cursors.get(statistic_id),
            "2026-03-01T12:00:00+00:00",
        )

    def test_statistics_batch_import_reports_successful_series(self) -> None:
        statistic_id_ok = BRIDGE._statistics_id_for_metric("tester", "heart_rate")
        statistic_id_fail = BRIDGE._statistics_id_for_metric("tester", "oxygen_saturation")

        metadata_ok = BRIDGE._statistics_metadata(statistic_id_ok, "Heart rate", "bpm")
        metadata_fail = BRIDGE._statistics_metadata(statistic_id_fail, "Blood oxygen", "%")
        row_ok = BRIDGE._statistics_data(
            start=datetime(2026, 3, 1, 10, 0, tzinfo=timezone.utc),
            state=61.0,
        )
        row_fail = BRIDGE._statistics_data(
            start=datetime(2026, 3, 1, 10, 5, tzinfo=timezone.utc),
            state=97.0,
        )
        self.assertIsNotNone(metadata_ok)
        self.assertIsNotNone(metadata_fail)
        self.assertIsNotNone(row_ok)
        self.assertIsNotNone(row_fail)

        original_importer = BRIDGE.async_add_external_statistics

        async def _fake_importer(_hass, metadata, _rows):
            if getattr(metadata, "statistic_id", "") == statistic_id_fail:
                raise RuntimeError("simulated failure")
            return None

        BRIDGE.async_add_external_statistics = _fake_importer
        try:
            imported_samples, successful_ids = asyncio.run(
                BRIDGE._async_import_statistics_batches(
                    hass=object(),
                    batches=[
                        (metadata_ok, [row_ok]),
                        (metadata_fail, [row_fail]),
                    ],
                )
            )
        finally:
            BRIDGE.async_add_external_statistics = original_importer

        self.assertEqual(imported_samples, 1)
        self.assertIn(statistic_id_ok, successful_ids)
        self.assertNotIn(statistic_id_fail, successful_ids)


if __name__ == "__main__":
    unittest.main()
