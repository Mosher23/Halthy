# Timestamps, statistics, and integration icons

## Sleep timestamps and local time

Sleep timestamps are stored in UTC and exposed as Home Assistant timestamp sensors, not text. For example, `2026-09-08T21:24:40Z` is **September 8, 2026 at 23:24** in Europe/Berlin. Do not manually add two hours: the offset changes with daylight saving time.

If the dashboard shows the literal ISO string ending in `Z`, check the installed integration version. The `v0.1.2-beta` release predates support for sleep timestamp device classes, even though newer code was already available on `main`. Install a release containing the fix and restart Home Assistant. In Developer Tools > States, the sleep entities should have `device_class: timestamp`. Check your Home Assistant/user-profile timezone settings too.

To request an absolute date and time instead of a relative value, use an Entities card. Replace `tester1` with your username:

```yaml
type: entities
entities:
  - entity: sensor.tester1_go_to_bed_time
    time_format: datetime
  - entity: sensor.tester1_fall_asleep_time
    time_format: datetime
  - entity: sensor.tester1_wake_up_time
    time_format: datetime
```

The exact language, date style, and 12/24-hour clock follow the frontend settings. On older frontend versions, the equivalent row setting is `format: datetime`. The integration cannot force a particular date format across every dashboard card without turning the sensor into plain text.

See the [Home Assistant Entities card documentation](https://www.home-assistant.io/dashboards/entities/).

## Sync diagnostics in the future

Earlier versions copied the newest uploaded measurement timestamp into Last update and Last full sync. Future-dated samples, or samples timestamped at a reporting interval's end, could therefore make these diagnostics appear in the future.

These diagnostics now use Home Assistant's processing time for an accepted upload. Last full sync still requires a full upload that applies at least one change. Existing diagnostic values are corrected on the next qualifying upload; historical recorder entries are not rewritten.

## Missing halthy statistics

Enable historical statistics in the integration options for the relevant user. Select `halthy:<username>_<metric>` as a statistic ID, not as a live `sensor.*` entity. External statistics have hourly resolution.

Historical samples and retries now reach statistics processing even when they are too old to replace the live sensor state or are duplicates of that state. A newer statistics cursor no longer blocks backfilling an earlier period. Recorder upserts rows by statistic ID and hour; statistics remain hourly summaries of the samples supplied in each batch, not a raw-sample archive.

After updating, resend the missing history from the app. The integration cannot recover data it never received. If the series remains missing, include the Home Assistant version, whether statistics are enabled for that person, the affected statistic ID, and recorder/Halthy error messages with your report. A successful queue submission is not proof that the recorder database write has completed.

## Icon missing in the HACS repository list

The installation ZIP includes `brand/icon.png` and `brand/icon@2x.png`. Package validation requires both. Home Assistant supports local custom-integration brand images starting with 2026.3.

The HACS frontend version investigated still requests repository-list icons from `brands.home-assistant.io`. Halthy's public icon currently returns 404, so that listing can show a placeholder even when the local integration icon is installed correctly. Adding another image to this repository or changing the README does not change that external lookup.

Resolving that listing requires a HACS version supporting local brand images or an accepted public brands entry. Halthy cannot replace HACS's icon URL from its own manifest. For the installed integration's icon, use Home Assistant 2026.3 or newer and restart after installation.

See [Home Assistant brand-image documentation](https://developers.home-assistant.io/docs/core/integration/brand_images/).
