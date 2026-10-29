# Troubleshooting

## Unit-change repairs after v0.2.7

Version 0.2.7 removed the literal `count` unit from counters without migrating
their existing Recorder statistics metadata. Home Assistant treats `count` and
no unit as incompatible, so it creates a repair for each affected sensor and can
pause statistics for those sensors. This is a unit-label mismatch, not evidence
that your historical numbers are wrong.

The updated integration automatically repairs this metadata after Home Assistant
finishes starting, or when the integration is reloaded while HA is running.
It changes only `count`/`counts` to no unit for counters belonging to Halthy.
Short-term and long-term values, timestamps, entity IDs and user-selected names
remain unchanged. Separate `halthy:` statistics are checked too. Confirmed stale
unit-change repairs are removed; unrelated repairs, such as expired Xiaomi
authentication, are not touched. Take a normal Home Assistant backup before an
integration upgrade.

To preview or retry manually as an administrator:

1. Open **Tools → Actions** (**Developer Tools → Actions** on older versions).
2. Select **Halthy: Migrate counter statistics** (`halthy.migrate_counter_statistics`).
3. Optionally select a Halthy integration entry. Leave it empty to check all loaded profiles.
4. Enable **Preview only** and request an action response to list affected statistic IDs without changing anything.
5. Turn **Preview only** off and run the action to repair them. Repeating it is safe.

The response lists the migrated IDs or reports `no_changes`. A Recorder timeout
or failed write is not reported as a successful migration; retry once Recorder
is available. The tool does not rewrite raw state history or reconstruct
statistics that Home Assistant never compiled while the mismatch was active.

If fixing a repair manually, choose **Update the unit of the historic statistic
values … without converting**, not **Delete all old statistic data**. There is
no need to remove and recreate the integration or its sensors.

## App cannot find an existing profile after API setup

An entry created through Home Assistant's config-flow API may have no owner.
Discovery only returns profiles owned by the signed-in account and does not claim
profiles automatically.

As a Home Assistant administrator, open **Developer Tools → Actions** and run
**Halthy: Assign profile owner** (`halthy.assign_profile_owner`). Select the
Halthy integration entry and enter the intended Home Assistant user's ID as
`owner_user_id`. Then sign in again in Halthy. The target user must be active.
This action repairs an ownerless profile; it cannot transfer an already owned
profile to another user.

## A workout fails to upload

Updated app builds identify the workout date, type, preparation stage, named
error and attempt number in technical logs. Failed items are retained locally
and retried separately with backoff; later calendar records can still upload.
After three unsuccessful preparation attempts, a force-upload request reports
failure and acknowledges that result instead of staying unfinished. The failed
items and command evidence remain saved. **Recheck sources** makes normal-sync
items eligible for another retry; a new force-upload request starts a new export.

For calendar automation without maps, enable **Workout metadata only** under
**Settings → Home Assistant → Maps and appearance**. This skips route collection,
weather and rendering. Queued images and archive repairs remain retained and
paused. If an earlier force-upload request included images, it finishes as failed
without changing its original manifest; request a new force upload to use the
metadata-only policy. Data already uploaded to Home Assistant is retained.

## GymKit equipment details

Supported app builds preserve available machine distance, duration, equipment
name/model and workout measurements in calendar records even without a route.
Machine duration is shown separately from workout duration. Cycling cadence is
displayed in rpm. Missing optional measurements do not prevent the basic workout
from uploading.

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
