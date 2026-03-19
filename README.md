
<a href="https://www.buymeacoffee.com/sergiit" target="_blank"><img src="https://cdn.buymeacoffee.com/buttons/default-orange.png" alt="Buy Me A Coffee" height="41" width="174"></a>   [![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/O5O81W9KPE)   [![Donate with PayPal](https://www.paypalobjects.com/en_US/DK/i/btn/btn_donateCC_LG.gif)](https://www.paypal.com/donate/?hosted_button_id=UGG7JC4WCZFEY)


# <img width="30" height="30" alt="Halthy icon" src="custom_components/halthy/brand/icon.png" /> Halthy
Home Assistant custom integration for the Halthy app.


Halthy is a peer-to-peer bridge between iPhone HealthKit data and Home Assistant.
The app talks directly to your Home Assistant instance. There is no external Halthy cloud relay for metric processing.

## ✨ Features

- Direct push from iPhone to Home Assistant via `POST /api/halthy/push`
- Per-person setup with stable unique IDs and predictable entity IDs
- Human-readable metric names with metric-specific icons and standardized units
- Workout route map support (`image.*` entities)
- Optional Home Assistant activity logbook integration (configurable)
- Optional import from Home Assistant sensors back into HealthKit (in app)
- Optional raw export to InfluxDB for long-range history and Grafana dashboards
- Home Assistant UI setup with multi-user ownership handling

## 🔄 How It Works

### 📤 Export Path (HealthKit -> Home Assistant)

1. The app reads selected HealthKit metrics and optional workout route images.
2. The app sends one authenticated payload to `/api/halthy/push` with:
   - app username
   - device ID
   - selected metric keys
   - `sensors[]` values and attributes
   - optional `images[]` route maps
3. The integration creates or updates:
   - `sensor.<app_username>_<metric_key>`
   - `image.<app_username>_workout_route_map`
   - diagnostic sensors for sync status

### 📥 Command Path (Home Assistant -> App)

The integration exposes command endpoints used by the iOS app:

- `GET /api/halthy/command`
- `POST /api/halthy/command_ack`

This is used for remote actions like force upload and Influx backfill.

## 📉 Home Assistant State Limitation and 📊 Statistics Import

> [!IMPORTANT]
> Home Assistant entity states represent **current values**. State pushes do not preserve full sample-by-sample history by themselves.

To improve history inside Home Assistant:

- When a pushed numeric metric includes `measurement_timestamp`, Halthy imports it into recorder statistics.
- Imports are deduplicated by per-metric cursors.
- Statistics are bucketed hourly for reliable long-term charting.

For full raw sample history and advanced analytics, use optional InfluxDB export.

## 🧩 Install and Setup

### 🛒 Install from HACS (Preferred)

1. Open **HACS**.
2. Go to **Integrations** and add this repository as a custom integration repository if needed:
   - `https://github.com/Mosher23/Halthy-Bridge`
3. Install **Halthy**.
4. Restart Home Assistant.
5. Go to **Settings -> Devices & Services -> Add Integration**.
6. Select **Halthy**.
7. Enter:
   - **App Username** (must match iOS app username)
   - **Display Name** (optional)
8. Repeat per person.

### 🧰 Manual Install

1. Copy `custom_components/halthy` to `<config>/custom_components/`.
2. Restart Home Assistant.
3. Add integration from UI.

## ⚙️ Home Assistant Integration Options

Open **Settings -> Devices & Services -> Halthy -> Configure**.

### 🌡️ Temperature Unit

Choose how incoming temperature metrics are exposed:

- Home Assistant unit system
- Always Celsius
- Always Fahrenheit

### 📝 Activity Log Mode

Controls what Halthy writes to Home Assistant Logbook:

| Mode | Behavior |
|---|---|
| `Off` | No Logbook entries |
| `Session summary` | One summary entry per sync session (updated/removed counts) |
| `Per-entity verbose` | Per-entity update/remove entries |

## 📱 iOS App Setup

Open **Halthy -> Settings**.

### ✅ Required

- **Home Assistant URL** (HTTPS)
- **Access Token** (Home Assistant long-lived token)
- **Username** (must match integration App Username)

### 👍 Recommended

- Enable background upload
- Select health data types
- Grant workout and route permissions if needed
- Use Test connection

### 🧠 Optional App Features

- **Import metrics**: pull mapped Home Assistant sensor states into HealthKit
- **InfluxDB**: export raw HealthKit samples to InfluxDB
- **Shortcuts action**: trigger **Upload Now** from the iOS Shortcuts app
- **Log** section: view upload/import status and troubleshooting hints

## 🔗 iOS Shortcuts: Upload Now

Halthy exposes an App Intent named **Upload Now**.

You can use it from the iOS Shortcuts app:

1. Open **Shortcuts**.
2. Create or edit a shortcut.
3. Tap **Add Action** and search for **Halthy**.
4. Select **Upload Now**.
5. Run it manually, pin it to Home Screen, or use it in automations.

Behavior:

- Runs the same force-upload flow as the app's **Upload Now** button.
- Uses your existing app configuration and selected metrics.

## 🔁 Import Metrics from Home Assistant (Optional)

Halthy can import Home Assistant sensor values into HealthKit.

In app settings:

1. Enable **Import metrics**.
2. Add mapping(s):
   - Home Assistant sensor suffix (for `sensor.<suffix>`)
   - Target HealthKit metric type
   - Source and target units
   - Friendly name
3. Keep each mapping enabled.

Current behavior and limits:

- Import supports quantity metrics.
- Dietary metrics are excluded.
- Values are fetched from Home Assistant sensor state endpoints.
- Import uses timestamps from `measurement_timestamp` when available, with fallback to HA update timestamps.
- Imported HealthKit samples are written as user-entered values.

## 🩺 Diagnostic Metrics

Each configured person gets diagnostic entities:

- `sensor.<app_username>_last_update`
  - Timestamp of the latest accepted update for that user
- `sensor.<app_username>_daily_upload_count`
  - Number of full sync uploads accepted for current local day
  - Automatically resets daily

You also get config/control entities per user:

- `select.<app_username>_force_upload_interval`
- `button.<app_username>_force_upload`
- `button.<app_username>_force_influx_backfill`

## 📈 Optional: InfluxDB Export + Grafana

In app **Settings -> InfluxDB**:

- Enable Influx export
- URL
- Organization
- Bucket
- Measurement (default `healthkit_raw`)
- Token

Use this when you want:

- Raw timestamped sample retention
- More precise historical analysis than state-only Home Assistant entities
- Grafana dashboards over long periods

## 🔑 How to Get a Home Assistant Token

1. Open Home Assistant.
2. Open your user profile.
3. Go to **Security**.
4. Under **Long-lived access tokens**, create a token.
5. Copy it immediately into the app.

## 🛠️ Troubleshooting

- **`401` or `403`**: token missing, expired, or wrong user ownership for target username.
- **Push works but history looks sparse**: this is usually state-vs-history limitation; enable recorder statistics and/or InfluxDB.
- **Import mapping fails**: verify sensor exists, mapping units are correct, and HealthKit write permission is granted.
- **Sensors not updating**: verify app username in app exactly matches integration App Username.
