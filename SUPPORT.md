# Halthy Support

Help with the Halthy iPhone app and its Home Assistant companion integration.

Last updated: 26 October 2026.

## Contact

- **Email support:** [tsdeveloper@pm.me](mailto:tsdeveloper@pm.me)
- **Report a bug or request a feature:** [GitHub Issues](https://github.com/Mosher23/Halthy/issues)
- **Integration setup:** [Home Assistant integration documentation](https://github.com/Mosher23/Halthy/blob/main/custom_components/halthy/README.md)
- **Privacy:** [Halthy Privacy Policy](https://github.com/Mosher23/Halthy/blob/main/PRIVACY.md)

Use email for private support, purchase questions, or privacy concerns. GitHub issues are public and require a GitHub account to submit. Email support does not require a GitHub account.

Do not send passwords, access tokens, webhook URLs, private server addresses, or identifiable health and workout data. The developer does not need your Home Assistant or InfluxDB credentials to help troubleshoot.

## Before Reporting a Problem

1. Check that Halthy and, if used, the Halthy Home Assistant integration are up to date. Restart Home Assistant after updating the integration.
2. Open Halthy with the iPhone unlocked and check the selected metrics and Apple Health permissions under **Settings > Health access**. Workouts and routes need their corresponding permissions and recorded data.
3. If you use Home Assistant or InfluxDB, check network access and run **Test connection** in that destination's settings. Review the displayed result and any explanation.
4. Try a manual upload and review **Settings > Logs** for errors. Older app versions may call this section **Log** or **Sync log**.

Home Assistant and InfluxDB are optional. The local dashboard, health charts, workout views, and file exports do not require either server.

## Common Questions

### Background uploads are delayed

iOS controls when Halthy can run in the background. Enable background upload in Halthy and check the app's Background App Refresh permission in iPhone Settings. Low Power Mode, network availability, and system scheduling can delay work. Some HealthKit data is unavailable while the iPhone is locked.

Background uploads are best effort, not a guarantee of continuous execution or uploads at a fixed interval. Open the app with the iPhone unlocked and use a manual upload when you need an immediate attempt. Historical imports may continue over multiple syncs.

### Home Assistant does not connect or update

Confirm that the Halthy integration is installed, Home Assistant has been restarted after installation or updates, and the configured HTTPS server address is reachable from the iPhone.

For token-based setup, check that the token is valid and the app username matches the Halthy integration profile. For native sign-in or paired webhook delivery, review the saved connection and pairing in Halthy. Keep webhook URLs private. Follow any sign-in or recovery instructions shown by the app rather than repeatedly creating new pairings.

Home Assistant entity states show current readings; they are not a complete raw sample history. Historical imports can require multiple upload passes. See the integration documentation for statistics and retention behavior.

### InfluxDB data is missing

Check the HTTPS address, organization, bucket, measurement, and token permissions in **Settings > InfluxDB**. Confirm that the desired health metrics and export options are selected. Run its connection test, then try a manual upload. A current snapshot and a historical sample import are different operations, so inspect the logs before assuming the full history has completed.

### A health metric, sleep value, or workout route is missing

Check that the corresponding record exists in Apple Health and that Halthy has permission to read it. Apple does not reveal individual read-permission decisions to apps, so review permissions in Apple Health if needed.

Some sources deliver or revise measurements after the activity has finished. A later upload can therefore update sleep totals or other recorded values. Workout maps and GPX exports require an available workout route, not just a workout summary.

### Digital Health is unavailable

Digital Health is optional and uses separate Screen Time data-access permission. It requires iOS 26.4 or later, a device in the EU, and an EU Apple Account. Availability is determined by Apple's authorization system; selecting an EU language or region in the app does not enable access.

### Trial, Lifetime Access, or restoring a purchase

Halthy offers a seven-day trial that you start yourself and a one-time Lifetime Access purchase. It is not a subscription, and the trial does not automatically charge you.

If you have already purchased Lifetime Access, use **Restore Purchase** with the Apple Account used for the purchase. Contact support if access is not restored. Never post payment details or receipts in a public issue.

## Information to Include in a Support Request

- Halthy app version and build number.
- iPhone model and iOS version.
- Home Assistant integration version and Home Assistant version, or InfluxDB version, if relevant.
- Whether the problem happens with the app open, in the background, or both.
- The connection method used, if relevant: sign-in, access token, or paired webhook. Do not include the credential itself.
- Approximate time of the issue, including your time zone.
- Steps to reproduce it, what you expected, and what happened instead.
- The visible error message or a screenshot with personal information removed.

### Exporting a Diagnostic Log

In recent versions, open **Settings > Logs** and use the share/export button to generate a timestamped CSV debug log. Review the file before sharing it. Remove private information, health values, workout locations, credentials, and server details. Share only the minimum information needed to explain the problem.

Do not attach health-data CSV/PDF exports or workout GPX files to a public issue. Those are different from a diagnostic log and may contain sensitive health or location data.

## Privacy Requests

Halthy does not operate a health-data backend or Halthy user accounts. App data is stored on your device; data you export or sync is controlled by the destinations you choose. The developer cannot retrieve or delete records from your Apple Health store, Home Assistant instance, or InfluxDB instance.

For privacy questions, email [tsdeveloper@pm.me](mailto:tsdeveloper@pm.me) without including health records or credentials. See the [Privacy Policy](https://github.com/Mosher23/Halthy/blob/main/PRIVACY.md) for data handling and deletion information.

Halthy is not a medical device and does not provide medical advice, diagnosis, or treatment.
