#!/usr/bin/env python3
"""Dependency-free website checks, including the iOS OAuth client-page contract."""
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import unquote, urlsplit
import sys
import json
from datetime import date
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
DOCS = ROOT / 'docs'
PAGES = ('index.html', 'documentation.html', 'support.html', 'privacy.html', 'changelog.html')
SITE = 'https://mosher23.github.io/Halthy/'
checks = 0


def check(condition, message):
    global checks
    checks += 1
    if not condition:
        raise AssertionError(message)


class Page(HTMLParser):
    def __init__(self, text):
        super().__init__(convert_charrefs=True)
        self.tags = []
        self.ids = []
        self.links = []
        self.feed(text)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        self.tags.append((tag, attrs))
        if 'id' in attrs:
            self.ids.append(attrs['id'])
        if 'href' in attrs and attrs.get('rel') != 'redirect_uri':
            self.links.append(attrs['href'])
        if 'src' in attrs:
            self.links.append(attrs['src'])
        if 'srcset' in attrs:
            self.links.extend(part.strip().split()[0] for part in attrs['srcset'].split(','))


def validate():
    parsed = {name: Page((DOCS / name).read_text()) for name in PAGES}
    for name, page in parsed.items():
        text = (DOCS / name).read_text()
        tags = page.tags
        check(len(page.ids) == len(set(page.ids)), f'{name}: duplicate IDs')
        check(sum(tag == 'h1' for tag, _ in tags) == 1, f'{name}: needs one h1')
        check(sum(tag == 'main' for tag, _ in tags) == 1, f'{name}: needs one main')
        check('main' in page.ids, f'{name}: skip-link target missing')
        check(any(tag == 'html' and attrs.get('lang') == 'en' for tag, attrs in tags), f'{name}: language missing')
        check('<title>Halthy' in text, f'{name}: title missing')
        for meta in ('description', 'viewport', 'referrer'):
            check(any(tag == 'meta' and attrs.get('name') == meta and attrs.get('content') for tag, attrs in tags), f'{name}: {meta} missing')
        expected = SITE + ('' if name == 'index.html' else name)
        check(any(tag == 'link' and attrs.get('rel') == 'canonical' and attrs.get('href') == expected for tag, attrs in tags), f'{name}: incorrect canonical URL')
        check(not any(tag in ('script', 'form', 'iframe', 'input', 'object', 'embed') for tag, _ in tags), f'{name}: unexpected active content')
        csp = [attrs.get('content', '') for tag, attrs in tags if tag == 'meta' and attrs.get('http-equiv', '').lower() == 'content-security-policy']
        check(len(csp) == 1, f'{name}: CSP missing')
        for directive in ("default-src 'none'", "img-src 'self'", "style-src 'self'", "base-uri 'none'", "form-action 'none'"):
            check(directive in csp[0], f'{name}: CSP missing {directive}')
        for tag, attrs in tags:
            check(not any(attr.startswith('on') for attr in attrs), f'{name}: inline handler')
            if tag == 'img':
                check('alt' in attrs and attrs.get('width') and attrs.get('height'), f'{name}: image needs alt and dimensions')
            if tag in ('img', 'link') and ('src' in attrs or attrs.get('rel') == 'stylesheet'):
                check(not urlsplit(attrs.get('src', attrs.get('href', ''))).scheme, f'{name}: remote asset')
        for link in page.links:
            url = urlsplit(link)
            check(url.scheme in ('', 'https', 'mailto'), f'{name}: unsafe link {link}')
            if url.scheme:
                continue
            check(not url.netloc, f'{name}: protocol-relative link')
            target = DOCS / unquote(url.path or name)
            if target.is_dir():
                target /= 'index.html'
            check(target.resolve().is_relative_to(DOCS.resolve()), f'{name}: link escapes site')
            check(target.is_file(), f'{name}: missing file {link}')
            if url.fragment and target.suffix == '.html':
                target_page = parsed.get(target.name)
                check(target_page is not None and unquote(url.fragment) in target_page.ids, f'{name}: missing anchor {link}')

    homepage = (DOCS / 'index.html').read_bytes()
    declaration = b'<link rel="redirect_uri" href="halthy-ha://auth/callback">'
    check(len(homepage) < 32 * 1024, 'Homepage exceeds iOS client-page response limit')
    check(declaration in homepage[:10_000], 'OAuth redirect declaration missing from first 10,000 bytes')
    check(homepage[:10_000].decode('utf-8') is not None, 'iOS response prefix is not valid UTF-8')
    check(homepage.count(declaration) == 1, 'Ambiguous OAuth callback declaration')
    check((DOCS / '.nojekyll').exists(), 'Static-site marker missing')
    check('halthy-ha://auth/callback' in (ROOT.parent / 'iOS app/Halthy/HomeAssistantSignIn.swift').read_text() if (ROOT.parent / 'iOS app/Halthy/HomeAssistantSignIn.swift').exists() else True, 'App callback mismatch')
    check('tsdeveloper@pm.me' in (DOCS / 'support.html').read_text(), 'Support contact missing')
    policy = (DOCS / 'privacy.html').read_text()
    for heading in ('Developer Data Collection', 'User-Directed Destinations', 'Retention and Deletion', 'Permissions and Choices', 'Children', 'Contact and Support'):
        check(heading in policy, f'Privacy section missing: {heading}')
    sitemap = ET.parse(DOCS / 'sitemap.xml')
    locations = {entry.text for entry in sitemap.findall('.//{http://www.sitemaps.org/schemas/sitemap/0.9}loc')}
    check(locations == {SITE, *(SITE + name for name in PAGES[1:])}, 'Sitemap does not match public pages')
    releases = json.loads((DOCS / 'releases.json').read_text())['releases']
    versions = [release['version'] for release in releases]
    check(len(versions) == len(set(versions)), 'Duplicate app release version')
    release_dates = [date.fromisoformat(release['date']) for release in releases]
    check(release_dates == sorted(release_dates, reverse=True), 'Releases must be newest first')
    changelog = (DOCS / 'changelog.html').read_text()
    for release in releases:
        version, status = release['version'], release['status']
        check(status in ('planned', 'released'), f'{version}: unknown release status')
        check(f'v{version.replace(".", "-")}' in parsed['changelog.html'].ids, f'{version}: release anchor missing')
        check(f'datetime="{release["date"]}"' in changelog, f'{version}: release date missing')
        check(release['date_label'] in changelog, f'{version}: visible release date missing')
        check(status != 'planned' or release['label'] == 'Planned release', f'{version}: planned release must be clearly labelled')
        check(bool(release['groups']) and all(group['items'] for group in release['groups']), f'{version}: release notes empty')
    for name, page in parsed.items():
        check('changelog.html' in page.links, f'{name}: changelog navigation missing')
    css = (DOCS / 'assets/site.css').read_text()
    check('prefers-reduced-motion' in css, 'Reduce Motion support missing')
    check(':focus-visible' in css, 'Keyboard focus styling missing')
    check('@media(max-width:420px)' in css, 'Small-screen layout missing')
    for path in DOCS.joinpath('assets').glob('*.webp'):
        data = path.read_bytes()
        check(data[:4] == b'RIFF' and data[8:12] == b'WEBP', f'Invalid WebP: {path.name}')
        check(len(data) < 250_000, f'Image unexpectedly large: {path.name}')
    print(f'Passed {checks} website checks. Homepage: {len(homepage):,} bytes; OAuth declaration preserved.')


if __name__ == '__main__':
    try:
        validate()
    except (AssertionError, UnicodeDecodeError, ET.ParseError) as error:
        print(f'Website validation failed: {error}', file=sys.stderr)
        sys.exit(1)
