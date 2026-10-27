# Halthy website

GitHub Pages publishes the `docs/` directory on `main` at
<https://mosher23.github.io/Halthy/>. Keep the existing Deploy from a branch
configuration; no framework, npm install, backend, credentials or runtime scripts
are needed.

## Editing

- Landing page: `docs/index.html`.
- Shared design and responsive layouts: `docs/assets/site.css`.
- Guide source: `docs/guide.md`.
- Support source: repository-root `SUPPORT.md`.
- Privacy source: repository-root `PRIVACY.md`.
- Regenerate the three document pages with
  `ruby .github/scripts/build_site_documents.rb` after source, header or footer edits.
- Validate with `ruby .github/scripts/build_site_documents.rb --check` and
  `python3 .github/scripts/check_site.py`.
- Preview with `python3 -m http.server 8080 --directory docs`.

The privacy policy is reproduced from the source document without rewriting its
wording. Website-hosting information is a separately labelled note. Don't edit
the generated document HTML directly.

## Sign-in compatibility

The iOS app uses the homepage as its public OAuth client identity. Preserve the
exact declaration below in the first 10,000 bytes, and keep the complete HTML
response below 32 KiB. The validator enforces these bounds, including valid UTF-8
at the iOS prefix boundary.

```html
<link rel="redirect_uri" href="halthy-ha://auth/callback">
```

Never collect or relay codes, tokens or credentials here. External scripts,
analytics and forms are deliberately absent. The Content Security Policy permits
only same-origin images and styles. No change to the iOS app or integration
runtime is required to publish website-only changes.

## Artwork

The website reuses the approved Halthy 1.1 App Store Graphite artwork, including
its workouts / health / export header and blue Home Assistant capability badge.
The three portrait screenshots and the two hero screens use synthetic demo
values and a demonstration route, not personal health or location data. The
header and screenshots preserve Apple Maps and Weather attribution.

Images are optimized WebP copies of the approved PNGs, resized without cropping
or stretching. `app-icon.png` retains Halthy's existing icon. Source assets remain
in the private app workspace; do not publish private app sources, personal
screenshots, debug exports or credentials to this repository.

The gallery opens each image directly for enlargement. Documentation is usable
without JavaScript, keyboard navigation has focus indicators, motion respects
Reduce Motion, and narrow screens use a stacked reading layout.
