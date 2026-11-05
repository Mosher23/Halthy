# Contributing to Halthy

Contributions are welcome through GitHub issues and pull requests.

## Before Opening a Pull Request

1. Create a branch from `main`.
2. Keep changes focused and include regression tests for behavior changes.
3. Do not commit access tokens, real health data, workout routes, private Home
   Assistant addresses, `.DS_Store`, or Xcode user data.
4. Run the local validation commands below.

```bash
python3 -m compileall -q custom_components
python3 -m unittest discover custom_components/halthy/tests -p 'test_*.py'
node --check custom_components/halthy/halthy-workout-card.js
node tests/workout_card_gymkit.test.cjs
git diff --check
```

Marketplace validation (using the HACS action) and Hassfest must pass before a change is released.

## Marketplace Compatibility

Halthy is listed in Home Assistant Marketplace, built into Home Assistant starting
with 2026.11. Keep the repository's `hacs.json`, `hacs/action` validation, and
`halthy.zip` release asset: Marketplace still uses these publishing interfaces.
The workflow and script paths containing `hacs` are retained for compatibility;
historical release notes retain the terminology used at the time.

Use Marketplace in current user-facing instructions. Keep HACS instructions
explicitly scoped to Home Assistant 2026.10 and earlier. First Marketplace
installs open the integration's config flow without a restart; updates still
require one. See the [Marketplace publishing documentation](https://contributors.home-assistant.io/marketplace/).

## Reporting Problems

Use GitHub Issues for reproducible defects and feature requests. Include the
Halthy version, Home Assistant version, relevant sanitized logs, and expected
behavior. Never post tokens or private health and location data.
