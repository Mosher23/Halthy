# Halthy Privacy Policy

Last updated: August 26, 2026

Halthy is an iPhone app that reads selected Apple Health data, displays health and workout information on the device, and can send selected data to services that the user configures, such as Home Assistant and InfluxDB.

Halthy is not a medical device and does not provide medical advice, diagnosis, or treatment.

## Summary

- Halthy does not operate a developer-controlled account system, analytics service, or health-data backend.
- The Halthy developer does not collect health, fitness, workout-route, usage, or diagnostic data through the app.
- Halthy does not sell personal information, use advertising identifiers, or track users across apps or websites.
- Health, workout, and route data stays on the device unless the user exports it or enables a destination that the user controls.
- Home Assistant and InfluxDB access tokens are stored in the iOS Keychain.
- The user controls Apple Health permissions and chooses which data types Halthy may read or write.

## Data Halthy Can Access

Depending on permissions and enabled features, Halthy can access:

- Selected HealthKit metrics, including activity, energy, distance, heart rate, blood oxygen, sleep, and related values.
- Workout details, including type, start and end times, duration, distance, active energy, speed, elevation, cadence, heart-rate samples, and available zone information.
- Workout-route locations, including latitude, longitude, altitude, timestamps, speed, and course when HealthKit provides them.
- A representative workout-route location and workout time used to request historical conditions from Apple Weather when weather enrichment is available.
- Home Assistant sensor values selected in an import mapping.
- Camera frames while the user is actively scanning a QR code used to fill destination configuration.
- App Store transaction information made available by StoreKit to verify the lifetime-access purchase on the device.

The camera image is processed for QR recognition and is not uploaded to the Halthy developer.

## How Data Is Used

Halthy uses data only to provide features selected by the user:

- Displaying local health statistics, charts, summaries, workouts, maps, and route replays.
- Enriching workout displays and generated route images with available workout-time conditions from Apple Weather.
- Creating a workout replay video for the user to review or share.
- Generating PDF, CSV, and optional GPX exports for the user to share through the iOS share sheet.
- Sending selected data to the user's Home Assistant instance.
- Sending selected raw data to the user's InfluxDB instance when enabled.
- Reading selected Home Assistant sensor values and writing mapped values to Apple Health after write permission is granted.
- Generating workout route images and uploading them to Home Assistant when enabled.
- Creating local notifications for enabled events, such as repeated synchronization failures or workout uploads.
- Creating optional local trend notifications based on changes from a recent on-device baseline.
- Determining the local trial period and StoreKit-verified lifetime-access status.

## Developer Data Collection

Halthy has no developer-operated server and does not include third-party analytics, advertising, tracking, or crash-reporting SDKs. The developer cannot access data sent to a Home Assistant or InfluxDB instance configured by the user.

For this reason, the app's current architecture does not collect data as Apple defines that term for App Store privacy disclosures: data is not transmitted in a way that allows the Halthy developer or an integrated third-party partner to access it beyond servicing a request.

If this architecture changes, this policy and the App Store privacy disclosures will be updated before the changed version is released.

## User-Directed Destinations

### Home Assistant

When enabled, Halthy sends selected health, workout, route, and synchronization data directly to the Home Assistant URL configured by the user, using the user's long-lived access token. Data retention and deletion in Home Assistant are controlled by the user and the user's Home Assistant configuration.

### InfluxDB

When enabled, Halthy sends selected raw HealthKit and optional workout-route data directly to the InfluxDB URL, organization, bucket, and measurement configured by the user. Data retention and deletion in InfluxDB are controlled by the user and the user's InfluxDB configuration.

### Apple Health

When the user enables an import mapping and grants write permission, Halthy can write a mapped Home Assistant value to the selected Apple Health data type. Apple Health data can be reviewed and deleted in the Health app.

### User Exports

Halthy can create local PDF, CSV, and GPX files containing selected health, workout, and precise route-location data. These files are shared only after the user starts an export and selects a destination in the iOS share sheet. The selected destination's privacy practices apply after the file is shared.

Halthy can also create a local workout replay video. The video is shared only after the user chooses a destination in the iOS share sheet.

## Apple Services

Halthy uses Apple system services including HealthKit, MapKit, WeatherKit, StoreKit, BackgroundTasks, notifications, and the iOS share sheet. When weather enrichment is available, WeatherKit receives a representative workout-route location and workout time to return historical conditions. On supported devices, Halthy can use Apple's Foundation Models framework to create summaries on the device. Halthy does not send the summary context to a Halthy-operated model or cloud service.

Apple may process information under Apple's own terms and privacy policy when its services are used. The Halthy developer does not receive that information through a Halthy backend.

## Local Storage and Security

Halthy stores app configuration and operational data in the app's local container, including:

- Destination URLs, usernames, selected metrics, import mappings, and preferences.
- HealthKit synchronization cursors, upload status, and pending upload queues.
- Cached health summaries, workouts, route data, workout weather, generated route images, replay videos, and export files while needed for app functionality or sharing.
- Local notification and troubleshooting information.

Home Assistant and InfluxDB access tokens and the local trial-start record are stored in the iOS Keychain using device-only protection. Network transfers to configured destinations require HTTPS.

## Retention and Deletion

Local cache and queue data is retained only as needed for configured app features and may be replaced or pruned as new data is processed. Export files are created in temporary local storage for sharing and are subject to iOS cleanup after use.

The user can:

- Revoke Halthy's HealthKit access in the Health app or iOS Settings.
- Disable Home Assistant, InfluxDB, background synchronization, notifications, route uploads, or import mappings in Halthy.
- Clear destination token fields before deleting the app.
- Delete the app to remove its local app container.
- Delete data previously sent to Home Assistant or InfluxDB in those systems.
- Review and delete data written to Apple Health in the Health app.

iOS Keychain items can persist after an app is deleted. Clearing the Home Assistant and InfluxDB token fields before deleting Halthy replaces the stored credentials with empty values. A local trial-start record may remain in Keychain to prevent a reinstall from restarting an expired trial.

Because Halthy has no developer backend or app accounts, the developer has no server-side health profile to retrieve or delete.

## Permissions and Choices

HealthKit read and write permissions are controlled by the user. Halthy requests access only for enabled functionality. The user can grant, deny, or later revoke individual data-type permissions through Apple Health and iOS privacy settings.

Camera and notification permissions are optional. Denying them disables only the related QR-scanning or notification feature.

## Children

Halthy is not directed to children under 13. The app does not knowingly collect children's personal information through a developer-operated service.

## Changes to This Policy

This policy may be updated when Halthy's features or data handling change. The date at the top identifies the latest revision. Material changes will be reflected in the app and App Store privacy disclosures as appropriate.

## Contact and Support

For support or privacy-policy questions, use the project issue tracker:

https://github.com/Mosher23/Halthy/issues

Do not include health data, workout routes, access tokens, private server addresses, or other sensitive information in a public issue.
