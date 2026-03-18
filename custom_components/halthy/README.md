# Halthy Home Assistant Integration

Halthy is a Home Assistant custom integration that receives health metrics from the Halthy app and creates per-user entities with stable unique identifiers.

## What This Integration Provides

- Receives app uploads at `POST /api/halthy/push`
- Creates and updates `sensor.*` and `image.*` entities in Home Assistant
- Supports multi-user setup via one config entry per app username
- Provides diagnostic and control entities for sync monitoring
- Supports optional logbook activity logging
- Imports numeric samples with timestamps into Home Assistant recorder statistics

## Installation

### HACS (recommended)

1. Open **HACS**.
2. Add repository `https://github.com/Mosher23/Halthy-Bridge` as a custom integration repository if needed.
3. Install **Halthy**.
4. Restart Home Assistant.

### Manual

1. Copy `custom_components/halthy` into `<config>/custom_components/`.
2. Restart Home Assistant.

## Setup in Home Assistant UI

1. Go to **Settings -> Devices & Services -> Add Integration**.
2. Select **Halthy**.
3. Enter:
   - **App Username**: must match the username configured in the app
   - **Display Name** (optional): shown as device name in Home Assistant
4. Repeat for each person.

## Integration Options

Open **Settings -> Devices & Services -> Halthy -> Configure**.

### Temperature Unit

- Home Assistant unit system
- Always Celsius
- Always Fahrenheit

### Activity Log Mode

| Mode | Behavior |
|---|---|
| `Off` | No logbook entries |
| `Session summary` | One summary log per sync session |
| `Per-entity verbose` | Log entry for each updated/removed entity |

## Entities Created

### Data entities

- Sensors: `sensor.<app_username>_<metric_key>`
- Workout route image: `image.<app_username>_workout_route_map`

### Diagnostic entities

- `sensor.<app_username>_last_update`
- `sensor.<app_username>_daily_upload_count`

### Control/config entities

- `select.<app_username>_force_upload_interval`
- `button.<app_username>_force_upload`
- `button.<app_username>_force_influx_backfill`

## Services

- `halthy.force_upload`
- `halthy.force_influx_backfill`

Both services accept optional `app_username` to target one configured user.

## API Endpoints (used by the app)

- `POST /api/halthy/push`
- `GET /api/halthy/command`
- `POST /api/halthy/command_ack`

## Recorder Statistics Behavior

> [!IMPORTANT]
> Home Assistant states represent current values. Full sample history is not stored as state snapshots by default.

When a numeric metric arrives with `measurement_timestamp`, the integration imports it into recorder statistics (hourly buckets, cursor-based deduplication).

## Troubleshooting

- **Config flow does not open**: restart Home Assistant and check integration logs for config flow errors.
- **`401` / `403` on upload**: verify long-lived token and user ownership for configured username.
- **Entities not updating**: verify app username exactly matches **App Username** in the integration entry.
- **History gaps in dashboards**: confirm payload includes `measurement_timestamp` and recorder is enabled.
