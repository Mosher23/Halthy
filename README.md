# <img width="30" height="30" alt="icon-glass" src="https://github.com/user-attachments/assets/6b268c3b-f5e0-42b5-bde7-4157a2a555a2" /> Halthy
Home Assistant custom integration for Halthy App.

# Halthy

Halthy is a peer-to-peer bridge that sends selected HealthKit metrics from your iPhone to Home Assistant.

The iOS app reads data from HealthKit and pushes it directly to Home Assistant on your network or public endpoint. There is no external HealthKit processing server in between.

## Features

- Direct upload from iPhone to Home Assistant (`/api/halthy/push`)
- Per-person setup with stable entity IDs and unique identifiers
- Optional background sync
- Optional raw HealthKit export to InfluxDB for advanced graphs in Grafana
- Human-readable sensor names and metric-specific icons
- Supports route map images for workouts
- Easy setup from Home Assistant UI

## How it works

1. The Home Assistant integration exposes a secure endpoint in Home Assistant itself:
   - `POST /api/halthy/push`
2. The app collects selected HealthKit metrics and optional workout route images.
3. The app sends them in a single POST with:
   - your configured app username
   - unique device ID
   - selected metric keys
   - `sensors[]` entries with state, unit, and optional attributes
   - optional `images[]` entries for route maps
4. The integration creates/updates:
   - sensor entities (example `sensor.<app_username>_steps`)
   - image entities (example `image.<app_username>_workout_route_map`)
   - a timestamp diagnostic sensor `sensor.<app_username>_last_update`

Entity IDs use your integration username prefix, so `sensor.sergi_steps` and `sensor.anna_steps` stay separate for different people.

The integration runs inside Home Assistant, so data is written directly into your HA instance.

### Home Assistant state limitation

Home Assistant entity states are designed as "current state" storage. The push endpoint updates the current value of each entity, so historical timing from every sample is not preserved as state in HA automatically.

What this means:

- dashboards and automations work well with latest values
- precise time-series reconstruction and strict timestamp-based analytics are limited at the HA state level

For richer historical analysis, enable optional InfluxDB export. That path sends raw health samples with timestamps to InfluxDB and is better suited for Grafana charts and long-range analytics.

## Install and set up Home Assistant integration

### Install from HACS (preferred)

1. Open **HACS** in Home Assistant.
2. Go to **Integrations** → **...** → **+ Explore & download repositories**.
3. Add repository `https://github.com/Mosher23/Halthy-Bridge` and choose **Integration**.
4. Restart Home Assistant.
5. Go to **Settings → Devices & Services → Add Integration**.
6. Select **Halthy**.
7. Enter:
   - **App Username** (must match what you configure in the iOS app)
   - Optional **Display Name**
8. Repeat steps 6–7 once for each person.
9. If this repository is not available in the HACS browser yet, add it first as a custom repository.

### Manual install (alternative)

1. Copy `custom_components/halthy` into `<config>/custom_components/`.
2. Restart Home Assistant.
3. Add the integration as above.

## What to put in the iOS app

Open the app and go to **Settings**.

### Required fields

- **Home Assistant URL**
  - This must be HTTPS and reachable from your phone.
  - Example: `https://homeassistant.local:8123` or a remote URL behind Nabu Casa / reverse proxy / cloudflare tunnel.
- **Access Token**
  - A Home Assistant long-lived token for your user.
- **Username**
  - Human readable identifier used to route data to the corresponding integration entry and to name entities.

Recommended pattern for username:

- Use the same value as **App Username** in integration setup.
- Keep it short and stable (for example `John`, `Wife`, etc).

### Recommended settings

- Enable **Background Upload** if you want automatic periodic uploads.
- Choose **Health Data Types** you want to send.
- Grant route access for route map uploads under health permissions.
- Use **Test connection** after entering settings.

### In-app options and behavior

- Set upload interval for scheduled background syncs.
- `sensor` names are formatted for readability in the UI
  - `walking_speed` becomes `Walking Speed`
- You can run a manual upload test from the app and see upload status in logs.

## How to get a Home Assistant token

1. Open Home Assistant in browser.
2. Open your profile (avatar in the left sidebar).
3. Go to **Security**.
4. Under **Long-lived access tokens**, click **Create token**.
5. Give it a clear name such as `Halthy`.
6. Copy the token immediately and paste it into **Access Token** in the app.

Optional workflow:
- Use the QR scanner button in the app to paste a token from a QR payload.

## Optional: InfluxDB export + Grafana

Halthy can also export raw HealthKit points to InfluxDB while still using Home Assistant for entity state.

In **Settings → InfluxDB**:

- Enable export
- InfluxDB URL
- Organization
- Bucket
- Measurement (default: `halthy`)
- InfluxDB Token

Why you might use this:
- More granular data retention than HA recorder
- Query-level analytics and transformations in InfluxDB
- Better charts/boards in Grafana for long-term trends

## Troubleshooting

- Home Assistant URL and token are empty: integration will not accept uploads.
- `401`/`403` responses from Home Assistant: token is missing or expired.
- Sensor updates appear but values are delayed: confirm upload interval and allow background execution for the app.
- If entities look wrong, verify app username matches `App Username` used in the integration setup.
