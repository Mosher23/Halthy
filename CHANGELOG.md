# Changelog

All notable changes to Halthy are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [0.2.8] - 2026-10-29

### Fixed

- Automatically migrate legacy `count`/`counts` statistics metadata for unitless Halthy counters after Home Assistant starts and on integration reload. Preserves short-term and long-term values, timestamps and entity IDs. Resolves the unit-change repairs introduced by v0.2.7 without deleting statistics.
- Add the administrator-only `halthy.migrate_counter_statistics` action with an optional profile selector and preview mode. Verify Recorder writes before clearing matching repairs; leave unrelated sensors, units and repair issues untouched. Safe to retry after a recorder outage.

### Upgrade

- Update the integration and restart Home Assistant, or reload Halthy after the updated code is loaded. The counter-unit migration runs automatically. No iOS app update is required for this repair.
- Do not delete historical statistics or recreate affected entities. For a manual preview or retry, run **Halthy: Migrate counter statistics** from **Tools > Actions**. See the [migration instructions](docs/troubleshooting.md#unit-change-repairs-after-v027).

## [0.2.7] - 2026-10-29

### Fixed

- Align Go to bed time and Sleep in bed with a shared calculation in the app. Prefer recorded HealthKit in-bed intervals; otherwise use the selected sleep-session window as an explicit estimate, including awakenings and gaps. Both sensors expose source and boundary attributes. Requires an updated iOS app.
- Accept corrected sleep-source attributes even when the value and measurement timestamp are unchanged, so later recorded data can replace an estimate.
- Refresh Workout start and Workout end from the latest stored workout, including calendar-only uploads and startup recovery. Preserve existing entity IDs and prevent older history from replacing newer workout times.
- Preserve the workout image entity when current image bytes are missing or a map has been cleared. Retain its stable identity across restarts and reuse it when a replacement arrives, without restoring cleared image data.
- Display the workout image entity's state as the workout finish timestamp instead of a workout-type string, avoiding Home Assistant's "Invalid timestamp" message. Keep the type in `workout_type` and refresh the picture URL for re-rendered maps.
- Remove the literal `count` unit from counters and event totals, including restored entities. Preserve meaningful units such as steps, floors, bpm, and rates.

### Compatibility

- Update the integration and restart Home Assistant for the workout and counter fixes. Updated sleep calculation and source attributes also require the updated iOS app and a new upload; this integration release does not update the app itself.
- Retains the v0.2.6 HACS review fixes for asynchronous time-zone loading and preservation of user-selected entity IDs.

## [0.2.6] - 2026-10-28

### Fixed

- Resolve dynamic reporting time zones with Home Assistant's async time-zone API before upload validation, daily rollover, or startup recovery. Calculation helpers receive resolved zones and never load the time-zone database on the event loop. Preserve fixed-offset identifiers, invalid-payload rejection, and daylight-saving rollover behaviour.
- Preserve user-customized sensor and image entity IDs across uploads, reloads, and username changes. Remove automatic entity-ID rewriting; username-prefixed IDs are suggested only when Home Assistant creates a new entity. Existing IDs remain unchanged.

### Tests

- Add real Home Assistant registry regressions for sensor and image renames, executor-thread coverage for uncached time zones, and upload, timer and startup recovery checks.

### Compatibility

- Addresses both changes requested in the HACS inclusion review. Update through HACS and restart Home Assistant; no iOS app update is required.

## [0.2.5] - 2026-10-27

### Fixed

- Preserve recently uploaded workouts, including workouts without route images, when saving options or reloading the integration. Flush current runtime state before unloading and retain other profiles during delayed saves. Fixes #8.

### Added

- Add the administrator-only `halthy.assign_profile_owner` action to repair ownerless profiles created through the config-flow API. Validate active users, prevent ownership transfers, and retain read-only, account-scoped discovery. Addresses #9.
- Preserve available GymKit machine duration, equipment name/model/manufacturer, steps and cadence units in workout storage, calendar descriptions and workout-card details. Cycling cadence displays in rpm. Supports #11 with compatible app uploads.
- Add regression tests for reload persistence, ownership repair and authorization, GymKit metadata, and workout-card rendering and escaping.

### Compatibility

- Update the integration through HACS and restart Home Assistant. The reload fix and ownership-repair action work with existing app builds.
- The iOS app is distributed separately. GymKit metadata export, per-workout retry isolation, calendar-first uploads and the metadata-only option require a compatible updated Halthy app; this integration release alone does not resolve the iOS preparation failures reported in #10 and #12.

## [0.2.2] - 2026-10-20

### Changed

- Declare Health & wellbeing (`health_wellbeing`) as Halthy's primary integration category, following Home Assistant's integration-category guidance.

### Fixed

- Build Hassfest from a pinned official Home Assistant Core revision that supports categories in custom integration manifests, keeping all validation checks enabled.

### Compatibility

- No iOS app update is required for this metadata change. Update the integration and restart Home Assistant.

## [0.2.1] - 2026-10-15

### Added

- Device info displays the installed Halthy integration version, explicitly labeled as Integration rather than the iPhone's OS version. All entity platforms share this metadata and existing devices update in place.

### Documentation

- Clarify that midnight rollover applies to new history after restart and does not rewrite previously recorded graphs.

### Compatibility

- No iOS rebuild is required for the Device info version display. Update the integration and restart Home Assistant.

## [0.2.0] - 2026-10-15

### Added

- Native Home Assistant sign-in discovery and optional per-device paired webhook uploads. Pairing, lookup and revocation remain authenticated and bound to the owning Home Assistant account and grant.
- Durable command acknowledgements and scoped workout-map transaction, inspection and archive-repair endpoints for compatible app builds.
- Independent midnight rollover for daily activity, energy, dietary, event, workout and Digital health totals, including catch-up after restart or reload and calendar/timezone-aware day boundaries.
- Freshness attributes distinguish local daily resets from phone uploads. First pickup time clears to unknown; sleep sessions and last medical measurements are preserved.
- Regression coverage for API/webhook delivery, daily rollover, historical retries, sensor compatibility and authentication using an isolated Home Assistant server.
- Resumable Home Assistant history range selection in the iOS app, with a backfill action and historical daily snapshots for sleep and cumulative metrics.
- Persistent sample aggregation across upload batches for accurate hourly Home Assistant statistics.

### Fixed

- Previous-day uploads and historical daily snapshots no longer restore yesterday's daily totals into today's live entities; historical samples remain eligible for statistics import.
- Completed sync receipts update Last full sync and Daily uploads independently of whether the payload contains changed readings. Calendar resets do not falsely count as uploads.
- Repair fragmented display names such as Handwashing, Swimming, Rowing and Skiing without renaming existing entity or statistics IDs.
- Keep workout-image replacement, archive repair and retries scoped to their destination and requested operation.
- Home Assistant incremental uploads no longer discard readings above a per-hour cap before advancing HealthKit sync anchors.

### Compatibility

- This is a stable integration release, not a prerelease. The separately distributed iPhone app remains available through TestFlight.
- Existing authenticated API uploads remain supported. Native sign-in, paired webhooks and correct daily event aggregation require a compatible updated Halthy app.
- Digital health retains Apple's device, region, OS and permission restrictions.
- Back up Home Assistant before upgrading, install the update and restart Home Assistant. Open the updated app and sync once. Existing recorder history is not rewritten by the midnight fix.

## [0.1.5-beta] - 2026-10-05

### Added

- Four Digital health sensors: screen time, longest activity session, first pickup time, and pickups without app use.
- Readable names, icons, and appropriate duration, timestamp, and count handling for the new sensors.
- Regression tests for uploads and selection-based sensor removal.

### Compatibility

- Requires an updated Halthy iOS build that uploads Digital health metrics and includes them in its selected-metrics payload. Older builds may remove these sensors during a regular HealthKit sync.

## [0.1.4-beta] - 2026-09-11

### Added

- Support for the iOS app's Awake, Core sleep, Deep sleep, and REM sleep duration metrics (`sleep_awake`, `sleep_core`, `sleep_deep`, and `sleep_rem`).
- Sleep-stage metrics use hours, Home Assistant's duration device class, and a suggested display precision of two decimal places.
- Regression tests for sleep-stage names, stable metric keys, selection management, units, and display precision.

### Compatibility

- Requires an iOS app version that uploads the new sleep-stage metrics. Enable the desired metrics in the app, update the integration, restart Home Assistant, and upload data.

## [0.1.3-beta] - 2026-09-09

### Fixed

- Last update, Last full sync, and the daily-upload diagnostic timestamp now use Home Assistant's upload-processing time rather than the newest measurement timestamp.
- Historical and duplicate samples can reach statistics import without replacing the latest live sensor state. Newer cursor values no longer suppress earlier backfills or retries.
- Recorder metadata includes units even for unitless statistics and uses the modern mean type when available.
- Release packaging now verifies both bundled brand icons. Added troubleshooting for HACS's separate public icon lookup and timestamp display formatting.

### Added

- Per-user **Go to bed time** (`go_to_bed_time`): start of the recorded in-bed interval associated with the selected sleep session.
- Per-user **Fall asleep time** (`fall_asleep_time`): first recorded asleep stage in that session.
- Per-user **Wake up time** (`wake_up_time`): end of the final recorded asleep stage in the same session.
- Missing recorded in-bed time is shown as unknown rather than estimated. Sleep timestamp sensors retain their timestamp device class when the value is unknown.
- Tests covering timestamp entities, overnight sleep stages, duplicate samples, brief awakenings, main-session selection, and missing in-bed records.

### Compatibility

- These sensors require both the updated integration and an updated iOS app that sends sleep-session timestamps. Earlier app versions send sleep durations without the required boundaries.
- Selecting a sleep metric in the updated app also enables the three timestamp sensors. They refresh on app uploads even if total sleep duration is unchanged.

## [0.1.2-beta] - 2026-09-05

### Changed

- Height sensors report centimetres by default and support Home Assistant unit selection and display precision.
- Body mass is displayed as Weight, with unit selection and display precision; existing entity IDs are preserved.
- Both sensors suggest one decimal place and preserve user-selected units and precision across uploads.

### Added

- Sensor regression tests using Home Assistant's unit conversion and saved entity options, included in CI.

## [0.1.1-beta] - 2026-09-04

### Added

- Safe migration for renamed usernames and archived workout images.
- Bounded workout-calendar metadata retention.
- Public release, security, and contribution documentation.
- Documentation for the iOS app's seven-day local trial and one-time lifetime-access purchase.
- Documentation for local PDF, CSV, and GPX health-data exports.
- Documentation for workout replay, shareable replay videos, Apple Weather enrichment, health insights, and configurable notifications.
- Documentation for workout-card image sharing and optional Save to Photos behavior.
- Workout-card option to show or hide heart-rate zones.

### Changed

- HACS releases use the published `halthy.zip` artifact.
- GitHub Actions use pinned revisions and explicit permissions.
- Configuration selector options support Home Assistant translations.
- Privacy documentation now covers WeatherKit requests, workout weather caching, replay videos, trend notifications, and the current entitlement model.
- Privacy documentation now covers add-only Photos access.

### Fixed

- HACS release packages now contain integration files at the archive root, preventing installation under `custom_components/halthy/custom_components/halthy`.
- Release-package validation rejects nested integration paths and development-only files before publishing.

## [0.1.0] - 2026-08-09

### Added

- Initial public release of the Halthy Home Assistant integration.
- Authenticated multi-user health metric uploads.
- Home Assistant sensors, recorder statistics, workout images, workout card,
  and per-user workout calendars.
- Optional activity logging and app command controls.

[Unreleased]: https://github.com/Mosher23/Halthy/compare/v0.2.2...HEAD
[0.2.2]: https://github.com/Mosher23/Halthy/compare/v0.2.1...v0.2.2
[0.2.1]: https://github.com/Mosher23/Halthy/releases/tag/v0.2.1
[0.2.0]: https://github.com/Mosher23/Halthy/releases/tag/v0.2.0
[0.1.5-beta]: https://github.com/Mosher23/Halthy/compare/v0.1.4-beta...v0.1.5-beta
[0.1.4-beta]: https://github.com/Mosher23/Halthy/releases/tag/v0.1.4-beta
[0.1.3-beta]: https://github.com/Mosher23/Halthy/releases/tag/v0.1.3-beta
[0.1.2-beta]: https://github.com/Mosher23/Halthy/releases/tag/v0.1.2-beta
[0.1.1-beta]: https://github.com/Mosher23/Halthy/releases/tag/v0.1.1-beta
[0.1.0]: https://github.com/Mosher23/Halthy/releases/tag/v0.1.0
