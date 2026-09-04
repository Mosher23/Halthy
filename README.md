
# <img width="30" height="30" alt="Halthy icon" src="custom_components/halthy/brand/icon.png" /> Halthy
Home Assistant custom integration for the Halthy app.


Halthy is a peer-to-peer bridge between iPhone HealthKit data and Home Assistant.
The app talks directly to your Home Assistant instance. There is no external Halthy cloud relay for metric processing.

> [!NOTE]
> **Halthy for iPhone is available in beta.**
>
> [Join the TestFlight](https://testflight.apple.com/join/8KWJZZj2) beta to test the app on an iPhone running iOS 18.5 or later. Beta builds may contain bugs and expire after 90 days. Please send feedback through TestFlight or [GitHub Issues](https://github.com/Mosher23/Halthy/issues).

## Documentation, Privacy, and Support

- Home Assistant integration documentation: [`custom_components/halthy/README.md`](custom_components/halthy/README.md)
- Privacy policy: [`PRIVACY.md`](PRIVACY.md)
- Security policy: [`SECURITY.md`](SECURITY.md)
- Contributing guide: [`CONTRIBUTING.md`](CONTRIBUTING.md)
- Release history: [`CHANGELOG.md`](CHANGELOG.md)
- Support and issue tracker: [GitHub Issues](https://github.com/Mosher23/Halthy/issues)

Halthy does not operate a central backend. Health, workout, and route data are sent only to user-configured destinations such as Home Assistant and optional InfluxDB. The iOS app stores access tokens in Keychain and uses HealthKit permissions only for selected app functionality.

## ✨ Features

- Direct push from iPhone to Home Assistant via `POST /api/halthy/push`
- Per-person setup with stable unique IDs and predictable entity IDs
- Readable metric names with metric-specific icons and standardized units
- Workout route map support (`image.*` entities)
- Workout image archive in Home Assistant media storage with same-workout replacement
- Read-only Home Assistant workout calendar for every configured person
- Optional Home Assistant activity logbook integration (configurable)
- Optional import from Home Assistant sensors back into HealthKit (in app)
- Optional raw export to InfluxDB for long-range history and Grafana dashboards
- Local PDF, CSV, and GPX health-data exports through the iOS share sheet
- Workout maps with Apple Weather context, route replay, and shareable replay videos
- On-device health summaries, charts, trends, and configurable notifications
- Seven-day local trial with an optional one-time lifetime-access purchase
- Home Assistant UI setup with multi-user ownership handling
- Built-in `custom:halthy-workout-card` Lovelace card with workout map navigation and calendar archive

## 🔄 How It Works

### 📤 Export Path (HealthKit -> Home Assistant)

1. The app reads selected HealthKit metrics and optional workout route images.
2. The app sends one authenticated payload to `/api/halthy/push` with:
   - username
   - device ID
   - selected metric keys
   - `sensors[]` values and attributes
   - optional `images[]` route maps
   - optional `workouts[]` calendar metadata
3. The integration creates or updates:
   - `sensor.<app_username>_<metric_key>`
   - `image.<app_username>_workout`
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
- Statistics are external Home Assistant long-term statistics, so they are bucketed hourly by design.
- Home Assistant's 5-minute short-term statistics apply to normal recorder-derived sensor statistics, not these historical `halthy:*` imports.

For full raw sample history and advanced analytics, use optional InfluxDB export.

## 🧩 Install and Setup

### 🛒 Install from HACS (Preferred)

1. Open **HACS**.
2. Go to **Integrations** and add this repository as a custom integration repository if needed:
   - `https://github.com/Mosher23/Halthy`
3. Install **Halthy**.
4. Restart Home Assistant.
5. Go to **Settings -> Devices & Services -> Add Integration**.
6. Select **Halthy**.
7. Enter:
   - **Username** (must match the iOS app username)
   - **Display Name** (optional)
8. Repeat per person.

#### Fix an installation from `v0.1.0-beta`

The `v0.1.0-beta` release archive could install Halthy under an incorrect nested directory. If your installation contains `custom_components/halthy/custom_components/halthy`, remove Halthy in HACS, delete the remaining `custom_components/halthy` directory, install `v0.1.1-beta` or newer, and restart Home Assistant. Removing the HACS files does not remove the person configurations stored by Home Assistant.

### 🧰 Manual Install

1. Copy `custom_components/halthy` to `<config>/custom_components/`.
2. Restart Home Assistant.
3. Add integration from UI.


## 🗂️ Built-in Workout Card

Halthy bundles a Lovelace card: `custom:halthy-workout-card`.

![Halthy workout card showing a fictional route and sample metrics](docs/images/workout-card.png)

The screenshot uses a fictional route and fabricated sample values; it contains no user health or location data.

- The integration auto-registers the card module at startup.
- In most setups you can use the card immediately in dashboard YAML without adding a manual resource.
- If your frontend cache is stale, hard refresh the browser.
- Manual fallback resource URL: `/halthy/halthy-workout-card.js`
- The main card shows the selected workout route map and lets you move between archived workouts with transparent left/right map overlay buttons.
- The right overlay is hidden when the newest workout is already selected.
- The calendar popup shows a larger route preview, a visually separated calendar, highlighted workout days, and a selector when multiple workouts exist on the same day.

Example:

```yaml
type: custom:halthy-workout-card
user: your_username
show_heart_rate_zones: true
```

The card visual editor can auto-detect configured Halthy users and suggest them for selection. Heart-rate zones are shown by default; turn off **Show heart rate zones** in the visual editor or set `show_heart_rate_zones: false` in YAML to hide them.

## 📅 Workout Calendar

Halthy creates one read-only Home Assistant calendar for each configured person:

- Entity ID: `calendar.<username>_workouts`
- Each HealthKit workout is shown at its actual start and end time.
- Event titles use readable workout types such as `Walking`, `Cycling`, or `Strength Training`.
- Event details can include duration, distance, active energy, average heart rate, cadence, and speed when HealthKit provides them.
- Multiple workouts on the same day remain separate calendar events.
- Re-uploading a workout updates the existing event using its HealthKit workout UUID instead of creating a duplicate.

Workout calendar metadata is stored independently from route-map image files, so workouts without route maps can also appear. Both calendar metadata and archived images are bounded by the per-person retention setting to prevent unbounded Home Assistant storage growth.

After installing compatible versions of both the integration and iOS app, unlock the iPhone and run a foreground upload or **Force upload** once. The app sends the available HealthKit workout history in bounded batches. Existing route-map archive metadata is also imported automatically when the integration starts.

Add `calendar.<username>_workouts` to Home Assistant's Calendar dashboard to display the workouts. The calendar is read-only because Apple Health remains the source of truth.

## 🗃️ Workout Image Archive

When the app uploads a workout route image, Halthy now archives it on disk:

- Folder: `/config/media/halthy/workouts/<app_username>/`
- Filename format: `<workout_timestamp>_<workout_fingerprint>.<ext>`
- `workout_timestamp` is derived from workout payload timestamps (`measurement_timestamp`/`workout_end`)

Same-workout replacement behavior:

- If a newer image for the same workout is uploaded, the older archived file is replaced.
- Workout identity uses a stable `workout_uuid` when present, with fallback to workout metadata fingerprinting.
- Newly archived workouts also store a small metadata sidecar so the card can show readable workout types, chips, and zone summaries for archived workouts.
- Older archived images without metadata still display, but may fall back to a generic `Workout` title unless matching entity metadata is available.
- The card reads archive data through authenticated integration endpoints:
  - `GET /api/halthy/workouts`
  - `GET /api/halthy/workout_image`

Workout image entities expose archive metadata attributes including:

- `archive_local_url`
- `archive_media_source_id`
- `archive_file_name`
- `archive_workout_timestamp`
- `archive_replaced_file_count`
- `heart_rate_zones`
- `cycling_power_zones`

## ⚙️ Home Assistant Integration Options

Open **Settings -> Devices & Services -> Halthy -> Configure**.

### 👤 Username and Display Name

You can change the configured **Username** and **Display Name** for an existing Halthy entry.

- The username is the routing key used by `/api/halthy/push`, command polling, services, and the workout archive.
- After changing it in Home Assistant, update the username in the iOS app to match.
- On reload, Halthy moves archived workout files to the new username folder and updates stored archive references.
- Sensor and image entity IDs are migrated when the target ID is available. Configuration controls retain stable internal IDs across username changes.
- Home Assistant recorder statistic IDs contain the username. Changing it starts new `halthy:*` statistic series; existing historical series remain in the recorder.

### 📊 Historical Statistics

Enable or disable **Import historical statistics** independently for each configured person.

- Enabled by default to preserve existing behavior.
- When enabled, timestamped numeric samples are imported as `halthy:*` hourly long-term statistics.
- When disabled, normal `sensor.*` entities continue updating, but no new `halthy:*` statistic rows are imported.
- Disabling the option does not delete historical statistics already stored by Home Assistant.

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

### 🗄️ Stored Workouts and Images

Controls the maximum number of workout calendar records and route images retained for this person. The default is 250 and the supported range is 25 to 2,000. The oldest records and images are removed first.

## 📱 iOS App Setup

Open **Halthy -> Settings**.

### ✅ Required

- **Home Assistant URL** (HTTPS)
- **Access Token** (Home Assistant long-lived token)
- **Username** (must match the integration Username)

### 👍 Recommended

- Enable **Background Upload** for best-effort automatic synchronization
- Select health data types
- Grant workout and route permissions if needed
- Use Test connection

> [!NOTE]
> iOS controls when background tasks may run. Background Upload improves automation, but it does not guarantee an exact execution time. Open Halthy or use **Upload Now** when an immediate upload is required.

### 🔐 Trial and Lifetime Access

- Halthy offers a seven-day trial that starts locally on the device.
- After the trial, premium features can be unlocked with a one-time lifetime-access purchase through Apple StoreKit. It is not a subscription.
- Purchases can be restored from the app.
- Connection setup and foreground upload tools remain available without premium access; premium access enables features such as background synchronization, workout replay, and sharing.

### 🧠 Dashboard and Health Insights

The app can display selected HealthKit information locally as readable dashboard cards, charts, trends, summaries, and workout history.

- Dashboard content is based on the HealthKit permissions and metrics selected by the user.
- Trend notifications compare recent local data with a recent baseline and can be disabled independently.
- On supported devices, summaries can use Apple's on-device Foundation Models framework. Summary context is not sent to a Halthy-operated service.
- Halthy is not a medical device, and summaries or trends are not medical advice, diagnosis, or treatment.

### 🗺️ Workout Maps, Weather, Replay, and Sharing

For workouts with route permission and route data, Halthy can:

- Display detailed, satellite, and 3D workout maps.
- Enrich route displays with workout-time conditions from Apple Weather, including available temperature, humidity, wind, and condition data.
- Replay a workout route and create a shareable replay video.
- Create a workout-card image for sharing or optional saving to Photos.
- Generate route-map images for Home Assistant using configurable map styles and aspect ratio.
- Queue previously archived maps for re-upload after Home Assistant map-preset changes.

Apple Weather enrichment requires a route location and network availability. Existing HealthKit weather metadata remains the fallback when enrichment is unavailable.

### 📤 Local Health Data Export

Open **Halthy -> Settings -> Health Data Export** to create files from selected HealthKit data:

- **PDF** reports, with optional graphs
- **CSV** data files
- **GPX** files for workout routes
- Preset or custom date ranges
- Optional workout and route inclusion

Files are generated locally and are shared only after the user selects a destination in the iOS share sheet. GPX export requires workouts and routes to be included.

### 🔔 Notifications

Notifications are optional and configurable in **Halthy -> Settings -> Notifications**:

- **Sync failures**: alerts after repeated upload failures
- **Workout uploads**: alerts when new workouts are ready and when maps and metrics are uploaded
- **Trend changes**: alerts when local trends move meaningfully from their recent baseline

Notification permission remains controlled by iOS. Disabling notifications does not disable uploads.

### ⚙️ Other Optional App Features

- **Import metrics**: pull mapped Home Assistant sensor states into HealthKit
- **InfluxDB**: export raw HealthKit samples to InfluxDB
- **Shortcuts action**: trigger **Upload Now** from the iOS Shortcuts app
- **Appearance and language**: follow the system or choose a light/dark appearance and a supported app language
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
- `sensor.<app_username>_last_full_sync`
  - Timestamp of the latest full sync that applied at least one change
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
- **Push works but history looks sparse**: Home Assistant external statistics are hourly; use InfluxDB for raw high-resolution history.
- **Import mapping fails**: verify sensor exists, mapping units are correct, and HealthKit write permission is granted.
- **Sensors not updating**: verify the username in the app exactly matches the integration Username.

## 📄 License

Halthy is available under the [MIT License](LICENSE).
