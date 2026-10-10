"""Build allowlisted public documents as static HTML, without runtime dependencies."""
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'public-pages'
DOCUMENTS = [
    ('getting-started', 'Getting started', 'Use Rally', 'Sign in, discover a market and follow a feed.'),
    ('trading', 'Trading', 'Use Rally', 'Routes, wallet requests and transaction confirmation.'),
    ('prediction-markets', 'Predictions', 'Use Rally', 'Monad future-price pools and settlement.'),
    ('algorithms', 'Algorithms', 'Use Rally', 'Ranking formulas, previews and paid access.'),
    ('community-tokens', 'Community tokens', 'Use Rally', 'Launches, beneficiaries, fee claims and revenue.'),
    ('agents', 'Agent integration', 'Build on Rally', 'Scoped OAuth, MCP publishing and media upload.'),
    ('architecture', 'Architecture', 'Build on Rally', 'Clients, application, workers and onchain contracts.'),
    ('api', 'API reference', 'Build on Rally', 'Reads, authenticated actions and exact transaction plans.'),
    ('android', 'Android', 'Build on Rally', 'Native client, wallet boundary and release behavior.'),
    ('development', 'Development', 'Build on Rally', 'Run from source, configuration and isolated checks.'),
    ('verification', 'Verification', 'Build on Rally', 'Receipt-backed records and the scope of each check.'),
]
SLUGS = {slug for slug, *_ in DOCUMENTS} | {'terms', 'privacy'}


def e(value):
    return html.escape(str(value), quote=True)


def safe_link(value):
    if value.startswith('../SECURITY.md'):
        return 'https://github.com/skew-labs/rally/blob/main/SECURITY.md'
    if value.startswith('../assets/'):
        return '/' + value[3:]
    match = re.fullmatch(r'([a-z-]+)\.md(#[a-zA-Z0-9_-]+)?', value)
    if match and match[1] in SLUGS:
        return ('/' if match[1] in {'terms', 'privacy'} else '/docs/') + match[1] + (match[2] or '')
    u = urlsplit(value)
    if u.scheme in {'https', 'http', 'mailto'} and not u.username and not u.password:
        return value
    if value.startswith('/') and not value.startswith('//') and not re.search(r'[\x00-\x20\\]', value):
        return value
    if re.fullmatch(r'#[a-zA-Z0-9_-]+', value):
        return value
    return None


def inline(text):
    tokens = []

    def token(markup):
        tokens.append(markup)
        return '\x00' + str(len(tokens) - 1) + '\x00'

    text = re.sub(r'`([^`]+)`', lambda m: token('<code>' + e(m[1]) + '</code>'), text)

    def link(m):
        target = safe_link(m[2])
        label = re.sub(r'\x00(\d+)\x00', lambda n: tokens[int(n[1])], e(m[1]))
        return token('<a href="' + e(target) + '">' + label + '</a>') if target else m[1]

    text = re.sub(r'\[([^\]]+)\]\(([^)]+)\)', link, text)
    text = e(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'(?<!\*)\*([^*]+)\*(?!\*)', r'<em>\1</em>', text)
    return re.sub(r'\x00(\d+)\x00', lambda m: tokens[int(m[1])], text)


def markdown(source):
    lines = source.splitlines()
    blocks, toc, seen = [], [], {}
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line:
            i += 1
            continue
        if line.startswith('```'):
            language = line[3:]
            code = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith('```'):
                code.append(lines[i])
                i += 1
            markup = '<pre><code>' + e('\n'.join(code)) + '</code></pre>'
            blocks.append('<details class="p-diagram"><summary>View component flow</summary>' + markup + '</details>' if language == 'mermaid' else markup)
            i += 1
            continue
        heading = re.match(r'^(#{1,4})\s+(.+)$', line)
        if heading:
            depth, title = len(heading[1]), heading[2]
            base = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
            seen[base] = seen.get(base, 0) + 1
            ident = base if seen[base] == 1 else base + '-' + str(seen[base])
            blocks.append(f'<h{depth} id="{e(ident)}">{inline(title)}</h{depth}>')
            if depth == 2:
                toc.append((ident, title))
            i += 1
            continue
        if line.startswith('|') and i + 1 < len(lines) and re.fullmatch(r'[\s|:\-]+', lines[i + 1]):
            headers = line.strip('|').split('|')
            rows = []
            i += 2
            while i < len(lines) and lines[i].strip().startswith('|'):
                rows.append(lines[i].strip().strip('|').split('|'))
                i += 1
            blocks.append('<div class="p-table-wrap" role="region" aria-label="Reference table" tabindex="0"><table><thead><tr>' + ''.join('<th scope="col">' + inline(c.strip()) + '</th>' for c in headers) + '</tr></thead><tbody>' + ''.join('<tr>' + ''.join('<td>' + inline(c.strip()) + '</td>' for c in row) + '</tr>' for row in rows) + '</tbody></table></div>')
            continue
        marker = re.match(r'^(?:([-*])|\d+\.)\s+(.+)$', line)
        if marker:
            ordered = not marker[1]
            tag, items = ('ol' if ordered else 'ul'), []
            while i < len(lines):
                item = re.match(r'^(?:([-*])|\d+\.)\s+(.+)$', lines[i].strip())
                if not item or bool(not item[1]) != ordered:
                    break
                items.append('<li>' + inline(item[2]) + '</li>')
                i += 1
            blocks.append('<' + tag + '>' + ''.join(items) + '</' + tag + '>')
            continue
        paragraph = [line]
        i += 1
        while i < len(lines) and lines[i].strip() and not re.match(r'^(?:#{1,4}\s|```|\||[-*]\s|\d+\.\s)', lines[i].strip()):
            paragraph.append(lines[i].strip())
            i += 1
        blocks.append('<p>' + inline(' '.join(paragraph)) + '</p>')
    return '\n'.join(blocks), toc


def nav(current, mobile=False):
    entries = [('index', 'Overview', 'Use Rally', '')] + DOCUMENTS + [('terms', 'Terms of Service', 'Legal', ''), ('privacy', 'Privacy Policy', 'Legal', '')]
    result, group = [], None
    for slug, title, category, _ in entries:
        if category != group and not mobile:
            result.append('<span class="p-nav-group">' + e(category) + '</span>')
        group = category
        path = '/docs' if slug == 'index' else '/' + slug if slug in {'terms', 'privacy'} else '/docs/' + slug
        result.append('<a href="' + path + '"' + (' aria-current="page"' if slug == current else '') + '>' + e(title) + '</a>')
    return '<nav aria-label="' + ('Mobile documentation' if mobile else 'Documentation') + '">' + ''.join(result) + '</nav>'


def page(slug, title, description, body, toc):
    path = '/docs' if slug == 'index' else '/' + slug if slug in {'terms', 'privacy'} else '/docs/' + slug
    css = hashlib.sha256((ROOT / 'public-docs.css').read_bytes()).hexdigest()[:12]
    js = hashlib.sha256((ROOT / 'public-docs.js').read_bytes()).hexdigest()[:12]
    sections = ''.join('<a href="#' + e(ident) + '">' + e(label) + '</a>' for ident, label in toc)
    crumb = 'Legal' if slug in {'terms', 'privacy'} else 'Documentation'
    return f'''<!doctype html>
<html lang="en" data-theme="light"><head>
<meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="theme-color" content="#f6f5f9" /><meta name="description" content="{e(description)}" />
<meta property="og:title" content="{e(title)} · Rally" /><meta property="og:description" content="{e(description)}" /><meta property="og:type" content="website" /><meta property="og:url" content="https://rallydot.com{path}" />
<link rel="canonical" href="https://rallydot.com{path}" /><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml" />
<link rel="preload" href="/assets/landing-manrope.woff2" as="font" type="font/woff2" crossorigin /><script src="/theme.js"></script>
<link rel="stylesheet" href="/public-docs.css?v={css}" /><title>{e(title)} · Rally</title></head><body>
<a class="p-skip" href="#main">Skip to content</a>
<header class="p-header"><a class="p-brand" href="/" aria-label="Rally home">rally<span>.</span></a><nav class="p-header-links" aria-label="Main navigation"><a href="/docs"{' aria-current="page"' if slug not in {'terms','privacy'} else ''}>Docs</a><a href="https://github.com/skew-labs/rally">GitHub</a><button type="button" class="p-theme" aria-label="Switch to dark mode"><svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M20.6 14A8.7 8.7 0 0 1 10 3.4 8.7 8.7 0 1 0 20.6 14Z"/></svg></button><a class="p-launch" href="/app">Launch app</a></nav></header>
<div class="p-shell"><aside class="p-sidebar">{nav(slug)}</aside><main class="p-article" id="main"><details class="p-mobile-nav"><summary>Browse documentation</summary>{nav(slug, True)}</details><p class="p-breadcrumb"><a href="/docs">Rally</a> / {crumb}</p>{body}<div class="p-next"><a href="/app">Open Rally</a><span>Questions? <a href="mailto:skewlabs@skew.deals">Contact support</a></span></div></main><aside class="p-toc" aria-label="On this page"><p>On this page</p>{sections}</aside></div>
<footer class="p-footer"><a class="p-brand" href="/" aria-label="Rally home">rally<span>.</span></a><nav aria-label="Footer"><a href="/docs">Docs</a><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="mailto:skewlabs@skew.deals">Support</a></nav></footer>
<script type="module" src="/public-docs.js?v={js}"></script></body></html>'''


def build():
    OUTPUT.mkdir(exist_ok=True)
    overview = '<h1 id="rally-documentation">Rally documentation</h1><p>Social discovery, community tokens and algorithm markets on Monad.</p><p>Learn how to use Rally, connect an agent and understand what happens between a post, a wallet request and an onchain result.</p><div class="p-model" aria-label="Rally product flow"><span>Discover</span><b aria-hidden="true">→</b><span>Discuss</span><b aria-hidden="true">→</b><span>Trade</span><b aria-hidden="true">→</b><span>Create</span></div>'
    for group in ['Use Rally', 'Build on Rally']:
        ident = group.lower().replace(' ', '-')
        overview += '<h2 id="' + ident + '">' + group + '</h2><ul class="p-overview-links">' + ''.join('<li><a href="/docs/' + slug + '">' + e(title) + '</a><span>' + e(description) + '</span></li>' for slug, title, category, description in DOCUMENTS if category == group) + '</ul>'
    overview += '<h2 id="legal-and-support">Legal and support</h2><p>Read our <a href="/terms">Terms of Service</a> and <a href="/privacy">Privacy Policy</a>, or contact <a href="mailto:skewlabs@skew.deals">support</a>.</p>'
    (OUTPUT / 'index.html').write_text(page('index', 'Documentation', 'User guides and architecture for Rally on Monad.', overview, [('use-rally', 'Use Rally'), ('build-on-rally', 'Build on Rally'), ('legal-and-support', 'Legal and support')]))
    for slug, title, _, description in DOCUMENTS + [('terms', 'Terms of Service', 'Legal', 'Rally account, content, trading and creator-service terms.'), ('privacy', 'Privacy Policy', 'Legal', 'How Rally processes account, social, wallet and authorization data.')]:
        body, toc = markdown((ROOT / 'docs' / (slug + '.md')).read_text())
        (OUTPUT / (slug + '.html')).write_text(page(slug, title, description, body, toc))
    print(json.dumps({'pages': len(DOCUMENTS) + 3, 'output': 'public-pages', 'runtimeDependencies': 0}))


if __name__ == '__main__':
    build()
