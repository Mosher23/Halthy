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
git diff --check
```

HACS validation and Hassfest must pass before a change is released.

## Reporting Problems

Use GitHub Issues for reproducible defects and feature requests. Include the
Halthy version, Home Assistant version, relevant sanitized logs, and expected
behavior. Never post tokens or private health and location data.
