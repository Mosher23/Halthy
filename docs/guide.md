# Halthy guide

Everything you need to explore your health, revisit a workout and connect your own services. The screenshots show the Halthy 1.1 design; controls can differ in older app versions.

## Get started

Halthy works with the health and workout data already recorded in Apple Health. It is not a workout recorder, medical device or diagnostic tool.

1. Install [Halthy from the App Store](https://apps.apple.com/app/halthy/id6798250587) on an iPhone running iOS 18.5 or later.
2. Follow setup, choose your health metrics and grant the corresponding Apple Health read permissions. Workout details and workout routes require their own permissions.
3. Choose the metrics displayed on your dashboard. Open a metric to explore its available charts and summaries.
4. Add Home Assistant or InfluxDB only if you want to use them. Neither is needed for the local dashboard, workout views or file exports.

Apple Health does not reveal individual read-permission decisions to apps. If a value is missing, first check that it exists in Apple Health and that Halthy has access to it. An empty result does not necessarily mean a zero measurement.

Halthy offers a seven-day trial that you start yourself, followed by an optional one-time Lifetime Access purchase. It is not a subscription and the trial does not automatically charge you. Restore purchases using the same Apple Account used for the original purchase.

## Workouts and replay

Browse the workout calendar to find a recorded session. Available details can include distance, duration, pace, energy, heart rate and elevation. A workout without route data can still have useful measurements.

With workout-route permission and recorded route data, you can explore maps, use satellite views, replay the route and create workout images or replay videos to share. Available Apple Weather context depends on route location, workout time and network access.

Read the sharing preview before sending a workout image, route or video: it can reveal precise locations. Halthy does not share these files automatically.

Sleep charts use recorded sleep stages when available, with durations and percentages. Sources can deliver or revise sleep records after you wake up, so later readings may change. Recorded sleep boundaries are not live sleep detection.

## Exports

Open **Settings > Export** in updated app versions. Choose the data and a preset or custom date range, then generate a file locally and select a destination in the iPhone share menu.

- **CSV:** selected health data for spreadsheets and your own analysis.
- **PDF:** readable health reports, with optional graphs.
- **GPX:** recorded workout routes. Include workouts and routes in the export options; a workout summary alone is not enough.

File export is separate from automatic synchronization. A file goes only to the destination you choose in the system share menu. Exported health values and locations can be sensitive; do not attach them to a public support issue.

## Home Assistant

### Install the companion integration

1. Open **HACS > Integrations** in your Home Assistant instance.
2. If needed, add `https://github.com/Mosher23/Halthy` as a custom repository with category **Integration**.
3. Install Halthy and **restart Home Assistant**.
4. Open **Settings > Devices & services > Add integration**, search for **Halthy**, and create a profile for each person.
5. Choose a username and, optionally, a display name. For manual-token setups, the app username must match the integration profile.

For a manual installation, copy only `custom_components/halthy` from the [integration repository](https://github.com/Mosher23/Halthy) into your Home Assistant configuration's `custom_components` directory, then restart and add the integration.

### Connect the iPhone app

In **Settings > Home Assistant**, use the connection setup to choose Home Assistant sign-in or an access token. Native sign-in takes place on your own Home Assistant server, not this website. Use a compatible updated app and integration for native sign-in and device pairing.

- **Home Assistant sign-in:** sign in on your server and select or create an eligible profile. Supported setups can pair a per-device webhook for uploads.
- **Access token:** configure a valid long-lived access token, your HTTPS server URL and the matching profile username.
- **Upload method:** choose paired Webhook delivery or Authenticated API as supported by the saved connection. A webhook is not a replacement for authentication for pairing, revocation or commands.

Keep access tokens and webhook URLs private. This website does not ask for, accept or relay credentials. The app's approved sign-in return address is `halthy-ha://auth/callback`.

### Verify and upload

Use **Test connection** and read its displayed success, warning or failure explanation. Connection checks and successful upload acknowledgments are separate checks. Select your metrics and try a foreground upload with the iPhone unlocked.

For an ownerless profile created through the config-flow API, an administrator may need to run `halthy.assign_profile_owner` before it appears during sign-in. This action cannot transfer an already-owned profile. See [advanced troubleshooting](https://github.com/Mosher23/Halthy/blob/main/docs/troubleshooting.md).

### Add the workout card

The companion integration bundles `custom:halthy-workout-card` and normally registers it automatically. Add it to a dashboard; replace `your_username` with the configured Halthy username.

```yaml
type: custom:halthy-workout-card
user: your_username
show_heart_rate_zones: true
```

Each person also gets a read-only `calendar.<username>_workouts` entity. Workout metadata and archived images have per-person retention limits. Maps, zone details and calendar history depend on what the app has uploaded.

[Full integration reference](https://github.com/Mosher23/Halthy/blob/main/custom_components/halthy/README.md) covers entity IDs, configuration, archive storage, services and authentication.

## InfluxDB

Open **Settings > InfluxDB** and configure your HTTPS address, organization, bucket, measurement and a token with the required permissions. Select the metrics and export options you want, run the connection test and try an upload.

A current snapshot is different from the full recorded sample history. Halthy can export supported raw HealthKit samples, including available heart-rate history, in bounded batches. Large imports may continue over multiple runs. The app cannot export samples it cannot read from Apple Health.

Check **Settings > Logs** for InfluxDB acknowledgments and history progress. InfluxDB retention and deletion are controlled by your bucket configuration, not by Halthy. Never put its token in a public issue.

## Digital Health

Digital Health is optional and uses separate Screen Time data-access permission, not HealthKit permission. It requires **iOS 26.4 or later, an eligible device in the EU and an EU Apple Account**. Apple's authorization system determines eligibility.

Open **Settings > Digital health** to configure supported readings. Available device-level aggregates include screen time, longest activity session, first pickup time and pickups without app use. App identities and website browsing history are not sent as part of these aggregates.

Updated compatible versions can upload selected readings to Home Assistant, including paired webhook delivery, and export supported Digital Health history to InfluxDB. Changing the app language or region alone does not enable eligibility.

## Background uploads

Enable background upload for the relevant destination in Halthy and review Background App Refresh in iPhone Settings. iOS decides when the app may run: **background uploads do not guarantee a fixed interval or continuous execution**.

Low Power Mode, network access, scheduling and unavailable protected HealthKit data can delay work. Opening the app with the iPhone unlocked gives pending work another opportunity to continue. Use a foreground manual upload for an immediate attempt.

Current readings, historical imports, workout images and commands are distinct work. An upload can succeed while history is still importing. If the app reports an issue, inspect the named operation in Logs rather than assuming every destination failed.

## Daily resets and history

The integration resets daily counters independently of phone uploads at **00:00 in the reporting timezone**. It also catches up after a restart or reload. Updated snapshots supply the reporting timezone; older payloads fall back to Home Assistant's timezone. Calendar-day boundaries follow daylight saving changes.

- Daily activity, steps, distance, energy, dietary totals, event counts and workout totals reset to **0**.
- Daily Digital Health screen time, longest activity session and pickups without app use reset to **0**.
- First pickup time becomes **unknown** until a pickup is reported for the new day.
- Sleep-session results, latest medical readings and last-workout timestamps retain their last result. They are not daily counters.
- Daily uploads uses Home Assistant's timezone. A midnight reset is not counted as a new upload or a new full sync.

Previous-day retries and historical daily snapshots cannot replace today's live total. Updating the integration does not rewrite old graph history or move a previously recorded morning reset back to midnight. The corrected behavior applies to future history.

Live entity states are current readings. Home Assistant's imported `halthy:*` long-term statistics are hourly summaries, not a raw sample archive. For full supported sample history, use InfluxDB. See the [rollover reference](https://github.com/Mosher23/Halthy/blob/main/custom_components/halthy/README.md#midnight-rollover) for freshness attributes and edge cases.

## Troubleshooting and logs

Open **Settings > Logs**. Use the filters to focus on issues, Home Assistant, InfluxDB or Digital Health. Expand **Details** for the specific operation. Share exports a timestamped CSV diagnostic log through the system share menu.

Review diagnostic files before sharing. Remove private server addresses, credentials, health values and route locations. A diagnostic log is different from a health-data export.

- **Missing readings:** check Apple Health records, permissions and metric selection.
- **Connection warning:** read the test result, confirm server reachability and the saved connection method, then retry.
- **Old daily graph:** previous history is retained; verify a new midnight rollover after updating and restarting the integration.
- **Sleep total changes:** a source may have delivered late records or revised the session. Compare the underlying records in Apple Health.
- **Missing history:** check logs and selected import range. Current readings being accepted does not mean every historical batch is complete.
- **Workout preparation fails:** review the named workout and preparation stage in Details. Retry or recovery actions depend on the failure; don't repeatedly create new pairings.

Visit [Support](support.html) for common questions and contact details, or the [advanced integration troubleshooting reference](https://github.com/Mosher23/Halthy/blob/main/docs/troubleshooting.md) for administrator actions. Do not send health data or credentials to this website.
