"""Unit tests for statistics import helpers."""

from __future__ import annotations

import asyncio
import dataclasses
from datetime import datetime, timezone
import importlib.util
import os
import pathlib
import sys
import tempfile
import types
import unittest


def _install_homeassistant_stubs() -> None:
    if "voluptuous" not in sys.modules:
        voluptuous_module = types.ModuleType("voluptuous")
        voluptuous_module.Schema = lambda schema, *args, **kwargs: schema
        voluptuous_module.Optional = lambda key, *args, **kwargs: key
        voluptuous_module.Required = lambda key, *args, **kwargs: key
        sys.modules["voluptuous"] = voluptuous_module

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

    config_validation_module = sys.modules.setdefault(
        "homeassistant.helpers.config_validation",
        types.ModuleType("homeassistant.helpers.config_validation"),
    )
    if not hasattr(config_validation_module, "string"):
        config_validation_module.string = str
    if not hasattr(config_validation_module, "config_entry_only_config_schema"):
        config_validation_module.config_entry_only_config_schema = lambda domain: {domain: {}}

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

    event_module = sys.modules.setdefault(
        "homeassistant.helpers.event",
        types.ModuleType("homeassistant.helpers.event"),
    )
    if not hasattr(event_module, "async_track_time_change"):
        event_module.async_track_time_change = lambda *_args, **_kwargs: (lambda: None)
    if not hasattr(event_module, "async_track_time_interval"):
        event_module.async_track_time_interval = lambda *_args, **_kwargs: (lambda: None)

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
    if not hasattr(core_module, "ServiceCall"):
        core_module.ServiceCall = type("ServiceCall", (), {"data": {}})
    if not hasattr(core_module, "callback"):
        core_module.callback = lambda func: func

    if "homeassistant.util" not in sys.modules:
        sys.modules["homeassistant.util"] = types.ModuleType("homeassistant.util")
    dt_module = sys.modules.setdefault(
        "homeassistant.util.dt",
        types.ModuleType("homeassistant.util.dt"),
    )
    if not hasattr(dt_module, "now"):
        dt_module.now = lambda: datetime.now(timezone.utc)


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
    def test_workout_archive_timestamp_from_file_name_formats(self) -> None:
        self.assertEqual(
            BRIDGE._workout_archive_timestamp_from_file_name("20260323T123436Z_uuid_test.jpg"),
            datetime(2026, 3, 23, 12, 34, 36, tzinfo=timezone.utc),
        )
        self.assertEqual(
            BRIDGE._workout_archive_timestamp_from_file_name("workout_2026-04-01_10-11-12_map.png"),
            datetime(2026, 4, 1, 10, 11, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(
            BRIDGE._workout_archive_timestamp_from_file_name("route_20260402.jpg"),
            datetime(2026, 4, 2, 0, 0, 0, tzinfo=timezone.utc),
        )

    def test_collect_workout_archive_records_includes_legacy_folders(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = pathlib.Path(temp_dir)
            modern_dir = media_root / "halthy" / "workouts" / "tester"
            legacy_dir = media_root / "halthy_bridge" / "workouts" / "tester"
            modern_dir.mkdir(parents=True, exist_ok=True)
            legacy_dir.mkdir(parents=True, exist_ok=True)

            modern_file = modern_dir / "20260401T101112Z_uuid_modern.jpg"
            legacy_file = legacy_dir / "20260323T123436Z_uuid_legacy.png"
            modern_file.write_bytes(b"modern")
            legacy_file.write_bytes(b"legacy")
            os.utime(modern_file, (1711966272, 1711966272))
            os.utime(legacy_file, (1710765276, 1710765276))

            records = BRIDGE._collect_workout_archive_records(media_root, "tester", limit=10)

            self.assertEqual(len(records), 2)
            self.assertEqual(records[0]["file_name"], "20260401T101112Z_uuid_modern.jpg")
            self.assertEqual(records[0]["day_key"], "2026-04-01")
            self.assertEqual(records[1]["file_name"], "20260323T123436Z_uuid_legacy.png")
            self.assertEqual(records[1]["day_key"], "2026-03-23")
            self.assertTrue(records[0]["local_url"].startswith("/media/local/"))
            self.assertIn("/halthy/workouts/tester/", records[0]["local_url"])

    def test_collect_workout_archive_records_prefers_newest_copy_of_same_workout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = pathlib.Path(temp_dir)
            modern_dir = media_root / "halthy" / "workouts" / "tester"
            legacy_dir = media_root / "halthy_bridge" / "workouts" / "tester"
            modern_dir.mkdir(parents=True, exist_ok=True)
            legacy_dir.mkdir(parents=True, exist_ok=True)

            file_name = "20260401T101112Z_uuid_same_workout.jpg"
            modern_file = modern_dir / file_name
            legacy_file = legacy_dir / file_name
            modern_file.write_bytes(b"new-layout")
            legacy_file.write_bytes(b"old-layout")
            os.utime(legacy_file, (1710765276, 1710765276))
            os.utime(modern_file, (1711966272, 1711966272))

            records = BRIDGE._collect_workout_archive_records(media_root, "tester", limit=10)

            self.assertEqual(len(records), 1)
            self.assertIn("/halthy/workouts/tester/", records[0]["local_url"])

    def test_workout_archive_image_url_is_tokenized(self) -> None:
        url = BRIDGE._workout_archive_image_url(
            "tester_1",
            "halthy/workouts/tester_1/20260401T101112Z_uuid.jpg",
            "abc123",
            "2026-04-01T10:11:13Z",
        )
        self.assertIn("/api/halthy/workout_image?", url)
        self.assertIn("username=tester_1", url)
        self.assertIn("token=abc123", url)
        self.assertIn("v=2026-04-01T10%3A11%3A13Z", url)

    def test_workout_archive_file_name_uses_timestamp_and_workout_uuid(self) -> None:
        file_name, workout_fingerprint, workout_timestamp, extension = (
            BRIDGE._workout_archive_file_name(
                metric_key="workout",
                attributes={
                    "measurement_timestamp": "2026-03-28T18:15:12Z",
                    "workout_uuid": "ABCD-1234",
                },
                content_type="image/jpeg",
            )
        )
        expected_fingerprint = "uuid_abcd_1234"

        self.assertEqual(workout_fingerprint, expected_fingerprint)
        self.assertEqual(extension, "jpg")
        self.assertEqual(
            workout_timestamp,
            datetime(2026, 3, 28, 18, 15, 12, tzinfo=timezone.utc),
        )
        self.assertEqual(file_name, f"20260328T181512Z_{expected_fingerprint}.jpg")

    def test_store_workout_archive_file_replaces_files_for_same_workout(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            archive_dir = pathlib.Path(temp_dir)
            old_same_workout_jpg = archive_dir / "20260328T181512Z_uuid_abcd_1234_abc123def4.jpg"
            old_same_workout_png = archive_dir / "20260328T181513Z_uuid_abcd_1234_abc123def4.png"
            old_same_workout_stable_key = archive_dir / "20260328T181519Z_uuid_abcd_1234.jpg"
            old_same_workout_metadata = archive_dir / "20260328T181519Z_uuid_abcd_1234.json"
            other_workout_file = archive_dir / "20260328T181514Z_uuid_other_5678.jpg"
            old_same_workout_jpg.write_bytes(b"old_jpg")
            old_same_workout_png.write_bytes(b"old_png")
            old_same_workout_stable_key.write_bytes(b"old_stable")
            old_same_workout_metadata.write_text("{}", encoding="utf-8")
            other_workout_file.write_bytes(b"other")

            replaced_count = BRIDGE._store_workout_archive_file(
                archive_dir=archive_dir,
                file_name="20260328T181520Z_uuid_abcd_1234.jpg",
                image_bytes=b"new_image",
                workout_fingerprint="uuid_abcd_1234",
            )

            self.assertEqual(replaced_count, 3)
            self.assertFalse(old_same_workout_jpg.exists())
            self.assertFalse(old_same_workout_png.exists())
            self.assertFalse(old_same_workout_stable_key.exists())
            self.assertFalse(old_same_workout_metadata.exists())
            self.assertTrue(other_workout_file.exists())
            self.assertEqual(
                (archive_dir / "20260328T181520Z_uuid_abcd_1234.jpg").read_bytes(),
                b"new_image",
            )

    def test_workout_archive_metadata_is_written_and_collected(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            media_root = pathlib.Path(temp_dir)
            archive_dir = media_root / "halthy" / "workouts" / "tester"
            archive_dir.mkdir(parents=True, exist_ok=True)
            file_name = "20260401T101112Z_uuid_abcd_1234.jpg"
            (archive_dir / file_name).write_bytes(b"image")

            BRIDGE._store_workout_archive_metadata(
                archive_dir,
                file_name,
                {
                    "workout_type": "Walking",
                    "workout_distance_m": 1234.5,
                    "workout_duration_s": 1800,
                    "ignored_route_payload": [{"lat": 1}],
                },
            )

            records = BRIDGE._collect_workout_archive_records(media_root, "tester", limit=10)

            self.assertEqual(records[0]["title"], "Walking")
            self.assertEqual(records[0]["workout_distance_m"], 1234.5)
            self.assertEqual(records[0]["workout_duration_s"], 1800)
            self.assertNotIn("ignored_route_payload", records[0])

    def test_workout_archive_file_name_uses_timestamp_fallback_key(self) -> None:
        file_name, workout_fingerprint, workout_timestamp, extension = (
            BRIDGE._workout_archive_file_name(
                metric_key="workout",
                attributes={
                    "timestamp": "2026-04-04T07:01:02Z",
                    "workout_uuid": "ABCD-1234",
                },
                content_type="image/jpeg",
            )
        )
        expected_fingerprint = "uuid_abcd_1234"

        self.assertEqual(workout_fingerprint, expected_fingerprint)
        self.assertEqual(
            workout_timestamp,
            datetime(2026, 4, 4, 7, 1, 2, tzinfo=timezone.utc),
        )
        self.assertEqual(extension, "jpg")
        self.assertEqual(file_name, f"20260404T070102Z_{expected_fingerprint}.jpg")

    def test_numeric_state_value_accepts_numeric_strings_with_units(self) -> None:
        self.assertEqual(BRIDGE._numeric_state_value("72"), 72.0)
        self.assertEqual(BRIDGE._numeric_state_value("72,5"), 72.5)
        self.assertEqual(BRIDGE._numeric_state_value("72 bpm"), 72.0)
        self.assertEqual(BRIDGE._numeric_state_value("36.5 °C"), 36.5)
        self.assertIsNone(BRIDGE._numeric_state_value("not-a-number"))

    def test_measurement_timestamp_value_uses_fallback_keys(self) -> None:
        attrs = {"timestamp": "2026-04-02T10:11:12Z"}
        self.assertEqual(BRIDGE._measurement_timestamp_value(attrs), "2026-04-02T10:11:12Z")

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

    def test_statistics_candidates_disabled_per_runtime(self) -> None:
        runtime = BRIDGE.IntegrationRuntime(
            configured_username="tester",
            app_username="Tester",
            display_name="Tester",
            statistics_enabled=False,
        )

        candidates = BRIDGE._statistics_candidates_from_sensor(
            runtime=runtime,
            metric_key="heart_rate",
            metric_name="Heart rate",
            state=72,
            unit="bpm",
            attributes={"measurement_timestamp": "2026-06-19T10:15:00Z"},
        )

        self.assertEqual(candidates, [])

    def test_statistics_candidate_name_includes_username(self) -> None:
        runtime = BRIDGE.IntegrationRuntime(
            configured_username="tester_1",
            app_username="Tester 1",
            display_name="Tester One",
        )

        candidates = BRIDGE._statistics_candidates_from_sensor(
            runtime=runtime,
            metric_key="heart_rate",
            metric_name="Heart rate",
            state=72,
            unit="bpm",
            attributes={"measurement_timestamp": "2026-06-19T10:15:00Z"},
        )

        self.assertEqual(candidates[0]["name"], "Heart rate (Tester 1)")
        self.assertEqual(candidates[0]["statistic_id"], "halthy:tester_1_heart_rate")

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
