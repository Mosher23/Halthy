# Changelog

All notable changes to Halthy are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and the project uses [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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

[Unreleased]: https://github.com/Mosher23/Halthy/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/Mosher23/Halthy/releases/tag/v0.1.0
