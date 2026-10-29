"""Migration against Recorder's real queued API and temporary SQLite database."""

import asyncio
from datetime import datetime, timezone
from functools import partial
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, patch

from homeassistant.components.recorder import get_instance
from homeassistant.components.recorder.db_schema import Statistics, StatisticsShortTerm
from homeassistant.components.recorder.statistics import get_metadata
from homeassistant.components.recorder.util import session_scope
from homeassistant.config_entries import ConfigEntries
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.helpers import entity_registry as er, issue_registry as ir
from homeassistant.helpers.recorder import async_initialize_recorder
from homeassistant.setup import async_setup_component
from homeassistant import loader

from custom_components.halthy import counter_unit_migration as migration
from custom_components.halthy.runtime import HalthySensorState, IntegrationRuntime


class CounterUnitMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = TemporaryDirectory(prefix="halthy-counter-migration-")
        self.hass = HomeAssistant(self.directory.name)
        loader.async_setup(self.hass)
        async_initialize_recorder(self.hass)
        self.hass.config_entries = ConfigEntries(self.hass, {})
        self.config_entries = {entry_id: SimpleNamespace(entry_id=entry_id, domain="halthy",
            pref_disable_new_entities=False, subentries={}) for entry_id in ("entry", "other")}
        lookup = patch.object(self.hass.config_entries, "async_get_entry", side_effect=self.config_entries.get)
        lookup.start()
        self.addCleanup(lookup.stop)
        await er.async_load(self.hass)
        await ir.async_load(self.hass)
        self.registry = er.async_get(self.hass)
        self.runtime = IntegrationRuntime(configured_username="tester", app_username="tester", display_name="Tester")
        self.other = IntegrationRuntime(configured_username="other", app_username="other", display_name="Other")
        self.hass.data["halthy"] = {"entries": {"entry": self.runtime, "other": self.other}}
        self.counter = self.add_sensor("handwashing_event", None)
        self.counter = self.registry.async_update_entity(self.counter.entity_id, new_entity_id="sensor.my_custom_counter")
        self.steps = self.add_sensor("steps", "count")
        self.heart = self.add_sensor("heart_rate", "bpm")
        self.other_counter = self.add_sensor("handwashing_event", None, entry_id="other", runtime=self.other)
        self.external = "halthy:tester_handwashing_event"
        self.assertTrue(await async_setup_component(self.hass, "recorder", {
            "recorder": {"db_url": "sqlite:///" + self.directory.name + "/recorder.db", "auto_purge": False}
        }))
        await self.hass.async_start()
        self.recorder = get_instance(self.hass)
        await asyncio.wait_for(self.recorder.async_recorder_ready.wait(), 30)
        for statistic_id, unit, source in (
            (self.counter.entity_id, "count", "recorder"), (self.external, "count", "halthy"),
            (self.steps.entity_id, "count", "recorder"), (self.heart.entity_id, "bpm", "recorder"),
            (self.other_counter.entity_id, "count", "recorder"),
            ("sensor.foreign_counter", "count", "recorder"),
        ):
            self.seed(statistic_id, unit, source)
        await self.recorder.async_block_till_done()
        self.issue_id = f"units_changed_{self.counter.entity_id}"
        self.add_issue(self.issue_id)
        self.add_issue("units_changed_sensor.foreign_counter")

    async def asyncTearDown(self):
        await self.hass.async_stop(force=True)
        self.directory.cleanup()

    def add_sensor(self, key, unit, *, entry_id="entry", runtime=None):
        runtime = runtime or self.runtime
        unique_id = entry_id + "_" + key
        runtime.sensors[unique_id] = HalthySensorState(unique_id=unique_id, metric_key=key,
            name=key, state=4, unit=unit, icon=None, attributes={}, username=runtime.app_username, device_id="phone")
        return self.registry.async_get_or_create("sensor", "halthy", unique_id,
            suggested_object_id=runtime.configured_username + "_" + key,
            config_entry=self.config_entries[entry_id])

    def add_issue(self, issue_id):
        ir.async_create_issue(self.hass, "sensor", issue_id, is_fixable=False,
            severity=ir.IssueSeverity.WARNING, translation_key="units_changed",
            data={"issue_type": "units_changed", "metadata_unit": "count", "state_unit": None})

    def seed(self, statistic_id, unit, source):
        metadata = {"statistic_id": statistic_id, "source": source, "name": None,
                    "unit_of_measurement": unit, "has_mean": True, "has_sum": True}
        sample = {"start": datetime(2026, 10, 28, 10, tzinfo=timezone.utc), "mean": 2.5,
                  "min": 1, "max": 4, "state": 4, "sum": 7}
        for table in (Statistics, StatisticsShortTerm):
            self.recorder.async_import_statistics(metadata, [sample], table)

    async def metadata(self):
        return await self.recorder.async_add_executor_job(partial(get_metadata, self.hass))

    async def values(self):
        def read():
            with session_scope(hass=self.hass, read_only=True) as session:
                return {table.__tablename__: [tuple(row) for row in session.query(
                    table.metadata_id, table.start_ts, table.mean, table.min, table.max, table.state, table.sum
                ).order_by(table.metadata_id)] for table in (Statistics, StatisticsShortTerm)}
        return await self.recorder.async_add_executor_job(read)

    async def test_preview_then_migrate_preserves_every_numeric_row_and_registry_id(self):
        before = await self.values()
        registry_before = list(self.registry.entities)
        expected = sorted([self.counter.entity_id, self.external])
        preview = await migration.async_migrate_counter_statistics(self.hass, "entry", dry_run=True)
        self.assertEqual(preview["statistic_ids"], expected)
        self.assertEqual((await self.metadata())[self.counter.entity_id][1]["unit_of_measurement"], "count")
        self.assertIsNotNone(ir.async_get(self.hass).async_get_issue("sensor", self.issue_id))
        result = await migration.async_migrate_counter_statistics(self.hass, "entry")
        self.assertEqual(result["statistic_ids"], expected)
        self.assertEqual(result["status"], "migrated")
        metadata = await self.metadata()
        for statistic_id in expected:
            self.assertIsNone(metadata[statistic_id][1]["unit_of_measurement"])
        for entity in (self.steps, self.other_counter):
            self.assertEqual(metadata[entity.entity_id][1]["unit_of_measurement"], "count")
        self.assertEqual(metadata[self.heart.entity_id][1]["unit_of_measurement"], "bpm")
        self.assertEqual(metadata["sensor.foreign_counter"][1]["unit_of_measurement"], "count")
        self.assertEqual(await self.values(), before)
        self.assertEqual(list(self.registry.entities), registry_before)
        self.assertIsNone(ir.async_get(self.hass).async_get_issue("sensor", self.issue_id))
        self.assertIsNotNone(ir.async_get(self.hass).async_get_issue("sensor", "units_changed_sensor.foreign_counter"))
        self.assertEqual((await migration.async_migrate_counter_statistics(self.hass, "entry"))["status"], "no_changes")

    async def test_current_api_gets_explicit_unit_class_and_cleans_manually_fixed_repairs(self):
        original = self.recorder.async_update_statistics_metadata
        calls = []

        def modern(statistic_id, *, new_unit_class, new_unit_of_measurement, on_done):
            calls.append((statistic_id, new_unit_class, new_unit_of_measurement))
            original(statistic_id, new_unit_of_measurement=new_unit_of_measurement, on_done=on_done)

        with patch.object(self.recorder, "async_update_statistics_metadata", modern):
            await migration.async_migrate_counter_statistics(self.hass, "entry")
        self.assertEqual(len(calls), 2)
        self.assertTrue(all(unit_class is None and unit is None for _, unit_class, unit in calls))
        self.add_issue(self.issue_id)
        await migration.async_migrate_counter_statistics(self.hass, "entry")
        self.assertIsNone(ir.async_get(self.hass).async_get_issue("sensor", self.issue_id))

    async def test_unexpected_unit_or_source_is_not_overwritten(self):
        self.add_sensor("inhaler_usage", None)
        foreign_id = "halthy:tester_inhaler_usage"
        self.seed(foreign_id, "count", "foreign")
        self.recorder.async_update_statistics_metadata(self.counter.entity_id, new_unit_of_measurement="kg")
        await self.recorder.async_block_till_done()
        before = await self.values()
        await migration.async_migrate_counter_statistics(self.hass, "entry")
        self.assertEqual((await self.metadata())[self.counter.entity_id][1]["unit_of_measurement"], "kg")
        self.assertEqual((await self.metadata())[foreign_id][1]["unit_of_measurement"], "count")
        self.assertIsNotNone(ir.async_get(self.hass).async_get_issue("sensor", self.issue_id))
        self.assertEqual(await self.values(), before)

    async def test_automatic_migration_waits_until_started_without_blocking_setup(self):
        callbacks = []
        entry = SimpleNamespace(entry_id="entry", async_on_unload=lambda fn: None)
        self.hass.set_state(CoreState.starting)
        with patch("homeassistant.helpers.start.async_at_started", side_effect=lambda hass, cb: callbacks.append(cb) or (lambda: None)), \
             patch.object(migration, "async_migrate_counter_statistics", new=AsyncMock()) as migrate:
            await migration.async_migrate_counter_statistics_on_setup(self.hass, entry)
            migrate.assert_not_awaited()
            self.hass.set_state(CoreState.running)
            await callbacks[0](self.hass)
            migrate.assert_awaited_once_with(self.hass, "entry")

    async def test_failed_write_is_not_claimed_as_migrated_or_repair_deleted(self):
        def failed(statistic_id, *, new_unit_of_measurement, on_done):
            on_done()

        with patch.object(self.recorder, "async_update_statistics_metadata", failed):
            with self.assertRaisesRegex(migration.HomeAssistantError, "could not be verified"):
                await migration.async_migrate_counter_statistics(self.hass, "entry")
        self.assertIsNotNone(ir.async_get(self.hass).async_get_issue("sensor", self.issue_id))
        self.assertEqual((await self.metadata())[self.counter.entity_id][1]["unit_of_measurement"], "count")
        self.assertEqual((await migration.async_migrate_counter_statistics(self.hass, "entry"))["status"], "migrated")

    async def test_timeout_keeps_repairs_and_does_not_cancel_recorder_readiness(self):
        self.recorder.async_recorder_ready.clear()
        with patch.object(migration, "_TIMEOUT", 0.01):
            with self.assertRaisesRegex(migration.HomeAssistantError, "timed out"):
                await migration.async_migrate_counter_statistics(self.hass, "entry")
        self.assertIsNotNone(ir.async_get(self.hass).async_get_issue("sensor", self.issue_id))
        self.recorder.async_recorder_ready.set()
        self.assertEqual((await migration.async_migrate_counter_statistics(self.hass, "entry"))["status"], "migrated")

    async def test_old_repair_for_a_different_unit_is_not_dismissed(self):
        self.add_issue(self.issue_id)
        issue = ir.async_get(self.hass).async_get_issue("sensor", self.issue_id)
        issue.data["metadata_unit"] = "kg"
        await migration.async_migrate_counter_statistics(self.hass, "entry")
        self.assertIsNotNone(ir.async_get(self.hass).async_get_issue("sensor", self.issue_id))
