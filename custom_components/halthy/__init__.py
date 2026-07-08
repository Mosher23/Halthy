"""Halthy integration."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
import asyncio
import base64
import binascii
import hmac
import hashlib
import inspect
import json
import logging
import math
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote, unquote
from uuid import uuid4

from aiohttp import web
import voluptuous as vol

from homeassistant.components.http import KEY_HASS, HomeAssistantView
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.helpers import entity_registry as er
from homeassistant.helpers import config_validation as cv
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.event import async_track_time_change, async_track_time_interval
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

try:
    from homeassistant.components.recorder.statistics import async_add_external_statistics
except ImportError:
    async_add_external_statistics = None

try:
    from homeassistant.components.recorder.models.statistics import (
        StatisticData,
        StatisticMeanType,
        StatisticMetaData,
    )
except ImportError:
    try:
        from homeassistant.components.recorder.models import (
            StatisticData,
            StatisticMeanType,
            StatisticMetaData,
        )
    except ImportError:
        StatisticData = None  # type: ignore[assignment]
        StatisticMeanType = None  # type: ignore[assignment]
        StatisticMetaData = None  # type: ignore[assignment]

from .const import (
    ACTIVITY_LOG_MODE_OFF,
    ACTIVITY_LOG_MODE_PER_ENTITY_VERBOSE,
    ACTIVITY_LOG_MODE_SESSION_SUMMARY,
    CONF_APP_USERNAME,
    CONF_ACTIVITY_LOG_MODE,
    CONF_DISPLAY_NAME,
    CONF_OWNER_USER_ID,
    CONF_STATISTICS_ENABLED,
    CONF_TEMPERATURE_UNIT,
    DEFAULT_ACTIVITY_LOG_MODE,
    DEFAULT_STATISTICS_ENABLED,
    DEFAULT_TEMPERATURE_UNIT,
    DOMAIN,
    COMMAND_ACK_ENDPOINT_NAME,
    COMMAND_ACK_ENDPOINT_PATH,
    COMMAND_ENDPOINT_NAME,
    COMMAND_ENDPOINT_PATH,
    WORKOUT_ARCHIVE_ENDPOINT_NAME,
    WORKOUT_ARCHIVE_ENDPOINT_PATH,
    WORKOUT_ARCHIVE_IMAGE_ENDPOINT_NAME,
    WORKOUT_ARCHIVE_IMAGE_ENDPOINT_PATH,
    ENDPOINT_NAME,
    ENDPOINT_PATH,
    PLATFORMS,
    SERVICE_FORCE_UPLOAD,
    SERVICE_FORCE_INFLUX_BACKFILL,
    VALID_ACTIVITY_LOG_MODES,
    VALID_TEMPERATURE_UNITS,
    new_image_signal,
    new_sensor_signal,
    remove_image_signal,
    remove_sensor_signal,
    update_image_signal,
    update_sensor_signal,
)
from .naming import (
    friendly_metric_name,
    is_selection_managed_metric,
    metric_icon,
    normalize_metric_key,
    sanitize_identifier,
)
from .units import canonical_unit, resolve_temperature_state

_LOGGER = logging.getLogger(__name__)

try:
    from homeassistant.components.lovelace.const import LOVELACE_DATA as LOVELACE_DATA_KEY
except Exception:  # noqa: BLE001
    LOVELACE_DATA_KEY = "lovelace"

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}_runtime"
SAVE_DELAY_SECONDS = 5
MAX_SENSORS_PER_PUSH = 256
MAX_IMAGES_PER_PUSH = 16
MAX_REQUEST_BYTES = 512 * 1024
MAX_ATTRIBUTES_BYTES = 64 * 1024
MAX_ROUTE_POINTS = 120
MAX_IMAGE_BYTES = 350 * 1024
WORKOUT_IMAGE_METRIC_KEY = "workout"
MEASUREMENT_TIMESTAMP_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "measurement_timestamp",
    "measured_at",
    "recorded_at",
    "observed_at",
    "sample_timestamp",
    "timestamp",
    "last_pushed",
    "updated_at",
)
WORKOUT_ARCHIVE_TIMESTAMP_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "measurement_timestamp",
    "measured_at",
    "recorded_at",
    "observed_at",
    "sample_timestamp",
    "timestamp",
    "last_pushed",
    "updated_at",
    "workout_end",
    "workout_start",
)
WORKOUT_ARCHIVE_ID_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "workout_uuid",
    "workout_id",
    "uuid",
)
WORKOUT_ARCHIVE_WORKOUT_TYPE_ATTRIBUTE_KEYS: tuple[str, ...] = (
    "workout_type",
    "workout_activity_type",
    "type",
)
WORKOUT_IMAGE_CONTENT_TYPE_EXTENSIONS: dict[str, str] = {
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/png": "png",
    "image/webp": "webp",
    "image/gif": "gif",
    "image/bmp": "bmp",
    "image/tiff": "tiff",
    "image/heic": "heic",
    "image/heif": "heif",
}
WORKOUT_ARCHIVE_FOLDER_DOMAIN_CANDIDATES: tuple[str, ...] = (
    DOMAIN,
    "halthy_bridge",
    "health2ha",
    "health2ha_bridge",
)
WORKOUT_ARCHIVE_IMAGE_SUFFIXES: tuple[str, ...] = (
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".gif",
    ".bmp",
    ".tif",
    ".tiff",
    ".heic",
    ".heif",
    ".avif",
)
WORKOUT_ARCHIVE_METADATA_KEYS: tuple[str, ...] = (
    "title",
    "name",
    "workout_uuid",
    "workout_id",
    "uuid",
    "workout_type",
    "workout_activity_type",
    "activity_type",
    "workout_kind",
    "type",
    "measurement_timestamp",
    "measured_at",
    "recorded_at",
    "observed_at",
    "sample_timestamp",
    "timestamp",
    "last_pushed",
    "updated_at",
    "workout_start",
    "workout_end",
    "end",
    "end_time",
    "start",
    "start_time",
    "workout_distance_m",
    "distance_m",
    "distance",
    "workout_duration_s",
    "duration_s",
    "duration_seconds",
    "duration",
    "workout_active_energy_kcal",
    "active_energy_kcal",
    "energy_kcal",
    "workout_avg_heart_rate_bpm",
    "avg_heart_rate_bpm",
    "lowest_heart_rate_bpm",
    "min_heart_rate_bpm",
    "highest_heart_rate_bpm",
    "max_heart_rate_bpm",
    "avg_speed_mps",
    "workout_avg_speed_mps",
    "average_speed_mps",
    "workout_average_speed_mps",
    "highest_speed_mps",
    "max_speed_mps",
    "lowest_speed_mps",
    "min_speed_mps",
    "cadence_spm",
    "avg_cadence_spm",
    "power_w",
    "avg_power_w",
    "respiratory_rate_brpm",
    "avg_respiratory_rate_brpm",
    "workout_elevation_gain_m",
    "elevation_gain_m",
    "highest_altitude_m",
    "max_altitude_m",
    "lowest_altitude_m",
    "min_altitude_m",
    "total_flights_climbed",
    "workout_total_flights_climbed",
    "flights_climbed",
    "workout_activity_type_raw",
    "point_count",
    "rendered_point_count",
    "detailed_map",
    "map_style",
    "dark_map",
    "weather_condition",
    "weather_condition_raw",
    "weather_temperature_c",
    "weather_humidity_percent",
    "workout_zone_groups",
    "heart_rate_zones",
    "heart_rate_zone_total_duration_s",
    "cycling_power_zones",
    "cycling_power_zone_total_duration_s",
)
WORKOUT_ARCHIVE_DEFAULT_LIST_LIMIT = 240
WORKOUT_ARCHIVE_MAX_LIST_LIMIT = 1000
WORKOUT_CARD_MODULE_FILENAME = "halthy-workout-card.js"
WORKOUT_CARD_STATIC_URL = f"/{DOMAIN}/{WORKOUT_CARD_MODULE_FILENAME}"
LAST_UPDATE_METRIC_KEY = "last_update"
LAST_UPDATE_NAME = "Last update"
LAST_UPDATE_ICON = "mdi:clock-check-outline"
LAST_FULL_SYNC_METRIC_KEY = "last_full_sync"
LAST_FULL_SYNC_NAME = "Last full sync"
LAST_FULL_SYNC_ICON = "mdi:sync"
DAILY_UPLOAD_COUNT_METRIC_KEY = "daily_upload_count"
DAILY_UPLOAD_COUNT_NAME = "Daily uploads"
DAILY_UPLOAD_COUNT_ICON = "mdi:counter"
STATISTICS_SOURCE = "halthy"
FORCE_UPLOAD_COMMAND_TYPE = "force_upload"
FORCE_INFLUX_BACKFILL_COMMAND_TYPE = "force_influx_backfill"
SUPPORTED_COMMAND_TYPES = {
    FORCE_UPLOAD_COMMAND_TYPE,
    FORCE_INFLUX_BACKFILL_COMMAND_TYPE,
}
FORCE_UPLOAD_INTERVAL_DEFAULT_SECONDS = 0
FORCE_UPLOAD_INTERVAL_OPTIONS: tuple[tuple[str, int], ...] = (
    ("Off", 0),
    ("1 minute", 60),
    ("5 minutes", 5 * 60),
    ("10 minutes", 10 * 60),
    ("15 minutes", 15 * 60),
    ("30 minutes", 30 * 60),
    ("1 hour", 60 * 60),
)
FORCE_UPLOAD_INTERVAL_ALLOWED_SECONDS = {
    option_value for _, option_value in FORCE_UPLOAD_INTERVAL_OPTIONS
}
FORCE_UPLOAD_SERVICE_SCHEMA = vol.Schema(
    {
        vol.Optional(CONF_APP_USERNAME): cv.string,
    }
)
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

if StatisticMetaData is not None:
    try:
        _STATISTIC_METADATA_FIELDS = set(inspect.signature(StatisticMetaData).parameters.keys())
    except (TypeError, ValueError):
        _STATISTIC_METADATA_FIELDS = set()
else:
    _STATISTIC_METADATA_FIELDS = set()

if StatisticData is not None:
    try:
        _STATISTIC_DATA_FIELDS = set(inspect.signature(StatisticData).parameters.keys())
    except (TypeError, ValueError):
        _STATISTIC_DATA_FIELDS = set()
else:
    _STATISTIC_DATA_FIELDS = set()


def _metadata_statistic_id(metadata: Any) -> str | None:
    if isinstance(metadata, dict):
        raw = metadata.get("statistic_id")
        return str(raw).strip() if raw is not None else None
    raw = getattr(metadata, "statistic_id", None)
    if raw is None:
        return None
    value = str(raw).strip()
    return value or None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _current_local_day_key(hass: HomeAssistant) -> str:
    return dt_util.now().date().isoformat()


def _normalize_day_key(raw_value: Any) -> str:
    if not isinstance(raw_value, str):
        return ""
    candidate = raw_value.strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return ""
    return candidate


def _coerce_daily_upload_count(raw_value: Any) -> int:
    if isinstance(raw_value, bool):
        return 0
    if isinstance(raw_value, int):
        return max(raw_value, 0)
    if isinstance(raw_value, float):
        if not math.isfinite(raw_value):
            return 0
        return max(int(raw_value), 0)
    if isinstance(raw_value, str):
        stripped = raw_value.strip()
        if stripped.isdigit():
            return max(int(stripped), 0)
    return 0


def force_upload_interval_label(seconds: int) -> str:
    normalized_seconds = _coerce_force_upload_interval_seconds(seconds)
    for label, option_seconds in FORCE_UPLOAD_INTERVAL_OPTIONS:
        if option_seconds == normalized_seconds:
            return label
    return FORCE_UPLOAD_INTERVAL_OPTIONS[0][0]


def force_upload_interval_seconds_from_label(label: str) -> int:
    normalized_label = label.strip().lower()
    for option_label, option_seconds in FORCE_UPLOAD_INTERVAL_OPTIONS:
        if option_label.lower() == normalized_label:
            return option_seconds
    return FORCE_UPLOAD_INTERVAL_DEFAULT_SECONDS


def _coerce_force_upload_interval_seconds(raw_value: Any) -> int:
    value: int | None = None
    if isinstance(raw_value, bool):
        value = None
    elif isinstance(raw_value, int):
        value = raw_value
    elif isinstance(raw_value, float):
        if math.isfinite(raw_value):
            value = int(raw_value)
    elif isinstance(raw_value, str):
        stripped = raw_value.strip()
        if stripped:
            if stripped.isdigit():
                value = int(stripped)
            else:
                value = force_upload_interval_seconds_from_label(stripped)
    if value is None:
        return FORCE_UPLOAD_INTERVAL_DEFAULT_SECONDS
    if value not in FORCE_UPLOAD_INTERVAL_ALLOWED_SECONDS:
        return FORCE_UPLOAD_INTERVAL_DEFAULT_SECONDS
    return value


def _coerce_activity_log_mode(raw_value: Any) -> str:
    if isinstance(raw_value, str):
        normalized = raw_value.strip().lower()
        if normalized in VALID_ACTIVITY_LOG_MODES:
            return normalized
    return DEFAULT_ACTIVITY_LOG_MODE


def _normalize_pending_force_upload_command(raw_value: Any) -> dict[str, Any] | None:
    if not isinstance(raw_value, dict):
        return None

    command_id = str(raw_value.get("id", "")).strip()
    command_type = str(raw_value.get("type", "")).strip().lower()
    requested_at_raw = str(raw_value.get("requested_at", "")).strip()
    requested_at = _parse_measurement_timestamp(requested_at_raw)
    if not command_id or command_type not in SUPPORTED_COMMAND_TYPES or requested_at is None:
        return None

    normalized: dict[str, Any] = {
        "id": command_id,
        "type": command_type,
        "requested_at": requested_at.isoformat(),
    }
    requested_by_user_id = str(raw_value.get("requested_by_user_id", "")).strip()
    if requested_by_user_id:
        normalized["requested_by_user_id"] = requested_by_user_id

    delivered_at_raw = raw_value.get("delivered_at")
    if delivered_at_raw is not None:
        delivered_at = _parse_measurement_timestamp(str(delivered_at_raw))
        if delivered_at is not None:
            normalized["delivered_at"] = delivered_at.isoformat()
    return normalized


@dataclass(slots=True)
class HalthySensorState:
    """In-memory state for one metric-backed sensor."""

    unique_id: str
    metric_key: str
    name: str
    state: str | float | int | bool
    unit: str | None
    icon: str | None
    attributes: dict[str, Any]
    username: str
    device_id: str
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class HalthyImageState:
    """In-memory state for one metric-backed image entity."""

    unique_id: str
    metric_key: str
    name: str
    content_type: str
    image_bytes: bytes
    attributes: dict[str, Any]
    username: str
    device_id: str
    updated_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass(slots=True)
class IntegrationRuntime:
    """Runtime data shared between endpoint and sensor platform."""

    configured_username: str
    app_username: str
    display_name: str
    owner_user_id: str | None = None
    temperature_unit_preference: str = DEFAULT_TEMPERATURE_UNIT
    activity_log_mode: str = DEFAULT_ACTIVITY_LOG_MODE
    statistics_enabled: bool = DEFAULT_STATISTICS_ENABLED
    sensors: dict[str, HalthySensorState] = field(default_factory=dict)
    images: dict[str, HalthyImageState] = field(default_factory=dict)
    statistics_cursors: dict[str, str] = field(default_factory=dict)
    force_upload_interval_seconds: int = FORCE_UPLOAD_INTERVAL_DEFAULT_SECONDS
    pending_force_upload_command: dict[str, Any] | None = None
    last_force_upload_ack_at: str | None = None
    last_force_upload_ack_status: str | None = None
    daily_upload_count: int = 0
    daily_upload_count_day: str = ""
    workout_archive_access_token: str = field(default_factory=lambda: uuid4().hex)
    lock: asyncio.Lock | None = None


def _runtime_lock(runtime: IntegrationRuntime) -> asyncio.Lock:
    """Create the runtime lock lazily inside the async context that needs it."""

    if runtime.lock is None:
        runtime.lock = asyncio.Lock()
    return runtime.lock


@dataclass(slots=True)
class StatisticsCursorUpdate:
    """Cursor update candidate for one statistics series."""

    latest_imported_at: datetime
    legacy_statistic_ids: tuple[str, ...] = ()


def _sanitize(value: str) -> str:
    return sanitize_identifier(value)


def _unique_sensor_id(username: str, device_id: str, metric_key: str) -> str:
    user = _sanitize(username)
    device = _sanitize(device_id)
    metric = _sanitize(metric_key)
    material = f"{user}:{device}:{metric}".encode()
    digest = hashlib.sha1(material, usedforsecurity=False).hexdigest()[:10]
    return f"{DOMAIN}_{user}_{device}_{metric}_{digest}"


def _unique_image_id(username: str, device_id: str, metric_key: str) -> str:
    user = _sanitize(username)
    device = _sanitize(device_id)
    metric = _sanitize(metric_key)
    material = f"{user}:{device}:{metric}:image".encode()
    digest = hashlib.sha1(material, usedforsecurity=False).hexdigest()[:10]
    return f"{DOMAIN}_{user}_{device}_{metric}_image_{digest}"


def _build_metric_lookup(runtime: IntegrationRuntime) -> dict[str, list[str]]:
    """Build a per-runtime metric lookup keyed by normalized/compact metric key."""
    lookup: dict[str, list[str]] = {}
    for unique_id, state in runtime.sensors.items():
        metric_key = _normalize_metric_key(state.metric_key)
        lookup.setdefault(metric_key, []).append(unique_id)
        compact = metric_key.replace("_", "")
        if compact != metric_key:
            lookup.setdefault(compact, []).append(unique_id)
    return lookup


def _build_image_metric_lookup(runtime: IntegrationRuntime) -> dict[str, list[str]]:
    """Build a per-runtime metric lookup for images."""
    lookup: dict[str, list[str]] = {}
    for unique_id, state in runtime.images.items():
        metric_key = _normalize_metric_key(state.metric_key)
        lookup.setdefault(metric_key, []).append(unique_id)
        compact = metric_key.replace("_", "")
        if compact != metric_key:
            lookup.setdefault(compact, []).append(unique_id)
    return lookup


def _matching_metric_unique_ids(
    runtime: IntegrationRuntime, metric_key: str, lookup: dict[str, list[str]]
) -> list[str]:
    """Return matching sensor ids for the metric using pre-built lookup."""
    normalized_metric = _normalize_metric_key(metric_key)
    compact_metric = normalized_metric.replace("_", "")
    unique_ids = set(lookup.get(normalized_metric, [])) | set(lookup.get(compact_metric, []))
    matches = [runtime.sensors[unique_id] for unique_id in unique_ids if unique_id in runtime.sensors]
    matches.sort(key=lambda item: item.updated_at, reverse=True)
    return [item.unique_id for item in matches]


def _matching_image_unique_ids(
    runtime: IntegrationRuntime, metric_key: str, lookup: dict[str, list[str]]
) -> list[str]:
    """Return matching image ids for the metric using pre-built lookup."""
    normalized_metric = _normalize_metric_key(metric_key)
    compact_metric = normalized_metric.replace("_", "")
    unique_ids = set(lookup.get(normalized_metric, [])) | set(lookup.get(compact_metric, []))
    matches = [runtime.images[unique_id] for unique_id in unique_ids if unique_id in runtime.images]
    matches.sort(key=lambda item: item.updated_at, reverse=True)
    return [item.unique_id for item in matches]


def _normalize_metric_key(metric_key: str) -> str:
    return normalize_metric_key(metric_key)


def _friendly_metric_name(metric_key: str, provided_name: str | None) -> str:
    return friendly_metric_name(metric_key, provided_name)


def _metric_icon(metric_key: str, provided_icon: str | None) -> str:
    return metric_icon(metric_key, provided_icon)


def _canonical_unit(metric_key: str, provided_unit: Any) -> str | None:
    return canonical_unit(metric_key, provided_unit)


def _resolve_temperature_state(
    metric_key: str,
    state: str | float | int | bool,
    unit: str | None,
    preference: str,
    hass_temperature_unit: str,
) -> tuple[str | float | int | bool, str | None]:
    return resolve_temperature_state(
        metric_key=metric_key,
        state=state,
        unit=unit,
        preference=preference,
        hass_temperature_unit=hass_temperature_unit,
    )


def _upsert_last_update_sensor(
    hass: HomeAssistant,
    runtime: IntegrationRuntime,
    entry_id: str,
    metric_lookup: dict[str, list[str]],
    source_device_id: str,
    updated_at: datetime,
) -> None:
    """Create or refresh the diagnostic last-update sensor for the entry."""
    timestamp_value = updated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    attributes = {
        "measurement_timestamp": timestamp_value,
        "source_device_id": source_device_id,
        "diagnostic": True,
    }

    matching_unique_ids = _matching_metric_unique_ids(runtime, LAST_UPDATE_METRIC_KEY, metric_lookup)
    if matching_unique_ids:
        for unique_id in matching_unique_ids:
            existing_state = runtime.sensors.get(unique_id)
            state_device_id = existing_state.device_id if existing_state is not None else "diagnostic"
            runtime.sensors[unique_id] = HalthySensorState(
                unique_id=unique_id,
                metric_key=LAST_UPDATE_METRIC_KEY,
                name=LAST_UPDATE_NAME,
                state=timestamp_value,
                unit=None,
                icon=LAST_UPDATE_ICON,
                attributes=attributes,
                username=runtime.app_username,
                device_id=state_device_id,
            )
            async_dispatcher_send(hass, update_sensor_signal(entry_id, unique_id))
        return

    unique_id = _unique_sensor_id(runtime.configured_username, "diagnostic", LAST_UPDATE_METRIC_KEY)
    runtime.sensors[unique_id] = HalthySensorState(
        unique_id=unique_id,
        metric_key=LAST_UPDATE_METRIC_KEY,
        name=LAST_UPDATE_NAME,
        state=timestamp_value,
        unit=None,
        icon=LAST_UPDATE_ICON,
        attributes=attributes,
        username=runtime.app_username,
        device_id="diagnostic",
    )
    metric_lookup.setdefault(LAST_UPDATE_METRIC_KEY, []).append(unique_id)
    compact_metric = LAST_UPDATE_METRIC_KEY.replace("_", "")
    if compact_metric != LAST_UPDATE_METRIC_KEY:
        metric_lookup.setdefault(compact_metric, []).append(unique_id)
    async_dispatcher_send(hass, new_sensor_signal(entry_id), unique_id)
    async_dispatcher_send(hass, update_sensor_signal(entry_id, unique_id))


def _upsert_last_full_sync_sensor(
    hass: HomeAssistant,
    runtime: IntegrationRuntime,
    entry_id: str,
    metric_lookup: dict[str, list[str]],
    source_device_id: str,
    updated_at: datetime,
) -> None:
    """Create or refresh the diagnostic last-full-sync sensor for the entry."""
    timestamp_value = updated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    attributes = {
        "measurement_timestamp": timestamp_value,
        "source_device_id": source_device_id,
        "diagnostic": True,
    }

    matching_unique_ids = _matching_metric_unique_ids(runtime, LAST_FULL_SYNC_METRIC_KEY, metric_lookup)
    if matching_unique_ids:
        for unique_id in matching_unique_ids:
            existing_state = runtime.sensors.get(unique_id)
            state_device_id = existing_state.device_id if existing_state is not None else "diagnostic"
            runtime.sensors[unique_id] = HalthySensorState(
                unique_id=unique_id,
                metric_key=LAST_FULL_SYNC_METRIC_KEY,
                name=LAST_FULL_SYNC_NAME,
                state=timestamp_value,
                unit=None,
                icon=LAST_FULL_SYNC_ICON,
                attributes=attributes,
                username=runtime.app_username,
                device_id=state_device_id,
            )
            async_dispatcher_send(hass, update_sensor_signal(entry_id, unique_id))
        return

    unique_id = _unique_sensor_id(runtime.configured_username, "diagnostic", LAST_FULL_SYNC_METRIC_KEY)
    runtime.sensors[unique_id] = HalthySensorState(
        unique_id=unique_id,
        metric_key=LAST_FULL_SYNC_METRIC_KEY,
        name=LAST_FULL_SYNC_NAME,
        state=timestamp_value,
        unit=None,
        icon=LAST_FULL_SYNC_ICON,
        attributes=attributes,
        username=runtime.app_username,
        device_id="diagnostic",
    )
    metric_lookup.setdefault(LAST_FULL_SYNC_METRIC_KEY, []).append(unique_id)
    compact_metric = LAST_FULL_SYNC_METRIC_KEY.replace("_", "")
    if compact_metric != LAST_FULL_SYNC_METRIC_KEY:
        metric_lookup.setdefault(compact_metric, []).append(unique_id)
    async_dispatcher_send(hass, new_sensor_signal(entry_id), unique_id)
    async_dispatcher_send(hass, update_sensor_signal(entry_id, unique_id))


def _upsert_daily_upload_count_sensor(
    hass: HomeAssistant,
    runtime: IntegrationRuntime,
    entry_id: str,
    metric_lookup: dict[str, list[str]],
    source_device_id: str,
    updated_at: datetime,
) -> None:
    timestamp_value = updated_at.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    current_day = _current_local_day_key(hass)
    count_value = max(int(runtime.daily_upload_count), 0)
    attributes = {
        "measurement_timestamp": timestamp_value,
        "source_device_id": source_device_id,
        "day": current_day,
        "diagnostic": True,
    }

    matching_unique_ids = _matching_metric_unique_ids(
        runtime,
        DAILY_UPLOAD_COUNT_METRIC_KEY,
        metric_lookup,
    )
    if matching_unique_ids:
        for unique_id in matching_unique_ids:
            existing_state = runtime.sensors.get(unique_id)
            state_device_id = existing_state.device_id if existing_state is not None else "diagnostic"
            runtime.sensors[unique_id] = HalthySensorState(
                unique_id=unique_id,
                metric_key=DAILY_UPLOAD_COUNT_METRIC_KEY,
                name=DAILY_UPLOAD_COUNT_NAME,
                state=count_value,
                unit=None,
                icon=DAILY_UPLOAD_COUNT_ICON,
                attributes=attributes,
                username=runtime.app_username,
                device_id=state_device_id,
            )
            async_dispatcher_send(hass, update_sensor_signal(entry_id, unique_id))
        return

    unique_id = _unique_sensor_id(
        runtime.configured_username,
        "diagnostic",
        DAILY_UPLOAD_COUNT_METRIC_KEY,
    )
    runtime.sensors[unique_id] = HalthySensorState(
        unique_id=unique_id,
        metric_key=DAILY_UPLOAD_COUNT_METRIC_KEY,
        name=DAILY_UPLOAD_COUNT_NAME,
        state=count_value,
        unit=None,
        icon=DAILY_UPLOAD_COUNT_ICON,
        attributes=attributes,
        username=runtime.app_username,
        device_id="diagnostic",
    )
    metric_lookup.setdefault(DAILY_UPLOAD_COUNT_METRIC_KEY, []).append(unique_id)
    compact_metric = DAILY_UPLOAD_COUNT_METRIC_KEY.replace("_", "")
    if compact_metric != DAILY_UPLOAD_COUNT_METRIC_KEY:
        metric_lookup.setdefault(compact_metric, []).append(unique_id)
    async_dispatcher_send(hass, new_sensor_signal(entry_id), unique_id)
    async_dispatcher_send(hass, update_sensor_signal(entry_id, unique_id))


def _increment_daily_upload_counter(
    hass: HomeAssistant,
    runtime: IntegrationRuntime,
    entry_id: str,
    source_device_id: str,
    updated_at: datetime,
) -> None:
    current_day = _current_local_day_key(hass)
    if runtime.daily_upload_count_day != current_day:
        runtime.daily_upload_count_day = current_day
        runtime.daily_upload_count = 0
    runtime.daily_upload_count += 1
    metric_lookup = _build_metric_lookup(runtime)
    _upsert_daily_upload_count_sensor(
        hass=hass,
        runtime=runtime,
        entry_id=entry_id,
        metric_lookup=metric_lookup,
        source_device_id=source_device_id,
        updated_at=updated_at,
    )


def _reset_daily_upload_counter_if_needed(
    hass: HomeAssistant,
    runtime: IntegrationRuntime,
    entry_id: str,
) -> bool:
    current_day = _current_local_day_key(hass)
    if runtime.daily_upload_count_day == current_day and runtime.daily_upload_count == 0:
        return False
    if runtime.daily_upload_count_day == current_day:
        return False

    runtime.daily_upload_count_day = current_day
    runtime.daily_upload_count = 0
    metric_lookup = _build_metric_lookup(runtime)
    _upsert_daily_upload_count_sensor(
        hass=hass,
        runtime=runtime,
        entry_id=entry_id,
        metric_lookup=metric_lookup,
        source_device_id="diagnostic",
        updated_at=datetime.now(timezone.utc),
    )
    return True


def _coerce_state(value: Any) -> str | float | int | bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        normalized = value.strip()
        if not normalized:
            return value

        lowered = normalized.lower()
        if lowered == "true":
            return True
        if lowered == "false":
            return False

        # Accept both "." and "," decimal separators from app payloads/locales.
        numeric = normalized.replace(",", ".")
        if re.fullmatch(r"[+-]?\d+", numeric):
            try:
                return int(numeric)
            except ValueError:
                return value
        if re.fullmatch(r"[+-]?(\d+(\.\d+)?|\.\d+)", numeric):
            try:
                return float(numeric)
            except ValueError:
                return value
        return value
    return str(value)


def _json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_safe(val) for key, val in value.items()}
    if isinstance(value, list):
        return [_json_safe(item) for item in value]
    return str(value)


def _normalize_attributes(raw: dict[str, Any]) -> dict[str, Any]:
    normalized = _json_safe(raw)
    if not isinstance(normalized, dict):
        return {}

    route_points = normalized.get("route_points")
    if isinstance(route_points, list) and len(route_points) > MAX_ROUTE_POINTS:
        normalized["route_points"] = route_points[:MAX_ROUTE_POINTS]
    return normalized


def _attributes_within_size_limit(attributes: dict[str, Any]) -> bool:
    try:
        encoded = json.dumps(attributes, separators=(",", ":"), ensure_ascii=False)
    except (TypeError, ValueError):
        return False
    return len(encoded.encode("utf-8")) <= MAX_ATTRIBUTES_BYTES


def _measurement_timestamp_value(attributes: dict[str, Any]) -> str | None:
    for key in MEASUREMENT_TIMESTAMP_ATTRIBUTE_KEYS:
        raw_value = attributes.get(key)
        if isinstance(raw_value, str):
            value = raw_value.strip()
            if value:
                return value
            continue
        if isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            return str(raw_value)
    return None


def _parse_measurement_timestamp(raw_value: str | None) -> datetime | None:
    if raw_value is None:
        return None
    value = raw_value.strip()
    if not value:
        return None

    numeric = value.replace(",", ".")
    if re.fullmatch(r"[+-]?(\d+(\.\d+)?|\.\d+)", numeric):
        try:
            timestamp = float(numeric)
            return datetime.fromtimestamp(timestamp, tz=timezone.utc)
        except (OverflowError, ValueError):
            return None

    normalized = value
    if normalized.endswith("Z"):
        normalized = f"{normalized[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _first_nonempty_attribute_value(attributes: dict[str, Any], keys: tuple[str, ...]) -> str | None:
    for key in keys:
        raw_value = attributes.get(key)
        if raw_value is None:
            continue
        value = str(raw_value).strip()
        if value:
            return value
    return None


def _workout_archive_timestamp(attributes: dict[str, Any]) -> datetime:
    for key in WORKOUT_ARCHIVE_TIMESTAMP_ATTRIBUTE_KEYS:
        raw_value = attributes.get(key)
        parsed = None
        if isinstance(raw_value, str):
            parsed = _parse_measurement_timestamp(raw_value.strip())
        elif isinstance(raw_value, (int, float)) and not isinstance(raw_value, bool):
            parsed = _parse_measurement_timestamp(str(raw_value))
        if parsed is not None:
            return parsed
    return datetime.now(timezone.utc)


def _image_extension_from_content_type(content_type: str) -> str:
    normalized = content_type.split(";", 1)[0].strip().lower()
    extension = WORKOUT_IMAGE_CONTENT_TYPE_EXTENSIONS.get(normalized)
    if extension:
        return extension

    if "/" not in normalized:
        return "img"
    candidate = sanitize_identifier(normalized.split("/", 1)[1]).replace("_", "")
    if candidate:
        return candidate[:10]
    return "img"


def _workout_archive_fingerprint(
    metric_key: str,
    attributes: dict[str, Any],
    workout_timestamp: datetime,
) -> str:
    raw_workout_id = _first_nonempty_attribute_value(attributes, WORKOUT_ARCHIVE_ID_ATTRIBUTE_KEYS)
    workout_start = _first_nonempty_attribute_value(attributes, ("workout_start",))
    workout_end = _first_nonempty_attribute_value(attributes, ("workout_end",))
    workout_type = _first_nonempty_attribute_value(attributes, WORKOUT_ARCHIVE_WORKOUT_TYPE_ATTRIBUTE_KEYS)
    archive_timestamp = _first_nonempty_attribute_value(
        attributes,
        WORKOUT_ARCHIVE_TIMESTAMP_ATTRIBUTE_KEYS,
    )
    if raw_workout_id is not None:
        sanitized_workout_id = sanitize_identifier(raw_workout_id)[:64]
        if sanitized_workout_id:
            return f"uuid_{sanitized_workout_id}"

    signature_source = "|".join(
        part
        for part in (
            _normalize_metric_key(metric_key),
            workout_start,
            workout_end,
            workout_type,
            archive_timestamp,
        )
        if part
    )
    if not signature_source:
        signature_source = f"{_normalize_metric_key(metric_key)}|{uuid4()}"
    digest = hashlib.sha1(signature_source.encode(), usedforsecurity=False).hexdigest()[:16]
    return f"sig_{digest}"


def _workout_archive_file_name(
    metric_key: str,
    attributes: dict[str, Any],
    content_type: str,
) -> tuple[str, str, datetime, str]:
    workout_timestamp = _workout_archive_timestamp(attributes).astimezone(timezone.utc)
    timestamp_fragment = workout_timestamp.strftime("%Y%m%dT%H%M%SZ")
    workout_fingerprint = _workout_archive_fingerprint(metric_key, attributes, workout_timestamp)
    extension = _image_extension_from_content_type(content_type)
    file_name = f"{timestamp_fragment}_{workout_fingerprint}.{extension}"
    return file_name, workout_fingerprint, workout_timestamp, extension


def _workout_archive_metadata_path(image_path: Path) -> Path:
    return image_path.with_suffix(".json")


def _workout_archive_metadata_value(value: Any) -> Any:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)) and math.isfinite(float(value)):
        return value
    if isinstance(value, list):
        cleaned_list = [
            cleaned
            for item in value
            if (cleaned := _workout_archive_metadata_value(item)) is not None
        ]
        return cleaned_list
    if isinstance(value, dict):
        cleaned_dict: dict[str, Any] = {}
        for key, item in value.items():
            cleaned = _workout_archive_metadata_value(item)
            if cleaned is not None:
                cleaned_dict[str(key)] = cleaned
        return cleaned_dict
    return None


def _workout_archive_metadata_from_attributes(attributes: dict[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in WORKOUT_ARCHIVE_METADATA_KEYS:
        if key not in attributes:
            continue
        value = _workout_archive_metadata_value(attributes[key])
        if value is None or value == "" or value == [] or value == {}:
            continue
        metadata[key] = value
    return metadata


def _store_workout_archive_metadata(
    archive_dir: Path,
    file_name: str,
    attributes: dict[str, Any],
) -> None:
    metadata = _workout_archive_metadata_from_attributes(attributes)
    metadata_path = _workout_archive_metadata_path(archive_dir / file_name)
    if not metadata:
        try:
            metadata_path.unlink()
        except FileNotFoundError:
            pass
        except OSError:
            _LOGGER.debug("Failed to remove empty workout archive metadata: %s", metadata_path)
        return

    temp_path = metadata_path.with_name(f".{metadata_path.name}.tmp")
    with temp_path.open("w", encoding="utf-8") as handle:
        json.dump(metadata, handle, ensure_ascii=False, sort_keys=True)
    temp_path.replace(metadata_path)


def _read_workout_archive_metadata(image_path: Path) -> dict[str, Any]:
    metadata_path = _workout_archive_metadata_path(image_path)
    try:
        with metadata_path.open("r", encoding="utf-8") as handle:
            payload = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, dict):
        return {}
    metadata: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, str):
            metadata[str(key)] = value
            continue
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            metadata[str(key)] = value
            continue
        if isinstance(value, (list, dict)):
            cleaned = _workout_archive_metadata_value(value)
            if cleaned is not None:
                metadata[str(key)] = cleaned
    return metadata


def _workout_archive_record_identity(
    file_path: Path,
    metadata: dict[str, Any],
) -> str:
    raw_workout_id = _first_nonempty_attribute_value(
        metadata,
        WORKOUT_ARCHIVE_ID_ATTRIBUTE_KEYS,
    )
    if raw_workout_id is not None:
        normalized_workout_id = sanitize_identifier(raw_workout_id)
        if normalized_workout_id:
            return f"uuid:{normalized_workout_id}"

    file_stem_parts = file_path.stem.split("_", 1)
    if len(file_stem_parts) == 2:
        fingerprint = file_stem_parts[1].strip().lower()
        if fingerprint.startswith(("uuid_", "sig_")):
            return f"fingerprint:{fingerprint}"
    return ""


def _store_workout_archive_file(
    archive_dir: Path,
    file_name: str,
    image_bytes: bytes,
    workout_fingerprint: str,
) -> int:
    archive_dir.mkdir(parents=True, exist_ok=True)
    target_path = archive_dir / file_name
    replaced_count = 0
    for existing in archive_dir.iterdir():
        if (
            not existing.is_file()
            or existing.name == file_name
            or existing.suffix.lower() not in WORKOUT_ARCHIVE_IMAGE_SUFFIXES
        ):
            continue
        existing_fingerprint = existing.stem.split("_", 1)[1] if "_" in existing.stem else ""
        same_fingerprint = existing_fingerprint == workout_fingerprint
        legacy_uuid_variant = (
            workout_fingerprint.startswith("uuid_")
            and existing_fingerprint.startswith(f"{workout_fingerprint}_")
        )
        if not same_fingerprint and not legacy_uuid_variant:
            continue
        try:
            existing.unlink()
            try:
                _workout_archive_metadata_path(existing).unlink()
            except FileNotFoundError:
                pass
            except OSError:
                _LOGGER.debug("Failed to remove older workout archive metadata: %s", existing)
            replaced_count += 1
        except OSError:
            _LOGGER.debug("Failed to remove older workout archive file: %s", existing)

    temp_path = target_path.with_name(f".{target_path.name}.tmp")
    with temp_path.open("wb") as handle:
        handle.write(image_bytes)
    temp_path.replace(target_path)
    return replaced_count


async def _async_archive_workout_image(
    hass: HomeAssistant,
    username: str,
    metric_key: str,
    content_type: str,
    image_bytes: bytes,
    attributes: dict[str, Any],
) -> dict[str, Any]:
    if _normalize_metric_key(metric_key) != WORKOUT_IMAGE_METRIC_KEY:
        return attributes

    file_name, workout_fingerprint, workout_timestamp, _extension = _workout_archive_file_name(
        metric_key=metric_key,
        attributes=attributes,
        content_type=content_type,
    )
    sanitized_username = sanitize_identifier(username)
    relative_path = f"{DOMAIN}/workouts/{sanitized_username}/{file_name}"
    archive_dir = Path(hass.config.path("media")) / DOMAIN / "workouts" / sanitized_username

    try:
        replaced_count = await hass.async_add_executor_job(
            _store_workout_archive_file,
            archive_dir,
            file_name,
            image_bytes,
            workout_fingerprint,
        )
        await hass.async_add_executor_job(
            _store_workout_archive_metadata,
            archive_dir,
            file_name,
            attributes,
        )
    except Exception as err:  # noqa: BLE001
        _LOGGER.warning(
            "Failed to archive workout image for '%s' (%s): %s",
            username,
            metric_key,
            err,
        )
        return attributes

    archived_attributes = dict(attributes)
    archived_attributes["archive_file_name"] = file_name
    archived_attributes["archive_relative_path"] = relative_path
    archived_attributes["archive_local_url"] = f"/media/local/{relative_path}"
    archived_attributes["archive_media_source_id"] = (
        f"media-source://media_source/local/{relative_path}"
    )
    archived_attributes["archive_replaced_file_count"] = replaced_count
    archived_attributes["archive_workout_fingerprint"] = workout_fingerprint
    archived_attributes["archive_workout_timestamp"] = (
        workout_timestamp.isoformat().replace("+00:00", "Z")
    )
    return archived_attributes


def _coerce_workout_archive_limit(raw_limit: Any) -> int:
    if isinstance(raw_limit, str):
        raw_limit = raw_limit.strip()
        if not raw_limit:
            return WORKOUT_ARCHIVE_DEFAULT_LIST_LIMIT
    if not isinstance(raw_limit, (int, str)):
        return WORKOUT_ARCHIVE_DEFAULT_LIST_LIMIT
    try:
        value = int(raw_limit)
    except (TypeError, ValueError):
        return WORKOUT_ARCHIVE_DEFAULT_LIST_LIMIT
    if value < 1:
        return 1
    if value > WORKOUT_ARCHIVE_MAX_LIST_LIMIT:
        return WORKOUT_ARCHIVE_MAX_LIST_LIMIT
    return value


def _safe_utc_datetime(
    year: int,
    month: int,
    day: int,
    hour: int = 0,
    minute: int = 0,
    second: int = 0,
) -> datetime | None:
    try:
        return datetime(year, month, day, hour, minute, second, tzinfo=timezone.utc)
    except ValueError:
        return None


def _workout_archive_timestamp_from_file_name(file_name: str) -> datetime | None:
    source = file_name.strip()
    if not source:
        return None

    compact_match = re.search(r"(\d{8})T(\d{6})Z?", source, flags=re.IGNORECASE)
    if compact_match:
        date_token = compact_match.group(1)
        time_token = compact_match.group(2)
        parsed = _safe_utc_datetime(
            int(date_token[0:4]),
            int(date_token[4:6]),
            int(date_token[6:8]),
            int(time_token[0:2]),
            int(time_token[2:4]),
            int(time_token[4:6]),
        )
        if parsed is not None:
            return parsed

    separated_match = re.search(
        r"(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})[T _-]?(\d{2})[:._-]?(\d{2})(?:[:._-]?(\d{2}))?",
        source,
    )
    if separated_match:
        parsed = _safe_utc_datetime(
            int(separated_match.group(1)),
            int(separated_match.group(2)),
            int(separated_match.group(3)),
            int(separated_match.group(4)),
            int(separated_match.group(5)),
            int(separated_match.group(6) or "0"),
        )
        if parsed is not None:
            return parsed

    date_only_match = re.search(r"(\d{4})[-_.]?(\d{2})[-_.]?(\d{2})", source)
    if date_only_match:
        return _safe_utc_datetime(
            int(date_only_match.group(1)),
            int(date_only_match.group(2)),
            int(date_only_match.group(3)),
        )

    return None


def _is_supported_workout_archive_file(path: Path) -> bool:
    suffix = path.suffix.lower()
    return suffix in WORKOUT_ARCHIVE_IMAGE_SUFFIXES


def _collect_workout_archive_records(
    media_root: Path,
    username: str,
    limit: int,
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    seen_relative_paths: set[str] = set()

    for archive_domain in WORKOUT_ARCHIVE_FOLDER_DOMAIN_CANDIDATES:
        archive_dir = media_root / archive_domain / "workouts" / username
        if not archive_dir.exists() or not archive_dir.is_dir():
            continue
        try:
            iterator = archive_dir.rglob("*")
        except OSError:
            continue

        for file_path in iterator:
            try:
                if not file_path.is_file() or not _is_supported_workout_archive_file(file_path):
                    continue
                relative_path = file_path.relative_to(media_root).as_posix()
            except (OSError, ValueError):
                continue
            if relative_path in seen_relative_paths:
                continue
            seen_relative_paths.add(relative_path)

            try:
                stat = file_path.stat()
                modified_at = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc)
            except OSError:
                modified_at = datetime.now(timezone.utc)

            timestamp_from_name = _workout_archive_timestamp_from_file_name(file_path.name)
            workout_timestamp = timestamp_from_name or modified_at
            encoded_relative_path = quote(relative_path, safe="/")
            metadata = _read_workout_archive_metadata(file_path)
            workout_identity = _workout_archive_record_identity(file_path, metadata)
            title = _first_nonempty_attribute_value(
                metadata,
                (*WORKOUT_ARCHIVE_WORKOUT_TYPE_ATTRIBUTE_KEYS, "activity_type", "workout_kind", "title", "name"),
            )
            record: dict[str, Any] = {
                "file_name": file_path.name,
                "relative_path": relative_path,
                "local_url": f"/media/local/{encoded_relative_path}",
                "media_source_id": f"media-source://media_source/local/{encoded_relative_path}",
                "timestamp": workout_timestamp.isoformat().replace("+00:00", "Z"),
                "day_key": workout_timestamp.date().isoformat(),
                "modified_at": modified_at.isoformat().replace("+00:00", "Z"),
                "_sort_timestamp": workout_timestamp.timestamp(),
                "_sort_modified": modified_at.timestamp(),
                "_workout_identity": workout_identity,
            }
            for key, value in metadata.items():
                if key not in record:
                    record[key] = value
            if title is not None:
                record["title"] = str(title)
            records.append(record)

    records.sort(
        key=lambda item: (
            float(item.get("_sort_timestamp", 0.0)),
            float(item.get("_sort_modified", 0.0)),
            str(item.get("relative_path", "")),
        ),
        reverse=True,
    )
    deduplicated_records: list[dict[str, Any]] = []
    seen_workout_identities: set[str] = set()
    for item in records:
        workout_identity = str(item.pop("_workout_identity", "")).strip()
        if workout_identity:
            if workout_identity in seen_workout_identities:
                continue
            seen_workout_identities.add(workout_identity)
        item.pop("_sort_timestamp", None)
        item.pop("_sort_modified", None)
        deduplicated_records.append(item)
    return deduplicated_records[:limit]


async def _async_collect_workout_archive_records(
    hass: HomeAssistant,
    username: str,
    limit: int,
) -> list[dict[str, Any]]:
    media_root = Path(hass.config.path("media"))
    return await hass.async_add_executor_job(
        _collect_workout_archive_records,
        media_root,
        username,
        limit,
    )


def _workout_archive_image_url(
    username: str,
    relative_path: str,
    token: str,
    version: str | None = None,
) -> str:
    encoded_username = quote(username, safe="")
    encoded_path = quote(relative_path, safe="")
    encoded_token = quote(token, safe="")
    url = (
        f"{WORKOUT_ARCHIVE_IMAGE_ENDPOINT_PATH}"
        f"?username={encoded_username}&path={encoded_path}&token={encoded_token}"
    )
    normalized_version = str(version or "").strip()
    if normalized_version:
        url += f"&v={quote(normalized_version, safe='')}"
    return url


def _normalize_requested_relative_path(raw_path: str) -> str:
    decoded = unquote(raw_path.strip())
    if not decoded:
        return ""
    normalized = decoded.replace("\\", "/").lstrip("/")
    path_obj = Path(normalized)
    if path_obj.is_absolute():
        return ""
    if any(part in {"", ".", ".."} for part in path_obj.parts):
        return ""
    return path_obj.as_posix()


def _resolve_workout_archive_file_path(
    media_root: Path,
    username: str,
    requested_relative_path: str,
) -> Path | None:
    normalized_path = _normalize_requested_relative_path(requested_relative_path)
    if not normalized_path:
        return None

    username_prefix = f"workouts/{username}/"
    if "/workouts/" not in normalized_path or not normalized_path.endswith(tuple(WORKOUT_ARCHIVE_IMAGE_SUFFIXES)):
        return None

    for archive_domain in WORKOUT_ARCHIVE_FOLDER_DOMAIN_CANDIDATES:
        prefix = f"{archive_domain}/{username_prefix}"
        if not normalized_path.startswith(prefix):
            continue
        candidate_path = media_root / normalized_path
        allowed_root = media_root / archive_domain / "workouts" / username
        try:
            resolved_candidate = candidate_path.resolve()
            resolved_allowed_root = allowed_root.resolve()
            resolved_candidate.relative_to(resolved_allowed_root)
        except (OSError, ValueError):
            return None
        if not resolved_candidate.exists() or not resolved_candidate.is_file():
            return None
        if not _is_supported_workout_archive_file(resolved_candidate):
            return None
        return resolved_candidate

    return None


def _parse_updated_at(raw: Any) -> datetime:
    if isinstance(raw, str):
        try:
            parsed = datetime.fromisoformat(raw)
            if parsed.tzinfo is None:
                return parsed.replace(tzinfo=timezone.utc)
            return parsed.astimezone(timezone.utc)
        except ValueError:
            pass
    return datetime.now(timezone.utc)


def _statistics_id_for_metric(username: str, metric_key: str) -> str:
    return f"{STATISTICS_SOURCE}:{_sanitize(username)}_{_sanitize(metric_key)}"


def _statistics_friendly_name(username: str, metric_name: str) -> str:
    resolved_username = username.strip() or "unknown"
    resolved_metric_name = metric_name.strip() or "Metric"
    return f"{resolved_metric_name} ({resolved_username})"


def _statistics_source_for_id(statistic_id: str) -> str:
    if ":" in statistic_id:
        return statistic_id.split(":", 1)[0]
    return STATISTICS_SOURCE


def _numeric_state_value(raw_state: Any) -> float | None:
    if isinstance(raw_state, bool):
        return None
    if isinstance(raw_state, (int, float)):
        value = float(raw_state)
        return value if math.isfinite(value) else None
    if isinstance(raw_state, str):
        normalized = raw_state.strip()
        if not normalized:
            return None

        numeric_candidate = normalized.replace(",", ".")
        direct_match = re.fullmatch(r"[+-]?(\d+(\.\d+)?|\.\d+)", numeric_candidate)
        if direct_match:
            try:
                value = float(numeric_candidate)
                return value if math.isfinite(value) else None
            except ValueError:
                return None

        # Accept values such as "72 bpm" or "36.5 °C" from payload variations.
        with_unit = re.fullmatch(
            r"([+-]?(?:\d+(?:\.\d+)?|\.\d+))\s*[\w°%/.-][\w°%/\s.-]*",
            numeric_candidate,
        )
        if with_unit:
            try:
                value = float(with_unit.group(1))
                return value if math.isfinite(value) else None
            except ValueError:
                return None
    return None


def _statistics_metadata(
    statistic_id: str,
    name: str,
    unit: str | None,
) -> Any:
    if StatisticMetaData is None:
        return None

    kwargs: dict[str, Any] = {
        "statistic_id": statistic_id,
        "source": _statistics_source_for_id(statistic_id),
        "name": name,
        "has_mean": True,
        "has_sum": False,
        # Explicitly provide unit_class for modern recorder API compatibility.
        # Use None when there is no known compatible unit converter.
        "unit_class": None,
    }
    if StatisticMeanType is not None:
        kwargs["mean_type"] = StatisticMeanType.ARITHMETIC
    if unit:
        kwargs["unit_of_measurement"] = unit
    try:
        return StatisticMetaData(**kwargs)
    except TypeError:
        fallback_kwargs: dict[str, Any] = {
            "has_mean": True,
            "has_sum": False,
            "name": name,
            "source": _statistics_source_for_id(statistic_id),
            "statistic_id": statistic_id,
        }
        if "unit_class" in _STATISTIC_METADATA_FIELDS:
            fallback_kwargs["unit_class"] = None
        if unit and ("unit_of_measurement" in _STATISTIC_METADATA_FIELDS or not _STATISTIC_METADATA_FIELDS):
            fallback_kwargs["unit_of_measurement"] = unit
        if StatisticMeanType is not None and ("mean_type" in _STATISTIC_METADATA_FIELDS):
            fallback_kwargs["mean_type"] = StatisticMeanType.ARITHMETIC
        try:
            return StatisticMetaData(**fallback_kwargs)
        except TypeError:
            return None


def _statistics_data(
    start: datetime,
    state: float,
    mean: float | None = None,
    min_value: float | None = None,
    max_value: float | None = None,
) -> Any:
    if StatisticData is None:
        return None

    resolved_mean = state if mean is None else mean
    resolved_min = state if min_value is None else min_value
    resolved_max = state if max_value is None else max_value

    kwargs: dict[str, Any] = {
        "start": start,
        "state": state,
        "mean": resolved_mean,
        "min": resolved_min,
        "max": resolved_max,
    }
    try:
        return StatisticData(**kwargs)
    except TypeError:
        fallback_kwargs: dict[str, Any] = {
            "start": start,
            "state": state,
            "mean": resolved_mean,
            "min": resolved_min,
            "max": resolved_max,
        }
        try:
            return StatisticData(**fallback_kwargs)
        except TypeError:
            return None


def _statistics_hour_bucket(measured_at: datetime) -> datetime:
    return measured_at.replace(minute=0, second=0, microsecond=0)


def _statistics_candidates_from_sensor(
    runtime: IntegrationRuntime,
    metric_key: str,
    metric_name: str,
    state: str | float | int | bool,
    unit: str | None,
    attributes: dict[str, Any],
) -> list[dict[str, Any]]:
    if not runtime.statistics_enabled:
        return []

    measurement_raw = _measurement_timestamp_value(attributes)
    measurement_at = _parse_measurement_timestamp(measurement_raw)
    numeric_state = _numeric_state_value(state)
    if measurement_at is None or numeric_state is None:
        _LOGGER.debug(
            "Skipping statistics candidate for metric '%s' (measurement=%r parsed=%r state=%r numeric=%r)",
            metric_key,
            measurement_raw,
            measurement_at,
            state,
            numeric_state,
        )
        return []

    statistic_id = _statistics_id_for_metric(runtime.configured_username, metric_key)
    return [
        {
            "statistic_id": statistic_id,
            "name": _statistics_friendly_name(runtime.app_username, metric_name),
            "unit": unit,
            "start": measurement_at,
            "value": numeric_state,
        }
    ]


def _prepare_statistics_imports_for_runtime(
    runtime: IntegrationRuntime,
    candidates: list[dict[str, Any]],
) -> tuple[list[tuple[Any, list[Any]]], dict[str, StatisticsCursorUpdate]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        statistic_id = candidate["statistic_id"]
        grouped.setdefault(statistic_id, []).append(candidate)

    imports: list[tuple[Any, list[Any]]] = []
    cursor_updates: dict[str, StatisticsCursorUpdate] = {}
    for statistic_id, rows in grouped.items():
        legacy_statistic_ids: list[str] = []
        if ":" in statistic_id:
            _, legacy_suffix = statistic_id.split(":", 1)
            if legacy_suffix:
                legacy_statistic_ids.append(legacy_suffix)
        else:
            legacy_statistic_ids.append(f"{STATISTICS_SOURCE}:{statistic_id}")

        cursor_raw = runtime.statistics_cursors.get(statistic_id)
        if cursor_raw is None:
            for legacy_statistic_id in legacy_statistic_ids:
                cursor_raw = runtime.statistics_cursors.get(legacy_statistic_id)
                if cursor_raw is not None:
                    break
        cursor_at = _parse_measurement_timestamp(cursor_raw)
        rows.sort(key=lambda row: row["start"])

        latest_imported_at = cursor_at
        metadata = _statistics_metadata(
            statistic_id=statistic_id,
            name=rows[-1]["name"],
            unit=rows[-1]["unit"],
        )
        if metadata is None:
            continue

        filtered_rows: list[dict[str, Any]] = []
        for row in rows:
            start = row["start"]
            if cursor_at is not None and start <= cursor_at:
                continue
            filtered_rows.append(row)
            if latest_imported_at is None or start > latest_imported_at:
                latest_imported_at = start

        if not filtered_rows:
            continue

        hourly_rows: dict[datetime, list[dict[str, Any]]] = {}
        for row in filtered_rows:
            hour_start = _statistics_hour_bucket(row["start"])
            hourly_rows.setdefault(hour_start, []).append(row)

        import_rows: list[Any] = []
        for hour_start in sorted(hourly_rows):
            bucket_rows = sorted(hourly_rows[hour_start], key=lambda item: item["start"])
            values = [float(item["value"]) for item in bucket_rows]
            if not values:
                continue
            latest_value = float(bucket_rows[-1]["value"])
            mean_value = sum(values) / len(values)
            statistic = _statistics_data(
                start=hour_start,
                state=latest_value,
                mean=mean_value,
                min_value=min(values),
                max_value=max(values),
            )
            if statistic is None:
                continue
            import_rows.append(statistic)

        if not import_rows:
            continue

        if latest_imported_at is not None:
            cursor_updates[statistic_id] = StatisticsCursorUpdate(
                latest_imported_at=latest_imported_at,
                legacy_statistic_ids=tuple(legacy_statistic_ids),
            )
        imports.append((metadata, import_rows))

    return imports, cursor_updates


def _commit_statistics_cursor_updates(
    runtime: IntegrationRuntime,
    cursor_updates: dict[str, StatisticsCursorUpdate],
    successful_statistic_ids: set[str],
) -> None:
    """Persist statistics cursors only for successfully imported series."""
    if not cursor_updates or not successful_statistic_ids:
        return

    for statistic_id, update in cursor_updates.items():
        if statistic_id not in successful_statistic_ids:
            continue

        existing_cursor = _parse_measurement_timestamp(
            runtime.statistics_cursors.get(statistic_id)
        )
        if existing_cursor is not None and existing_cursor >= update.latest_imported_at:
            continue

        runtime.statistics_cursors[statistic_id] = update.latest_imported_at.isoformat()
        for legacy_statistic_id in update.legacy_statistic_ids:
            runtime.statistics_cursors.pop(legacy_statistic_id, None)


async def _async_import_statistics_batches(
    hass: HomeAssistant,
    batches: list[tuple[Any, list[Any]]],
) -> tuple[int, set[str]]:
    if not batches or async_add_external_statistics is None:
        return 0, set()

    imported_samples = 0
    successful_statistic_ids: set[str] = set()
    failed_batches: list[tuple[str, str]] = []
    for metadata, rows in batches:
        statistic_id = _metadata_statistic_id(metadata) or "unknown"
        try:
            result = async_add_external_statistics(hass, metadata, rows)
            if inspect.isawaitable(result):
                await result
            imported_samples += len(rows)
            successful_statistic_ids.add(statistic_id)
        except Exception as err:  # noqa: BLE001
            failed_batches.append((statistic_id, str(err)))

    if failed_batches:
        unique_failed = sorted({item[0] for item in failed_batches})
        sample_ids = ", ".join(unique_failed[:6])
        if len(unique_failed) > 6:
            sample_ids = f"{sample_ids}, ..."
        last_error = failed_batches[-1][1]
        _LOGGER.warning(
            "Could not import Halthy statistics for %d batch(es) across %d metric(s): %s. Last error: %s",
            len(failed_batches),
            len(unique_failed),
            sample_ids,
            last_error,
        )
    return imported_samples, successful_statistic_ids


def _sensor_to_storage(state: HalthySensorState) -> dict[str, Any]:
    return {
        "unique_id": state.unique_id,
        "metric_key": state.metric_key,
        "name": state.name,
        "state": _json_safe(state.state),
        "unit": state.unit,
        "icon": state.icon,
        "attributes": _json_safe(state.attributes),
        "username": state.username,
        "device_id": state.device_id,
        "updated_at": state.updated_at.isoformat(),
    }


def _image_to_storage(state: HalthyImageState) -> dict[str, Any]:
    return {
        "unique_id": state.unique_id,
        "metric_key": state.metric_key,
        "name": state.name,
        "content_type": state.content_type,
        "image_base64": base64.b64encode(state.image_bytes).decode("ascii"),
        "attributes": _json_safe(state.attributes),
        "username": state.username,
        "device_id": state.device_id,
        "updated_at": state.updated_at.isoformat(),
    }


def _sensor_from_storage(unique_id: str, raw: Any) -> HalthySensorState | None:
    if not isinstance(raw, dict):
        return None

    raw_metric_key = str(raw.get("metric_key", "")).strip()
    if not raw_metric_key:
        return None
    metric_key = _normalize_metric_key(raw_metric_key)

    attrs = raw.get("attributes")
    attributes = attrs if isinstance(attrs, dict) else {}

    return HalthySensorState(
        unique_id=str(raw.get("unique_id", unique_id)),
        metric_key=metric_key,
        name=_friendly_metric_name(metric_key, raw.get("name")),
        state=_coerce_state(raw.get("state", "")),
        unit=_canonical_unit(metric_key, raw.get("unit")),
        icon=_metric_icon(metric_key, raw.get("icon")),
        attributes=attributes,
        username=str(raw.get("username", "")).strip() or "unknown",
        device_id=str(raw.get("device_id", "")).strip() or "unknown",
        updated_at=_parse_updated_at(raw.get("updated_at")),
    )


def _image_from_storage(unique_id: str, raw: Any) -> HalthyImageState | None:
    if not isinstance(raw, dict):
        return None

    raw_metric_key = str(raw.get("metric_key", "")).strip()
    if not raw_metric_key:
        return None
    metric_key = _normalize_metric_key(raw_metric_key)

    raw_base64 = raw.get("image_base64")
    if not isinstance(raw_base64, str) or not raw_base64.strip():
        return None

    try:
        image_bytes = base64.b64decode(raw_base64.encode("ascii"), validate=True)
    except (ValueError, binascii.Error):
        return None

    if not image_bytes or len(image_bytes) > MAX_IMAGE_BYTES:
        return None

    attrs = raw.get("attributes")
    attributes = attrs if isinstance(attrs, dict) else {}
    content_type = str(raw.get("content_type", "image/jpeg")).strip() or "image/jpeg"
    if not content_type.startswith("image/"):
        content_type = "image/jpeg"

    return HalthyImageState(
        unique_id=str(raw.get("unique_id", unique_id)),
        metric_key=metric_key,
        name=_friendly_metric_name(metric_key, raw.get("name")),
        content_type=content_type,
        image_bytes=image_bytes,
        attributes=attributes,
        username=str(raw.get("username", "")).strip() or "unknown",
        device_id=str(raw.get("device_id", "")).strip() or "unknown",
        updated_at=_parse_updated_at(raw.get("updated_at")),
    )


def _serialize_entries(entries: dict[str, IntegrationRuntime]) -> dict[str, Any]:
    payload: dict[str, Any] = {"entries": {}}
    serialized_entries: dict[str, Any] = payload["entries"]

    for entry_id, runtime in entries.items():
        serialized_entries[entry_id] = {
            "configured_username": runtime.configured_username,
            "app_username": runtime.app_username,
            "display_name": runtime.display_name,
            "owner_user_id": runtime.owner_user_id,
            "force_upload_interval_seconds": runtime.force_upload_interval_seconds,
            "pending_force_upload_command": _json_safe(runtime.pending_force_upload_command),
            "last_force_upload_ack_at": runtime.last_force_upload_ack_at,
            "last_force_upload_ack_status": runtime.last_force_upload_ack_status,
            "daily_upload_count": runtime.daily_upload_count,
            "daily_upload_count_day": runtime.daily_upload_count_day,
            "statistics_cursors": {
                statistic_id: cursor
                for statistic_id, cursor in runtime.statistics_cursors.items()
                if isinstance(statistic_id, str) and isinstance(cursor, str) and statistic_id.strip()
            },
            "sensors": {
                unique_id: _sensor_to_storage(sensor_state)
                for unique_id, sensor_state in runtime.sensors.items()
            },
            "images": {
                unique_id: _image_to_storage(image_state)
                for unique_id, image_state in runtime.images.items()
            },
        }

    return payload


def _schedule_store_save(hass: HomeAssistant) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    store = domain_data.get("store")
    entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
    if not isinstance(store, Store):
        return

    store.async_delay_save(lambda: _serialize_entries(entries), SAVE_DELAY_SECONDS)


def _resolve_activity_log_mode(target_entries: list[tuple[str, IntegrationRuntime]]) -> str:
    mode_priority = {
        ACTIVITY_LOG_MODE_OFF: 0,
        ACTIVITY_LOG_MODE_SESSION_SUMMARY: 1,
        ACTIVITY_LOG_MODE_PER_ENTITY_VERBOSE: 2,
    }
    resolved = ACTIVITY_LOG_MODE_OFF
    resolved_priority = mode_priority[resolved]
    for _, runtime in target_entries:
        candidate = _coerce_activity_log_mode(runtime.activity_log_mode)
        candidate_priority = mode_priority.get(candidate, 0)
        if candidate_priority > resolved_priority:
            resolved = candidate
            resolved_priority = candidate_priority
    return resolved


async def _async_emit_activity_log_entries(
    hass: HomeAssistant,
    *,
    mode: str,
    username: str,
    prune_unselected_metrics: bool,
    accepted_total: int,
    deleted_total: int,
    duplicates: int,
    ignored_older: int,
    entity_ids: list[str],
    deleted_entity_ids: list[str],
) -> None:
    normalized_mode = _coerce_activity_log_mode(mode)
    if normalized_mode == ACTIVITY_LOG_MODE_OFF:
        return
    if not hass.services.has_service("logbook", "log"):
        return

    source_name = username.strip() or "unknown"
    log_name = f"Halthy ({source_name})"

    async def _log(message: str, entity_id: str | None = None) -> None:
        service_data: dict[str, Any] = {
            "name": log_name,
            "message": message,
            "domain": DOMAIN,
        }
        if entity_id:
            service_data["entity_id"] = entity_id
        await hass.services.async_call("logbook", "log", service_data, blocking=False)

    if normalized_mode == ACTIVITY_LOG_MODE_SESSION_SUMMARY:
        if not prune_unselected_metrics:
            return
        if accepted_total == 0 and deleted_total == 0:
            return
        summary = f"Sync: {accepted_total} updated, {deleted_total} removed"
        if duplicates > 0 or ignored_older > 0:
            summary += f" (duplicates {duplicates}, ignored older {ignored_older})"
        await _log(summary)
        return

    unique_entity_ids = list(dict.fromkeys(entity_ids))
    unique_deleted_entity_ids = list(dict.fromkeys(deleted_entity_ids))
    for entity_id in unique_entity_ids:
        await _log("Entity updated from iOS upload", entity_id=entity_id)
    for entity_id in unique_deleted_entity_ids:
        await _log("Entity removed after metric deselection", entity_id=entity_id)


def _target_entries_for_username(
    entries: dict[str, IntegrationRuntime],
    username: str,
) -> list[tuple[str, IntegrationRuntime]]:
    normalized_username = _sanitize(username)
    return [
        (entry_id, runtime)
        for entry_id, runtime in entries.items()
        if runtime.configured_username == normalized_username
    ]


def _enqueue_force_upload_command(
    runtime: IntegrationRuntime,
    requested_by_user_id: str | None,
    command_type: str = FORCE_UPLOAD_COMMAND_TYPE,
) -> tuple[bool, str]:
    existing_command = _normalize_pending_force_upload_command(runtime.pending_force_upload_command)
    if existing_command is not None:
        runtime.pending_force_upload_command = existing_command
        return False, str(existing_command["id"])

    normalized_command_type = command_type.strip().lower()
    if normalized_command_type not in SUPPORTED_COMMAND_TYPES:
        normalized_command_type = FORCE_UPLOAD_COMMAND_TYPE

    command_id = str(uuid4())
    command: dict[str, Any] = {
        "id": command_id,
        "type": normalized_command_type,
        "requested_at": _utc_now_iso(),
    }
    if requested_by_user_id:
        command["requested_by_user_id"] = requested_by_user_id
    runtime.pending_force_upload_command = command
    return True, command_id


async def async_queue_remote_command(
    hass: HomeAssistant,
    runtime: IntegrationRuntime,
    requested_by_user_id: str | None = None,
    command_type: str = FORCE_UPLOAD_COMMAND_TYPE,
) -> tuple[bool, str]:
    """Queue a remote command for the app and persist runtime store if needed."""
    async with _runtime_lock(runtime):
        queued, command_id = _enqueue_force_upload_command(
            runtime,
            requested_by_user_id=requested_by_user_id,
            command_type=command_type,
        )
    if queued:
        _schedule_store_save(hass)
    return queued, command_id


def _clear_force_upload_timer(hass: HomeAssistant, entry_id: str) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    timers: dict[str, Any] = domain_data.setdefault("force_upload_timers", {})
    unsub = timers.pop(entry_id, None)
    if unsub is not None:
        unsub()


def _clear_daily_upload_reset_timer(hass: HomeAssistant, entry_id: str) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    timers: dict[str, Any] = domain_data.setdefault("daily_upload_reset_timers", {})
    unsub = timers.pop(entry_id, None)
    if unsub is not None:
        unsub()


async def _async_reset_daily_upload_counter_for_entry(
    hass: HomeAssistant,
    entry_id: str,
) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
    runtime = entries.get(entry_id)
    if runtime is None:
        return

    did_reset = False
    async with _runtime_lock(runtime):
        did_reset = _reset_daily_upload_counter_if_needed(hass, runtime, entry_id)
    if did_reset:
        _schedule_store_save(hass)


def _reschedule_daily_upload_reset(hass: HomeAssistant, entry_id: str) -> None:
    _clear_daily_upload_reset_timer(hass, entry_id)

    @callback
    def _midnight_callback(now: datetime) -> None:
        hass.async_create_task(_async_reset_daily_upload_counter_for_entry(hass, entry_id))

    domain_data = hass.data.get(DOMAIN, {})
    domain_data.setdefault("daily_upload_reset_timers", {})[entry_id] = async_track_time_change(
        hass,
        _midnight_callback,
        hour=0,
        minute=0,
        second=0,
    )


async def _async_enqueue_force_upload_from_interval(
    hass: HomeAssistant,
    entry_id: str,
) -> None:
    domain_data = hass.data.get(DOMAIN, {})
    entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
    runtime = entries.get(entry_id)
    if runtime is None:
        return

    async with _runtime_lock(runtime):
        queued, _ = _enqueue_force_upload_command(runtime, requested_by_user_id=None)
    if queued:
        _schedule_store_save(hass)


def _reschedule_force_upload_interval(hass: HomeAssistant, entry_id: str) -> None:
    _clear_force_upload_timer(hass, entry_id)

    domain_data = hass.data.get(DOMAIN, {})
    entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
    runtime = entries.get(entry_id)
    if runtime is None:
        return

    interval_seconds = _coerce_force_upload_interval_seconds(runtime.force_upload_interval_seconds)
    runtime.force_upload_interval_seconds = interval_seconds
    if interval_seconds <= 0:
        return

    @callback
    def _interval_callback(now: datetime) -> None:
        hass.async_create_task(_async_enqueue_force_upload_from_interval(hass, entry_id))

    domain_data.setdefault("force_upload_timers", {})[entry_id] = async_track_time_interval(
        hass,
        _interval_callback,
        timedelta(seconds=interval_seconds),
    )


async def async_update_force_upload_interval(
    hass: HomeAssistant,
    entry_id: str,
    interval_seconds: int,
) -> int:
    domain_data = hass.data.get(DOMAIN, {})
    entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
    runtime = entries.get(entry_id)
    if runtime is None:
        return FORCE_UPLOAD_INTERVAL_DEFAULT_SECONDS

    normalized_interval_seconds = _coerce_force_upload_interval_seconds(interval_seconds)
    async with _runtime_lock(runtime):
        runtime.force_upload_interval_seconds = normalized_interval_seconds
    _reschedule_force_upload_interval(hass, entry_id)
    _schedule_store_save(hass)
    return normalized_interval_seconds


async def _async_reload_entry_on_update(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry when options are updated."""
    await hass.config_entries.async_reload(entry.entry_id)


class HalthyPushView(HomeAssistantView):
    """Accept push payloads from the iOS app and fan out sensor updates."""

    url = ENDPOINT_PATH
    name = ENDPOINT_NAME
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        domain_data = hass.data.get(DOMAIN, {})
        entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
        if not entries:
            return web.json_response(
                {"error": "integration_not_configured", "message": "Add Halthy first"},
                status=503,
            )

        request_size = request.content_length or 0
        if request_size > MAX_REQUEST_BYTES:
            return web.json_response(
                {"error": "payload_too_large", "message": f"Request exceeds {MAX_REQUEST_BYTES} bytes"},
                status=413,
            )

        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "invalid_json"}, status=400)

        if not isinstance(payload, dict):
            return web.json_response({"error": "invalid_payload"}, status=400)
        if request_size <= 0:
            try:
                encoded_payload = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
            except (TypeError, ValueError):
                return web.json_response({"error": "invalid_payload"}, status=400)
            if len(encoded_payload.encode("utf-8")) > MAX_REQUEST_BYTES:
                return web.json_response(
                    {
                        "error": "payload_too_large",
                        "message": f"Request exceeds {MAX_REQUEST_BYTES} bytes",
                    },
                    status=413,
                )

        username = str(payload.get("username", "")).strip()
        if not username:
            return web.json_response({"error": "missing_username"}, status=400)

        raw_device_id = str(payload.get("device_id", "")).strip()
        device_id = raw_device_id or username

        prune_unselected_metrics = payload.get("prune_unselected_metrics") is True
        selected_metric_keys_payload = payload.get("selected_metric_keys")
        selected_metric_keys: set[str] | None = None
        if selected_metric_keys_payload is not None:
            if not isinstance(selected_metric_keys_payload, list):
                return web.json_response({"error": "invalid_selected_metric_keys"}, status=400)
            selected_metric_keys = {
                _normalize_metric_key(item.strip())
                for item in selected_metric_keys_payload
                if isinstance(item, str) and item.strip()
            }
        if prune_unselected_metrics and selected_metric_keys is None:
            return web.json_response({"error": "missing_selected_metric_keys"}, status=400)

        sensors_payload = payload.get("sensors")
        if sensors_payload is None:
            sensors_payload = []
        if not isinstance(sensors_payload, list):
            return web.json_response({"error": "missing_sensors"}, status=400)
        if len(sensors_payload) > MAX_SENSORS_PER_PUSH:
            return web.json_response(
                {
                    "error": "too_many_sensors",
                    "message": f"At most {MAX_SENSORS_PER_PUSH} sensors are allowed per push",
                },
                status=413,
            )

        images_payload = payload.get("images")
        if images_payload is None:
            images_payload = []
        if not isinstance(images_payload, list):
            return web.json_response({"error": "invalid_images"}, status=400)
        if len(images_payload) > MAX_IMAGES_PER_PUSH:
            return web.json_response(
                {
                    "error": "too_many_images",
                    "message": f"At most {MAX_IMAGES_PER_PUSH} images are allowed per push",
                },
                status=413,
            )
        if not sensors_payload and not images_payload and not prune_unselected_metrics:
            return web.json_response({"error": "missing_sensors"}, status=400)

        request_user = request.get("hass_user")
        request_user_id = getattr(request_user, "id", None)
        if not isinstance(request_user_id, str) or not request_user_id.strip():
            return web.json_response(
                {"error": "missing_user_context", "message": "Authenticated user context is required"},
                status=403,
            )
        request_user_id = request_user_id.strip()

        prepared_sensors: list[dict[str, Any]] = []
        for raw_sensor in sensors_payload:
            if not isinstance(raw_sensor, dict):
                continue

            raw_metric_key = str(raw_sensor.get("key", "")).strip()
            if not raw_metric_key:
                continue
            metric_key = _normalize_metric_key(raw_metric_key)

            state = raw_sensor.get("state")
            if state is None:
                continue

            unit = _canonical_unit(metric_key, raw_sensor.get("unit"))

            raw_attributes = raw_sensor.get("attributes", {})
            attributes = _normalize_attributes(raw_attributes if isinstance(raw_attributes, dict) else {})
            if attributes and not _attributes_within_size_limit(attributes):
                return web.json_response(
                    {
                        "error": "attributes_too_large",
                        "message": (
                            f"Sensor '{metric_key}' attributes exceed {MAX_ATTRIBUTES_BYTES} bytes"
                        ),
                    },
                    status=413,
                )

            prepared_sensors.append(
                {
                    "metric_key": metric_key,
                    "state": _coerce_state(state),
                    "name": _friendly_metric_name(metric_key, raw_sensor.get("name")),
                    "unit": unit,
                    "icon": _metric_icon(metric_key, raw_sensor.get("icon")),
                    "attributes": attributes,
                }
            )

        prepared_images: list[dict[str, Any]] = []
        for raw_image in images_payload:
            if not isinstance(raw_image, dict):
                continue

            raw_metric_key = str(raw_image.get("key", "")).strip()
            if not raw_metric_key:
                continue
            metric_key = _normalize_metric_key(raw_metric_key)

            raw_image_base64 = raw_image.get("image_base64")
            if not isinstance(raw_image_base64, str) or not raw_image_base64.strip():
                continue

            try:
                image_bytes = base64.b64decode(raw_image_base64.encode("ascii"), validate=True)
            except (ValueError, binascii.Error):
                return web.json_response(
                    {
                        "error": "invalid_image_base64",
                        "message": f"Image '{metric_key}' is not valid base64",
                    },
                    status=400,
                )
            if not image_bytes:
                continue
            if len(image_bytes) > MAX_IMAGE_BYTES:
                return web.json_response(
                    {
                        "error": "image_too_large",
                        "message": f"Image '{metric_key}' exceeds {MAX_IMAGE_BYTES} bytes",
                    },
                    status=413,
                )

            content_type = str(raw_image.get("content_type", "image/jpeg")).strip() or "image/jpeg"
            if not content_type.startswith("image/"):
                return web.json_response(
                    {
                        "error": "invalid_content_type",
                        "message": f"Image '{metric_key}' must use an image/* content type",
                    },
                    status=400,
                )

            raw_attributes = raw_image.get("attributes", {})
            attributes = _normalize_attributes(raw_attributes if isinstance(raw_attributes, dict) else {})
            if attributes and not _attributes_within_size_limit(attributes):
                return web.json_response(
                    {
                        "error": "attributes_too_large",
                        "message": (
                            f"Image '{metric_key}' attributes exceed {MAX_ATTRIBUTES_BYTES} bytes"
                        ),
                    },
                    status=413,
                )

            prepared_images.append(
                {
                    "metric_key": metric_key,
                    "name": _friendly_metric_name(metric_key, raw_image.get("name")),
                    "content_type": content_type,
                    "image_bytes": image_bytes,
                    "attributes": attributes,
                }
            )

        if not prepared_sensors and not prepared_images and not prune_unselected_metrics:
            return web.json_response({"error": "no_valid_sensors"}, status=400)

        normalized_username = _sanitize(username)
        target_entries = [
            (entry_id, runtime)
            for entry_id, runtime in entries.items()
            if runtime.configured_username == normalized_username
        ]

        if not target_entries:
            return web.json_response(
                {
                    "error": "username_not_configured",
                    "message": f"No Halthy entry found for username '{username}'",
                },
                status=404,
            )

        if any(
            runtime.owner_user_id and runtime.owner_user_id != request_user_id
            for _, runtime in target_entries
        ):
            return web.json_response(
                {
                    "error": "username_not_owned_by_user",
                    "message": f"Username '{username}' is bound to a different Home Assistant user",
                },
                status=403,
            )

        for prepared_image in prepared_images:
            prepared_image["attributes"] = await _async_archive_workout_image(
                hass=hass,
                username=username,
                metric_key=prepared_image["metric_key"],
                content_type=prepared_image["content_type"],
                image_bytes=prepared_image["image_bytes"],
                attributes=prepared_image["attributes"],
            )

        created = 0
        updated = 0
        deleted = 0
        duplicates = 0
        ignored_older = 0
        accepted_sensor_ids: list[str] = []
        accepted_image_ids: list[str] = []
        removed_sensors_by_entry: list[tuple[str, str]] = []
        removed_images_by_entry: list[tuple[str, str]] = []
        statistics_jobs: list[
            tuple[
                IntegrationRuntime,
                list[tuple[Any, list[Any]]],
                dict[str, StatisticsCursorUpdate],
            ]
        ] = []
        hass_temperature_unit = str(hass.config.units.temperature_unit)
        for entry_id, runtime in target_entries:
            pending_sensor_new: list[str] = []
            pending_sensor_updates: list[str] = []
            pending_image_new: list[str] = []
            pending_image_updates: list[str] = []
            async with _runtime_lock(runtime):
                if runtime.owner_user_id is None:
                    runtime.owner_user_id = request_user_id

                accepted_sensor_count_before = len(accepted_sensor_ids)
                accepted_image_count_before = len(accepted_image_ids)
                deleted_count_before = deleted

                metric_lookup = _build_metric_lookup(runtime)
                image_metric_lookup = _build_image_metric_lookup(runtime)
                runtime_statistics_candidates: list[dict[str, Any]] = []
                entry_has_state_update = False
                entry_last_update_at: datetime | None = None
                for prepared_sensor in prepared_sensors:
                    metric_key = prepared_sensor["metric_key"]
                    state = prepared_sensor["state"]
                    name = prepared_sensor["name"]
                    unit = prepared_sensor["unit"]
                    icon = prepared_sensor["icon"]
                    attributes = prepared_sensor["attributes"]
                    state, unit = _resolve_temperature_state(
                        metric_key=metric_key,
                        state=state,
                        unit=unit,
                        preference=runtime.temperature_unit_preference,
                        hass_temperature_unit=hass_temperature_unit,
                    )
                    incoming_measurement_raw = _measurement_timestamp_value(attributes)
                    incoming_measurement = _parse_measurement_timestamp(incoming_measurement_raw)
                    sensor_applied = False

                    matching_unique_ids = _matching_metric_unique_ids(runtime, metric_key, metric_lookup)
                    if matching_unique_ids:
                        # Keep historical entity ids in sync so dashboards that still point at
                        # older ids continue to update after app reinstall/device-id changes.
                        for target_unique_id in matching_unique_ids:
                            existing_state = runtime.sensors.get(target_unique_id)
                            state_device_id = (
                                existing_state.device_id if existing_state is not None else device_id
                            )
                            if existing_state is not None:
                                existing_measurement_raw = _measurement_timestamp_value(
                                    existing_state.attributes
                                )
                                existing_measurement = _parse_measurement_timestamp(
                                    existing_measurement_raw
                                )

                                if (
                                    incoming_measurement is not None
                                    and existing_measurement is not None
                                    and incoming_measurement < existing_measurement
                                ):
                                    ignored_older += 1
                                    continue

                                if (
                                    incoming_measurement_raw is not None
                                    and existing_measurement_raw is not None
                                    and incoming_measurement_raw == existing_measurement_raw
                                    and existing_state.state == state
                                    and existing_state.unit == unit
                                ):
                                    duplicates += 1
                                    continue

                            runtime.sensors[target_unique_id] = HalthySensorState(
                                unique_id=target_unique_id,
                                metric_key=metric_key,
                                name=name,
                                state=_coerce_state(state),
                                unit=unit,
                                icon=icon,
                                attributes=attributes,
                                username=runtime.app_username,
                                device_id=state_device_id,
                            )
                            accepted_sensor_ids.append(target_unique_id)
                            updated += 1
                            sensor_applied = True
                            if entry_last_update_at is None:
                                entry_last_update_at = incoming_measurement or datetime.now(timezone.utc)
                            elif incoming_measurement is not None and incoming_measurement > entry_last_update_at:
                                entry_last_update_at = incoming_measurement
                            entry_has_state_update = True
                            pending_sensor_updates.append(target_unique_id)
                    else:
                        unique_id = _unique_sensor_id(username, device_id, metric_key)
                        runtime.sensors[unique_id] = HalthySensorState(
                            unique_id=unique_id,
                            metric_key=metric_key,
                            name=name,
                            state=_coerce_state(state),
                            unit=unit,
                            icon=icon,
                            attributes=attributes,
                            username=runtime.app_username,
                            device_id=device_id,
                        )
                        accepted_sensor_ids.append(unique_id)
                        created += 1
                        sensor_applied = True
                        if entry_last_update_at is None:
                            entry_last_update_at = incoming_measurement or datetime.now(timezone.utc)
                        elif incoming_measurement is not None and incoming_measurement > entry_last_update_at:
                            entry_last_update_at = incoming_measurement
                        entry_has_state_update = True
                        metric_lookup.setdefault(metric_key, []).append(unique_id)
                        compact_metric = metric_key.replace("_", "")
                        if compact_metric != metric_key:
                            metric_lookup.setdefault(compact_metric, []).append(unique_id)
                        pending_sensor_new.append(unique_id)
                        pending_sensor_updates.append(unique_id)

                    if sensor_applied:
                        runtime_statistics_candidates.extend(
                            _statistics_candidates_from_sensor(
                                runtime=runtime,
                                metric_key=metric_key,
                                metric_name=name,
                                state=_coerce_state(state),
                                unit=unit,
                                attributes=attributes,
                            )
                        )

                for prepared_image in prepared_images:
                    metric_key = prepared_image["metric_key"]
                    name = prepared_image["name"]
                    content_type = prepared_image["content_type"]
                    image_bytes = prepared_image["image_bytes"]
                    attributes = prepared_image["attributes"]
                    matching_unique_ids = _matching_image_unique_ids(
                        runtime,
                        metric_key,
                        image_metric_lookup,
                    )
                    if matching_unique_ids:
                        for target_unique_id in matching_unique_ids:
                            existing_state = runtime.images.get(target_unique_id)
                            state_device_id = (
                                existing_state.device_id if existing_state is not None else device_id
                            )
                            runtime.images[target_unique_id] = HalthyImageState(
                                unique_id=target_unique_id,
                                metric_key=metric_key,
                                name=name,
                                content_type=content_type,
                                image_bytes=image_bytes,
                                attributes=attributes,
                                username=runtime.app_username,
                                device_id=state_device_id,
                            )
                            accepted_image_ids.append(target_unique_id)
                            updated += 1
                            if entry_last_update_at is None:
                                entry_last_update_at = datetime.now(timezone.utc)
                            entry_has_state_update = True
                            pending_image_updates.append(target_unique_id)
                    else:
                        unique_id = _unique_image_id(username, device_id, metric_key)
                        runtime.images[unique_id] = HalthyImageState(
                            unique_id=unique_id,
                            metric_key=metric_key,
                            name=name,
                            content_type=content_type,
                            image_bytes=image_bytes,
                            attributes=attributes,
                            username=runtime.app_username,
                            device_id=device_id,
                        )
                        accepted_image_ids.append(unique_id)
                        created += 1
                        if entry_last_update_at is None:
                            entry_last_update_at = datetime.now(timezone.utc)
                        entry_has_state_update = True
                        image_metric_lookup.setdefault(metric_key, []).append(unique_id)
                        compact_metric = metric_key.replace("_", "")
                        if compact_metric != metric_key:
                            image_metric_lookup.setdefault(compact_metric, []).append(unique_id)
                        pending_image_new.append(unique_id)
                        pending_image_updates.append(unique_id)

                if prune_unselected_metrics and selected_metric_keys is not None:
                    removed_sensor_ids = [
                        unique_id
                        for unique_id, state in runtime.sensors.items()
                        if is_selection_managed_metric(state.metric_key)
                        and _normalize_metric_key(state.metric_key) not in selected_metric_keys
                    ]
                    for unique_id in removed_sensor_ids:
                        runtime.sensors.pop(unique_id, None)
                        removed_sensors_by_entry.append((entry_id, unique_id))
                    deleted += len(removed_sensor_ids)

                    removed_image_ids = [
                        unique_id
                        for unique_id, state in runtime.images.items()
                        if is_selection_managed_metric(state.metric_key)
                        and _normalize_metric_key(state.metric_key) not in selected_metric_keys
                    ]
                    for unique_id in removed_image_ids:
                        runtime.images.pop(unique_id, None)
                        removed_images_by_entry.append((entry_id, unique_id))
                    deleted += len(removed_image_ids)

                deleted_count_delta = deleted - deleted_count_before
                if entry_has_state_update or deleted_count_delta > 0:
                    upserted_last_update_at = (
                        entry_last_update_at
                        if entry_last_update_at is not None
                        else datetime.now(timezone.utc)
                    )
                    _upsert_last_update_sensor(
                        hass=hass,
                        runtime=runtime,
                        entry_id=entry_id,
                        metric_lookup=metric_lookup,
                        source_device_id=device_id,
                        updated_at=upserted_last_update_at,
                    )

                accepted_count_delta = (
                    (len(accepted_sensor_ids) - accepted_sensor_count_before)
                    + (len(accepted_image_ids) - accepted_image_count_before)
                )
                if prune_unselected_metrics and (accepted_count_delta > 0 or deleted_count_delta > 0):
                    _upsert_last_full_sync_sensor(
                        hass=hass,
                        runtime=runtime,
                        entry_id=entry_id,
                        metric_lookup=metric_lookup,
                        source_device_id=device_id,
                        updated_at=entry_last_update_at or datetime.now(timezone.utc),
                    )
                # Count session-level uploads only. Single-point incremental pushes can issue
                # many HTTP requests per sync cycle and would inflate this diagnostic metric.
                if prune_unselected_metrics and (accepted_count_delta > 0 or deleted_count_delta > 0):
                    _increment_daily_upload_counter(
                        hass=hass,
                        runtime=runtime,
                        entry_id=entry_id,
                        source_device_id=device_id,
                        updated_at=entry_last_update_at or datetime.now(timezone.utc),
                    )
                runtime_statistics_batches, runtime_cursor_updates = (
                    _prepare_statistics_imports_for_runtime(runtime, runtime_statistics_candidates)
                )
                if runtime_statistics_batches:
                    statistics_jobs.append(
                        (runtime, runtime_statistics_batches, runtime_cursor_updates)
                    )
            for unique_id in pending_sensor_new:
                async_dispatcher_send(hass, new_sensor_signal(entry_id), unique_id)
            for unique_id in pending_sensor_updates:
                async_dispatcher_send(hass, update_sensor_signal(entry_id, unique_id))
            for unique_id in pending_image_new:
                async_dispatcher_send(hass, new_image_signal(entry_id), unique_id)
            for unique_id in pending_image_updates:
                async_dispatcher_send(hass, update_image_signal(entry_id, unique_id))

        imported_statistics_samples = 0
        for runtime, runtime_statistics_batches, runtime_cursor_updates in statistics_jobs:
            imported_count, successful_statistic_ids = await _async_import_statistics_batches(
                hass,
                runtime_statistics_batches,
            )
            imported_statistics_samples += imported_count
            if successful_statistic_ids and runtime_cursor_updates:
                async with _runtime_lock(runtime):
                    _commit_statistics_cursor_updates(
                        runtime,
                        runtime_cursor_updates,
                        successful_statistic_ids,
                    )
        _schedule_store_save(hass)

        accepted_total = len(accepted_sensor_ids) + len(accepted_image_ids)
        accepted_sensor_unique_ids = list(dict.fromkeys(accepted_sensor_ids))
        accepted_image_unique_ids = list(dict.fromkeys(accepted_image_ids))
        if accepted_total == 0 and deleted == 0:
            if prune_unselected_metrics and selected_metric_keys is not None:
                return web.json_response(
                    {
                        "ok": True,
                        "accepted": 0,
                        "created": 0,
                        "updated": 0,
                        "deleted": 0,
                        "duplicates": duplicates,
                        "ignored_older": ignored_older,
                        "accepted_sensor_unique_ids": [],
                        "accepted_image_unique_ids": [],
                        "unique_ids": [],
                        "entity_ids": [],
                        "image_entity_ids": [],
                        "deleted_entity_ids": [],
                        "statistics_imported": imported_statistics_samples,
                    }
                )
            if duplicates > 0 or ignored_older > 0:
                return web.json_response(
                    {
                        "ok": True,
                        "accepted": 0,
                        "created": 0,
                        "updated": 0,
                        "deleted": 0,
                        "duplicates": duplicates,
                        "ignored_older": ignored_older,
                        "accepted_sensor_unique_ids": [],
                        "accepted_image_unique_ids": [],
                        "unique_ids": [],
                        "entity_ids": [],
                        "image_entity_ids": [],
                        "deleted_entity_ids": [],
                        "statistics_imported": imported_statistics_samples,
                    }
                )
            return web.json_response({"error": "no_valid_sensors"}, status=400)

        registry = er.async_get(hass)
        sensor_entity_ids: list[str] = []
        image_entity_ids: list[str] = []
        for unique_id in accepted_sensor_unique_ids:
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is not None:
                sensor_entity_ids.append(entity_id)
        for unique_id in accepted_image_unique_ids:
            entity_id = registry.async_get_entity_id("image", DOMAIN, unique_id)
            if entity_id is not None:
                image_entity_ids.append(entity_id)
        entity_ids = sensor_entity_ids + image_entity_ids

        deleted_entity_ids: list[str] = []
        for entry_id, unique_id in removed_sensors_by_entry:
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is not None:
                deleted_entity_ids.append(entity_id)
                registry.async_remove(entity_id)
            async_dispatcher_send(hass, remove_sensor_signal(entry_id, unique_id))
        for entry_id, unique_id in removed_images_by_entry:
            entity_id = registry.async_get_entity_id("image", DOMAIN, unique_id)
            if entity_id is not None:
                deleted_entity_ids.append(entity_id)
                registry.async_remove(entity_id)
            async_dispatcher_send(hass, remove_image_signal(entry_id, unique_id))

        activity_log_mode = _resolve_activity_log_mode(target_entries)
        await _async_emit_activity_log_entries(
            hass,
            mode=activity_log_mode,
            username=username,
            prune_unselected_metrics=prune_unselected_metrics,
            accepted_total=accepted_total,
            deleted_total=deleted,
            duplicates=duplicates,
            ignored_older=ignored_older,
            entity_ids=entity_ids,
            deleted_entity_ids=deleted_entity_ids,
        )

        if _LOGGER.isEnabledFor(logging.DEBUG):
            _LOGGER.debug(
                "Processed Halthy push: username=%s accepted=%d created=%d updated=%d deleted=%d stats_imported=%d",
                username,
                accepted_total,
                created,
                updated,
                deleted,
                imported_statistics_samples,
            )

        return web.json_response(
            {
                "ok": True,
                "accepted": accepted_total,
                "created": created,
                "updated": updated,
                "deleted": deleted,
                "duplicates": duplicates,
                "ignored_older": ignored_older,
                "accepted_sensor_unique_ids": accepted_sensor_unique_ids,
                "accepted_image_unique_ids": accepted_image_unique_ids,
                "unique_ids": accepted_sensor_unique_ids + accepted_image_unique_ids,
                "entity_ids": entity_ids,
                "image_entity_ids": image_entity_ids,
                "deleted_entity_ids": deleted_entity_ids,
                "statistics_imported": imported_statistics_samples,
            }
        )


def _request_user_id_from_request(request: web.Request) -> str | None:
    request_user = request.get("hass_user")
    request_user_id = getattr(request_user, "id", None)
    if not isinstance(request_user_id, str) or not request_user_id.strip():
        return None
    return request_user_id.strip()


class HalthyCommandView(HomeAssistantView):
    """Provide pending integration command for the iOS app."""

    url = COMMAND_ENDPOINT_PATH
    name = COMMAND_ENDPOINT_NAME
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        domain_data = hass.data.get(DOMAIN, {})
        entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
        if not entries:
            return web.json_response(
                {"error": "integration_not_configured", "message": "Add Halthy first"},
                status=503,
            )

        username = str(request.query.get("username", "")).strip()
        if not username:
            return web.json_response({"error": "missing_username"}, status=400)

        request_user_id = _request_user_id_from_request(request)
        if request_user_id is None:
            return web.json_response(
                {"error": "missing_user_context", "message": "Authenticated user context is required"},
                status=403,
            )

        target_entries = _target_entries_for_username(entries, username)
        if not target_entries:
            return web.json_response(
                {
                    "error": "username_not_configured",
                    "message": f"No Halthy entry found for username '{username}'",
                },
                status=404,
            )

        if any(
            runtime.owner_user_id and runtime.owner_user_id != request_user_id
            for _, runtime in target_entries
        ):
            return web.json_response(
                {
                    "error": "username_not_owned_by_user",
                    "message": f"Username '{username}' is bound to a different Home Assistant user",
                },
                status=403,
            )

        entry_id, runtime = target_entries[0]
        should_save = False
        async with _runtime_lock(runtime):
            if runtime.owner_user_id is None:
                runtime.owner_user_id = request_user_id
                should_save = True

            pending_command = _normalize_pending_force_upload_command(runtime.pending_force_upload_command)
            runtime.pending_force_upload_command = pending_command
            if pending_command is not None and "delivered_at" not in pending_command:
                pending_command["delivered_at"] = _utc_now_iso()
                runtime.pending_force_upload_command = pending_command
                should_save = True

            response_payload: dict[str, Any] = {
                "ok": True,
                "command": pending_command,
                "entry_id": entry_id,
                "interval_seconds": runtime.force_upload_interval_seconds,
            }

        if should_save:
            _schedule_store_save(hass)
        return web.json_response(response_payload)


class HalthyCommandAckView(HomeAssistantView):
    """Accept command acknowledgements from the iOS app."""

    url = COMMAND_ACK_ENDPOINT_PATH
    name = COMMAND_ACK_ENDPOINT_NAME
    requires_auth = True

    async def post(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        domain_data = hass.data.get(DOMAIN, {})
        entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
        if not entries:
            return web.json_response(
                {"error": "integration_not_configured", "message": "Add Halthy first"},
                status=503,
            )

        request_user_id = _request_user_id_from_request(request)
        if request_user_id is None:
            return web.json_response(
                {"error": "missing_user_context", "message": "Authenticated user context is required"},
                status=403,
            )

        try:
            payload = await request.json()
        except ValueError:
            return web.json_response({"error": "invalid_json"}, status=400)
        if not isinstance(payload, dict):
            return web.json_response({"error": "invalid_payload"}, status=400)

        username = str(payload.get("username", "")).strip()
        command_id = str(payload.get("command_id", "")).strip()
        status_value = str(payload.get("status", "")).strip().lower()
        if not username:
            return web.json_response({"error": "missing_username"}, status=400)
        if not command_id:
            return web.json_response({"error": "missing_command_id"}, status=400)
        if status_value not in {"completed", "failed"}:
            return web.json_response({"error": "invalid_status"}, status=400)

        target_entries = _target_entries_for_username(entries, username)
        if not target_entries:
            return web.json_response(
                {
                    "error": "username_not_configured",
                    "message": f"No Halthy entry found for username '{username}'",
                },
                status=404,
            )
        if any(
            runtime.owner_user_id and runtime.owner_user_id != request_user_id
            for _, runtime in target_entries
        ):
            return web.json_response(
                {
                    "error": "username_not_owned_by_user",
                    "message": f"Username '{username}' is bound to a different Home Assistant user",
                },
                status=403,
            )

        _, runtime = target_entries[0]
        acknowledged = False
        should_save = False
        pending_id: str | None = None
        async with _runtime_lock(runtime):
            if runtime.owner_user_id is None:
                runtime.owner_user_id = request_user_id
                should_save = True

            pending = _normalize_pending_force_upload_command(runtime.pending_force_upload_command)
            runtime.pending_force_upload_command = pending
            pending_id = str(pending.get("id")) if pending is not None else None
            if pending is not None and pending_id == command_id:
                runtime.pending_force_upload_command = None
                runtime.last_force_upload_ack_at = _utc_now_iso()
                runtime.last_force_upload_ack_status = status_value
                acknowledged = True
                should_save = True

        if should_save:
            _schedule_store_save(hass)
        return web.json_response(
            {
                "ok": True,
                "acknowledged": acknowledged,
                "pending_command_id": pending_id,
            }
        )


class HalthyWorkoutArchiveView(HomeAssistantView):
    """Provide a robust workout archive listing from media storage."""

    url = WORKOUT_ARCHIVE_ENDPOINT_PATH
    name = WORKOUT_ARCHIVE_ENDPOINT_NAME
    requires_auth = True

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        domain_data = hass.data.get(DOMAIN, {})
        entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
        if not entries:
            return web.json_response(
                {"error": "integration_not_configured", "message": "Add Halthy first"},
                status=503,
            )

        username = str(request.query.get("username", "")).strip()
        if not username:
            return web.json_response({"error": "missing_username"}, status=400)

        request_user_id = _request_user_id_from_request(request)
        if request_user_id is None:
            return web.json_response(
                {"error": "missing_user_context", "message": "Authenticated user context is required"},
                status=403,
            )

        target_entries = _target_entries_for_username(entries, username)
        if not target_entries:
            return web.json_response(
                {
                    "error": "username_not_configured",
                    "message": f"No Halthy entry found for username '{username}'",
                },
                status=404,
            )
        if any(
            runtime.owner_user_id and runtime.owner_user_id != request_user_id
            for _, runtime in target_entries
        ):
            return web.json_response(
                {
                    "error": "username_not_owned_by_user",
                    "message": f"Username '{username}' is bound to a different Home Assistant user",
                },
                status=403,
            )

        _, runtime = target_entries[0]
        should_save = False
        async with _runtime_lock(runtime):
            if runtime.owner_user_id is None:
                runtime.owner_user_id = request_user_id
                should_save = True
            runtime_username = runtime.configured_username

        if should_save:
            _schedule_store_save(hass)

        limit = _coerce_workout_archive_limit(request.query.get("limit"))
        workouts = await _async_collect_workout_archive_records(
            hass=hass,
            username=runtime_username,
            limit=limit,
        )
        image_token = runtime.workout_archive_access_token
        response_workouts = [
            {
                **workout,
                "image_url": _workout_archive_image_url(
                    runtime_username,
                    str(workout.get("relative_path", "")),
                    image_token,
                    str(workout.get("modified_at", "")),
                ),
            }
            for workout in workouts
        ]
        return web.json_response(
            {
                "ok": True,
                "username": runtime_username,
                "count": len(response_workouts),
                "limit": limit,
                "workouts": response_workouts,
            }
        )


class HalthyWorkoutArchiveImageView(HomeAssistantView):
    """Serve archived workout images via tokenized URL for dashboard cards."""

    url = WORKOUT_ARCHIVE_IMAGE_ENDPOINT_PATH
    name = WORKOUT_ARCHIVE_IMAGE_ENDPOINT_NAME
    requires_auth = False

    async def get(self, request: web.Request) -> web.Response:
        hass: HomeAssistant = request.app[KEY_HASS]
        domain_data = hass.data.get(DOMAIN, {})
        entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
        if not entries:
            return web.Response(status=503)

        username = str(request.query.get("username", "")).strip()
        relative_path = str(request.query.get("path", "")).strip()
        token = str(request.query.get("token", "")).strip()
        if not username or not relative_path:
            return web.Response(status=400)

        target_entries = _target_entries_for_username(entries, username)
        if not target_entries:
            return web.Response(status=404)
        _, runtime = target_entries[0]

        request_user_id = _request_user_id_from_request(request)
        should_save = False
        if request_user_id is not None:
            async with _runtime_lock(runtime):
                if runtime.owner_user_id and runtime.owner_user_id != request_user_id:
                    return web.Response(status=403)
                if runtime.owner_user_id is None:
                    runtime.owner_user_id = request_user_id
                    should_save = True
        else:
            if not token or not hmac.compare_digest(token, runtime.workout_archive_access_token):
                return web.Response(status=401)

        if should_save:
            _schedule_store_save(hass)

        media_root = Path(hass.config.path("media"))
        resolved_path = await hass.async_add_executor_job(
            _resolve_workout_archive_file_path,
            media_root,
            runtime.configured_username,
            relative_path,
        )
        if resolved_path is None:
            return web.Response(status=404)

        response = web.FileResponse(resolved_path)
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        return response


async def _async_register_workout_card_module(hass: HomeAssistant) -> None:
    """Expose and register the bundled Halthy workout card frontend module."""
    domain_data = hass.data.get(DOMAIN)

    module_path = Path(__file__).resolve().parent / WORKOUT_CARD_MODULE_FILENAME
    if not module_path.exists():
        _LOGGER.debug("Workout card module file missing at '%s'", module_path)
        return

    static_registered = bool(
        isinstance(domain_data, dict) and domain_data.get("workout_card_registered")
    )
    if not static_registered:
        try:
            # Modern HA static path API.
            from homeassistant.components.http import StaticPathConfig

            await hass.http.async_register_static_paths(
                [StaticPathConfig(WORKOUT_CARD_STATIC_URL, str(module_path), False)]
            )
            static_registered = True
        except Exception:  # noqa: BLE001
            try:
                # Fallback for older HA cores.
                hass.http.register_static_path(
                    WORKOUT_CARD_STATIC_URL,
                    str(module_path),
                    cache_headers=False,
                )
                static_registered = True
            except Exception as err:  # noqa: BLE001
                _LOGGER.warning(
                    "Failed to register Halthy workout card static module '%s': %s",
                    WORKOUT_CARD_STATIC_URL,
                    err,
                )

    if not static_registered:
        return

    try:
        from homeassistant.components import frontend

        if hasattr(frontend, "async_register_extra_module_url"):
            await frontend.async_register_extra_module_url(hass, WORKOUT_CARD_STATIC_URL)
    except Exception as err:  # noqa: BLE001
        # Keep static URL available even if frontend helper is unavailable.
        _LOGGER.debug(
            "Unable to auto-register workout card module URL '%s': %s",
            WORKOUT_CARD_STATIC_URL,
            err,
        )

    try:
        await _async_ensure_lovelace_module_resource(hass, WORKOUT_CARD_STATIC_URL)
    except Exception as err:  # noqa: BLE001
        _LOGGER.debug(
            "Unable to auto-create Lovelace resource for '%s': %s",
            WORKOUT_CARD_STATIC_URL,
            err,
        )

    if isinstance(domain_data, dict):
        domain_data["workout_card_registered"] = True


async def _async_ensure_lovelace_module_resource(hass: HomeAssistant, module_url: str) -> None:
    """Ensure dashboard resources include the bundled workout card module URL."""
    resources = _lovelace_resource_collection(hass)
    if resources is None:
        _schedule_lovelace_resource_retry(hass)
        return

    existing_resources = await _async_lovelace_resource_items(resources)
    if _lovelace_resource_exists(existing_resources, module_url):
        return

    create_item = getattr(resources, "async_create_item", None)
    if not callable(create_item):
        return

    last_error: Exception | None = None
    for payload in (
        {"url": module_url, "res_type": "module"},
        {"url": module_url, "type": "module"},
    ):
        try:
            created = create_item(payload)
            if inspect.isawaitable(created):
                await created
            _LOGGER.info("Added Lovelace module resource for Halthy workout card: %s", module_url)
            return
        except Exception as err:  # noqa: BLE001
            last_error = err

    if last_error is not None:
        _LOGGER.debug("Failed to create Lovelace module resource '%s': %s", module_url, last_error)


def _lovelace_resource_collection(hass: HomeAssistant) -> Any | None:
    """Return the Lovelace resources collection across HA versions."""
    for key in (LOVELACE_DATA_KEY, "lovelace"):
        lovelace_data = hass.data.get(key)
        if lovelace_data is None:
            continue
        if isinstance(lovelace_data, dict):
            resources = lovelace_data.get("resources")
        else:
            resources = getattr(lovelace_data, "resources", None)
        if resources is not None:
            return resources
    return None


def _schedule_lovelace_resource_retry(hass: HomeAssistant) -> None:
    """Retry resource registration once Home Assistant has fully started."""
    domain_data = hass.data.get(DOMAIN)
    if not isinstance(domain_data, dict):
        return
    if domain_data.get("workout_card_resource_retry_scheduled"):
        return

    @callback
    def _async_retry_lovelace_resource(_event: Any) -> None:
        runtime_domain_data = hass.data.get(DOMAIN)
        if isinstance(runtime_domain_data, dict):
            runtime_domain_data["workout_card_resource_retry_scheduled"] = False
        hass.async_create_task(_async_register_workout_card_module(hass))

    hass.bus.async_listen_once("homeassistant_started", _async_retry_lovelace_resource)
    domain_data["workout_card_resource_retry_scheduled"] = True


async def _async_lovelace_resource_items(resources: Any) -> list[dict[str, Any]]:
    """Return Lovelace resources from storage collection across HA versions."""
    info_fetcher = getattr(resources, "async_get_info", None)
    if callable(info_fetcher):
        try:
            fetched_info = info_fetcher()
            if inspect.isawaitable(fetched_info):
                await fetched_info
        except Exception:  # noqa: BLE001
            pass

    items_fetcher = getattr(resources, "async_items", None)
    if callable(items_fetcher):
        try:
            fetched_items = items_fetcher()
            if inspect.isawaitable(fetched_items):
                fetched_items = await fetched_items
        except Exception:  # noqa: BLE001
            fetched_items = []
        if isinstance(fetched_items, list):
            return [item for item in fetched_items if isinstance(item, dict)]
    return []


def _lovelace_resource_exists(resources: list[dict[str, Any]], module_url: str) -> bool:
    """Check whether Lovelace resources already contain the module URL."""
    normalized_target = module_url.strip()
    if not normalized_target:
        return False
    normalized_variants = {
        normalized_target,
        normalized_target.lstrip("/"),
        f"/{normalized_target.lstrip('/')}",
    }
    for resource in resources:
        resource_url = str(resource.get("url", resource.get("path", ""))).strip()
        if not resource_url:
            continue
        if resource_url not in normalized_variants:
            continue
        resource_type = str(resource.get("res_type", resource.get("type", ""))).strip().lower()
        if resource_type and resource_type != "module":
            continue
        return True
    return False


def _ensure_http_views_registered(
    hass: HomeAssistant,
    domain_data: dict[str, Any],
) -> None:
    """Register HTTP views idempotently."""

    view_specs: tuple[tuple[str, type[HomeAssistantView]], ...] = (
        ("push_view_registered", HalthyPushView),
        ("command_view_registered", HalthyCommandView),
        ("command_ack_view_registered", HalthyCommandAckView),
        ("workout_archive_view_registered", HalthyWorkoutArchiveView),
        ("workout_archive_image_view_registered", HalthyWorkoutArchiveImageView),
    )
    any_registered = False
    for flag_key, view_cls in view_specs:
        if domain_data.get(flag_key):
            any_registered = True
            continue
        hass.http.register_view(view_cls())
        domain_data[flag_key] = True
        any_registered = True
    domain_data["view_registered"] = any_registered


async def async_setup(hass: HomeAssistant, config: dict[str, Any]) -> bool:
    """Set up domain storage."""
    store = Store(hass, STORAGE_VERSION, STORAGE_KEY)
    stored_payload = await store.async_load()
    stored_entries = stored_payload.get("entries", {}) if isinstance(stored_payload, dict) else {}
    if not isinstance(stored_entries, dict):
        stored_entries = {}

    hass.data[DOMAIN] = {
        "entries": {},
        "view_registered": False,
        "push_view_registered": False,
        "command_view_registered": False,
        "command_ack_view_registered": False,
        "workout_archive_view_registered": False,
        "workout_archive_image_view_registered": False,
        "workout_card_registered": False,
        "workout_card_resource_retry_scheduled": False,
        "store": store,
        "stored_entries": stored_entries,
        "force_upload_timers": {},
        "daily_upload_reset_timers": {},
    }
    await _async_register_workout_card_module(hass)

    async def _async_handle_force_upload_service(call: ServiceCall) -> None:
        domain_data = hass.data.get(DOMAIN, {})
        entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
        if not entries:
            return

        raw_username = str(call.data.get(CONF_APP_USERNAME, "")).strip()
        if raw_username:
            target_entries = _target_entries_for_username(entries, raw_username)
        else:
            target_entries = list(entries.items())

        if not target_entries:
            _LOGGER.warning(
                "Halthy force_upload service ignored: no entry for username '%s'",
                raw_username,
            )
            return

        request_user_id = call.context.user_id if isinstance(call.context.user_id, str) else None
        queued_count = 0
        already_pending_count = 0
        denied_count = 0
        for _, runtime in target_entries:
            async with _runtime_lock(runtime):
                if (
                    request_user_id
                    and runtime.owner_user_id
                    and runtime.owner_user_id != request_user_id
                ):
                    denied_count += 1
                    continue
                if request_user_id and runtime.owner_user_id is None:
                    runtime.owner_user_id = request_user_id

                queued, _ = _enqueue_force_upload_command(
                    runtime,
                    requested_by_user_id=request_user_id,
                )
                if queued:
                    queued_count += 1
                else:
                    already_pending_count += 1

        if queued_count > 0:
            _schedule_store_save(hass)
        if denied_count > 0:
            _LOGGER.warning(
                "Halthy force_upload service skipped %d entry(ies) due to owner mismatch",
                denied_count,
            )
        _LOGGER.debug(
            "Halthy force_upload service: queued=%d already_pending=%d target_entries=%d",
            queued_count,
            already_pending_count,
            len(target_entries),
        )

    async def _async_handle_force_influx_backfill_service(call: ServiceCall) -> None:
        domain_data = hass.data.get(DOMAIN, {})
        entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
        if not entries:
            return

        raw_username = str(call.data.get(CONF_APP_USERNAME, "")).strip()
        if raw_username:
            target_entries = _target_entries_for_username(entries, raw_username)
        else:
            target_entries = list(entries.items())

        if not target_entries:
            _LOGGER.warning(
                "Halthy force_influx_backfill service ignored: no entry for username '%s'",
                raw_username,
            )
            return

        request_user_id = call.context.user_id if isinstance(call.context.user_id, str) else None
        queued_count = 0
        already_pending_count = 0
        denied_count = 0
        for _, runtime in target_entries:
            async with _runtime_lock(runtime):
                if (
                    request_user_id
                    and runtime.owner_user_id
                    and runtime.owner_user_id != request_user_id
                ):
                    denied_count += 1
                    continue
                if request_user_id and runtime.owner_user_id is None:
                    runtime.owner_user_id = request_user_id

                queued, _ = _enqueue_force_upload_command(
                    runtime,
                    requested_by_user_id=request_user_id,
                    command_type=FORCE_INFLUX_BACKFILL_COMMAND_TYPE,
                )
                if queued:
                    queued_count += 1
                else:
                    already_pending_count += 1

        if queued_count > 0:
            _schedule_store_save(hass)
        if denied_count > 0:
            _LOGGER.warning(
                "Halthy force_influx_backfill service skipped %d entry(ies) due to owner mismatch",
                denied_count,
            )
        _LOGGER.debug(
            "Halthy force_influx_backfill service: queued=%d already_pending=%d target_entries=%d",
            queued_count,
            already_pending_count,
            len(target_entries),
        )

    if not hass.services.has_service(DOMAIN, SERVICE_FORCE_UPLOAD):
        hass.services.async_register(
            DOMAIN,
            SERVICE_FORCE_UPLOAD,
            _async_handle_force_upload_service,
            schema=FORCE_UPLOAD_SERVICE_SCHEMA,
        )
    if not hass.services.has_service(DOMAIN, SERVICE_FORCE_INFLUX_BACKFILL):
        hass.services.async_register(
            DOMAIN,
            SERVICE_FORCE_INFLUX_BACKFILL,
            _async_handle_force_influx_backfill_service,
            schema=FORCE_UPLOAD_SERVICE_SCHEMA,
        )
    return True


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up from config entry."""
    domain_data = hass.data.setdefault(
        DOMAIN,
        {
            "entries": {},
            "view_registered": False,
            "push_view_registered": False,
            "command_view_registered": False,
            "command_ack_view_registered": False,
            "workout_archive_view_registered": False,
            "workout_archive_image_view_registered": False,
            "workout_card_registered": False,
            "workout_card_resource_retry_scheduled": False,
            "force_upload_timers": {},
            "daily_upload_reset_timers": {},
        },
    )
    await _async_register_workout_card_module(hass)
    entries: dict[str, IntegrationRuntime] = domain_data["entries"]
    stored_entries: dict[str, Any] = domain_data.get("stored_entries", {})
    stored_entry = stored_entries.get(entry.entry_id, {})
    if not isinstance(stored_entry, dict):
        stored_entry = {}

    entry_app_username = str(entry.data.get(CONF_APP_USERNAME) or "").strip()
    entry_display_name = str(entry.data.get(CONF_DISPLAY_NAME) or "").strip()
    stored_app_username = stored_entry.get("app_username")
    stored_display_name = stored_entry.get("display_name")

    if entry_app_username:
        app_username = entry_app_username
    elif isinstance(stored_app_username, str) and stored_app_username.strip():
        app_username = stored_app_username.strip()
    else:
        app_username = str(entry.data.get(CONF_DISPLAY_NAME) or entry.title).strip() or "unknown"

    if CONF_DISPLAY_NAME in entry.data:
        display_name = entry_display_name or app_username
    elif isinstance(stored_display_name, str) and stored_display_name.strip():
        display_name = stored_display_name.strip()
    else:
        display_name = app_username

    configured_username = _sanitize(app_username)
    owner_user_id = str(entry.data.get(CONF_OWNER_USER_ID) or "").strip() or None
    temperature_unit_preference = str(
        entry.options.get(CONF_TEMPERATURE_UNIT, DEFAULT_TEMPERATURE_UNIT)
    ).strip()
    if temperature_unit_preference not in VALID_TEMPERATURE_UNITS:
        temperature_unit_preference = DEFAULT_TEMPERATURE_UNIT
    activity_log_mode = _coerce_activity_log_mode(
        entry.options.get(CONF_ACTIVITY_LOG_MODE, DEFAULT_ACTIVITY_LOG_MODE)
    )
    statistics_enabled = bool(
        entry.options.get(
            CONF_STATISTICS_ENABLED,
            entry.data.get(CONF_STATISTICS_ENABLED, DEFAULT_STATISTICS_ENABLED),
        )
    )

    stored_username = stored_entry.get("configured_username")
    if not entry_app_username and isinstance(stored_username, str) and stored_username.strip():
        configured_username = _sanitize(stored_username)

    stored_owner_user_id = stored_entry.get("owner_user_id")
    if isinstance(stored_owner_user_id, str) and stored_owner_user_id.strip():
        owner_user_id = stored_owner_user_id.strip()

    force_upload_interval_seconds = _coerce_force_upload_interval_seconds(
        stored_entry.get("force_upload_interval_seconds")
    )
    pending_force_upload_command = _normalize_pending_force_upload_command(
        stored_entry.get("pending_force_upload_command")
    )
    last_force_upload_ack_at_raw = stored_entry.get("last_force_upload_ack_at")
    last_force_upload_ack_at: str | None = None
    if isinstance(last_force_upload_ack_at_raw, str) and last_force_upload_ack_at_raw.strip():
        parsed_ack_at = _parse_measurement_timestamp(last_force_upload_ack_at_raw)
        if parsed_ack_at is not None:
            last_force_upload_ack_at = parsed_ack_at.isoformat()
    last_force_upload_ack_status_raw = stored_entry.get("last_force_upload_ack_status")
    last_force_upload_ack_status = (
        str(last_force_upload_ack_status_raw).strip().lower()
        if isinstance(last_force_upload_ack_status_raw, str)
        else None
    )
    if last_force_upload_ack_status not in {"completed", "failed"}:
        last_force_upload_ack_status = None
    daily_upload_count = _coerce_daily_upload_count(stored_entry.get("daily_upload_count"))
    daily_upload_count_day = _normalize_day_key(stored_entry.get("daily_upload_count_day"))
    current_local_day = _current_local_day_key(hass)
    if daily_upload_count_day != current_local_day:
        daily_upload_count = 0
        daily_upload_count_day = current_local_day

    runtime = IntegrationRuntime(
        configured_username=configured_username,
        app_username=app_username,
        display_name=display_name,
        owner_user_id=owner_user_id,
        temperature_unit_preference=temperature_unit_preference,
        activity_log_mode=activity_log_mode,
        statistics_enabled=statistics_enabled,
        force_upload_interval_seconds=force_upload_interval_seconds,
        pending_force_upload_command=pending_force_upload_command,
        last_force_upload_ack_at=last_force_upload_ack_at,
        last_force_upload_ack_status=last_force_upload_ack_status,
        daily_upload_count=daily_upload_count,
        daily_upload_count_day=daily_upload_count_day,
    )

    stored_sensors = stored_entry.get("sensors", {})
    if isinstance(stored_sensors, dict):
        for unique_id, raw_sensor in stored_sensors.items():
            restored = _sensor_from_storage(unique_id, raw_sensor)
            if restored is not None:
                runtime.sensors[unique_id] = restored

    stored_images = stored_entry.get("images", {})
    if isinstance(stored_images, dict):
        for unique_id, raw_image in stored_images.items():
            restored = _image_from_storage(unique_id, raw_image)
            if restored is not None:
                runtime.images[unique_id] = restored

    stored_statistics_cursors = stored_entry.get("statistics_cursors", {})
    if isinstance(stored_statistics_cursors, dict):
        for statistic_id, cursor in stored_statistics_cursors.items():
            if not isinstance(statistic_id, str) or not statistic_id.strip():
                continue
            if not isinstance(cursor, str) or not cursor.strip():
                continue
            if _parse_measurement_timestamp(cursor) is None:
                continue
            runtime.statistics_cursors[statistic_id] = cursor

    # Legacy cleanup: route-location trackers are no longer part of this integration.
    legacy_route_location_sensor_ids = [
        unique_id
        for unique_id, sensor_state in runtime.sensors.items()
        if _normalize_metric_key(sensor_state.metric_key) == "workout_route_location"
    ]
    for unique_id in legacy_route_location_sensor_ids:
        runtime.sensors.pop(unique_id, None)

    legacy_route_location_image_ids = [
        unique_id
        for unique_id, image_state in runtime.images.items()
        if _normalize_metric_key(image_state.metric_key) == "workout_route_location"
    ]
    for unique_id in legacy_route_location_image_ids:
        runtime.images.pop(unique_id, None)

    entries[entry.entry_id] = runtime

    _ensure_http_views_registered(hass, domain_data)

    _upsert_daily_upload_count_sensor(
        hass=hass,
        runtime=runtime,
        entry_id=entry.entry_id,
        metric_lookup=_build_metric_lookup(runtime),
        source_device_id="diagnostic",
        updated_at=datetime.now(timezone.utc),
    )
    _reschedule_force_upload_interval(hass, entry.entry_id)
    _reschedule_daily_upload_reset(hass, entry.entry_id)

    registry = er.async_get(hass)
    legacy_tracker_entity_ids = [
        registry_entry.entity_id
        for registry_entry in er.async_entries_for_config_entry(registry, entry.entry_id)
        if registry_entry.domain == "device_tracker"
        and (registry_entry.unique_id or "").startswith(f"{DOMAIN}_")
    ]

    if legacy_route_location_sensor_ids or legacy_route_location_image_ids or legacy_tracker_entity_ids:
        for unique_id in legacy_route_location_sensor_ids:
            entity_id = registry.async_get_entity_id("sensor", DOMAIN, unique_id)
            if entity_id is not None:
                registry.async_remove(entity_id)

        for unique_id in legacy_route_location_image_ids:
            entity_id = registry.async_get_entity_id("image", DOMAIN, unique_id)
            if entity_id is not None:
                registry.async_remove(entity_id)

        for entity_id in legacy_tracker_entity_ids:
            registry.async_remove(entity_id)

    entry.async_on_unload(entry.add_update_listener(_async_reload_entry_on_update))

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    _schedule_store_save(hass)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        domain_data = hass.data.get(DOMAIN, {})
        entries: dict[str, IntegrationRuntime] = domain_data.get("entries", {})
        entries.pop(entry.entry_id, None)
        _clear_force_upload_timer(hass, entry.entry_id)
        _clear_daily_upload_reset_timer(hass, entry.entry_id)
        _schedule_store_save(hass)
    return unload_ok
