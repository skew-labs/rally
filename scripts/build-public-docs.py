"""Build allowlisted public documents as static HTML, without runtime dependencies."""
import hashlib
import html
import json
import re
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / 'public-pages'
# Public guides are edited separately from the repository's implementation docs.
# (slug, title, navigation group, description, Markdown source)
DOCUMENTS = [
    ('getting-started', 'Getting started', 'Essentials', 'Connect an account and make your first trade.', 'site/getting-started'),
    ('wallets', 'Wallets & transfers', 'Essentials', 'Connect, deposit, send and understand your balance.', 'site/wallets'),
    ('android', 'Android app', 'Essentials', 'Install Rally and use the same account on mobile.', 'site/android'),
    ('spot', 'Spot', 'Trading', 'Buy and sell tokens through routes on Monad.', 'site/spot'),
    ('memes', 'Meme tokens', 'Trading', 'Discover launches, curves and graduated tokens.', 'site/memes'),
    ('perps', 'Perpetuals', 'Trading', 'Collateral, long and short orders, and positions.', 'site/perps'),
    ('prediction-markets', 'Price predictions', 'Trading', 'Enter and settle eligible future-price pools.', 'site/prediction-markets'),
    ('trading', 'Order status', 'Trading', 'Follow your order from a quote to its result.', 'site/trading'),
    ('fees', 'Fees & costs', 'Trading', 'Network gas, venue fees and subscription prices.', 'site/fees'),
    ('social', 'Feeds & communities', 'Social & creators', 'Post, discover and participate in a community.', 'site/social'),
    ('social-loop', 'Signals & benefits', 'Social & creators', 'Verified signals, shared fills, token benefits and weekly contests.', 'site/social-loop'),
    ('algorithms', 'Feed algorithms', 'Social & creators', 'Preview, subscribe to and publish a feed algorithm.', 'site/algorithms'),
    ('community-tokens', 'Community tokens', 'Social & creators', 'Launch a token and connect its revenue policy.', 'site/community-tokens'),
    ('agents', 'Connected agents', 'Social & creators', 'Connect an external agent with scoped permissions.', 'site/agents'),
    ('faq', 'FAQ', 'Help', 'Answers to common account and trading questions.', 'site/faq'),
    ('architecture', 'Architecture', 'Developers', 'Clients, application, workers and onchain contracts.', 'architecture'),
    ('api', 'API reference', 'Developers', 'Reads, authenticated actions and exact transaction plans.', 'api'),
    ('agent-api', 'OAuth & MCP', 'Developers', 'Scopes, authorization, publishing and media upload.', 'agents'),
    ('development', 'Local development', 'Developers', 'Run from source and configure an isolated deployment.', 'development'),
    ('verification', 'Execution & verification', 'Developers', 'Receipt-backed state and verification boundaries.', 'verification'),
]
LEGAL = [
    ('terms', 'Terms of Service', 'Legal', 'Rally account, content, trading and creator-service terms.', 'terms'),
    ('privacy', 'Privacy Policy', 'Legal', 'How Rally processes account, social, wallet and authorization data.', 'privacy'),
]
SLUGS = {slug for slug, *_ in DOCUMENTS + LEGAL} | {'developers'}


def route(slug):
    return '/docs' if slug == 'index' else '/' + slug if slug in {'terms', 'privacy'} else '/docs/' + slug


def icon(name):
    paths = {
        'search': '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4.5 4.5"/>',
        'menu': '<path d="M4 6h16M4 12h16M4 18h16"/>',
        'close': '<path d="m6 6 12 12M18 6 6 18"/>',
        'arrow': '<path d="M5 12h14m-5-5 5 5-5 5"/>',
        'chevron': '<path d="m9 5 7 7-7 7"/>',
        'link': '<path d="m9 15 6-6m-7 3-2 2a4 4 0 0 0 6 6l2-2m-2-4 2-2a4 4 0 0 0-6-6L6 8"/>',
        'book': '<path d="M12 5c-3-2-6-2-9-1v15c3-1 6-1 9 1 3-2 6-2 9-1V4c-3-1-6-1-9 1Zm0 0v15"/>',
        'wallet': '<rect x="3" y="5" width="18" height="15" rx="3"/><path d="M3 8h18m-4 4h4v5h-4a2.5 2.5 0 0 1 0-5Z"/>',
        'chart': '<path d="M4 3v17h17M7 14l4-4 4 2 5-7"/>',
        'community': '<circle cx="9" cy="8" r="3"/><path d="M3 20v-2a6 6 0 0 1 12 0v2m1-15a3 3 0 0 1 0 6m2 4a5 5 0 0 1 3 5"/>',
        'code': '<path d="m8 6-6 6 6 6m8-12 6 6-6 6m-3-15-2 18"/>',
    }
    return '<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">' + paths[name] + '</svg>'


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


def component_diagram(code):
    """Render the documented component groups without a Mermaid runtime."""
    groups, current = [], None
    for line in code:
        match = re.match(r'\s*subgraph\s+([A-Za-z ]+)', line)
        if match:
            current = [match[1], []]
            groups.append(current)
        elif line.strip() == 'end':
            current = None
        elif current is not None:
            node = re.match(r'\s*\w+\[\(?(.+?)\)?\]', line)
            if node:
                current[1].append(node[1])
    if not groups:
        return '<pre><code>' + e('\n'.join(code)) + '</code></pre>'
    return '<figure class="p-diagram" aria-label="Rally system components"><div class="p-diagram-grid">' + ''.join('<section><h3>' + e(name) + '</h3><ul>' + ''.join('<li>' + e(label) + '</li>' for label in nodes) + '</ul></section>' for name, nodes in groups) + '</div><figcaption>Clients connect to the application over HTTPS. Workers update indexed state. Wallets submit onchain actions; the application reconciles their results from Monad.</figcaption></figure>'


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
            markup = '<div class="p-code"><div class="p-code-bar"><span>' + e(language or 'Code') + '</span><button type="button" data-copy-code aria-label="Copy code">Copy</button></div><pre><code>' + e('\n'.join(code)) + '</code></pre></div>'
            blocks.append(component_diagram(code) if language == 'mermaid' else markup)
            i += 1
            continue
        heading = re.match(r'^(#{1,4})\s+(.+)$', line)
        if heading:
            depth, title = len(heading[1]), heading[2]
            base = re.sub(r'[^a-z0-9]+', '-', title.lower()).strip('-')
            seen[base] = seen.get(base, 0) + 1
            ident = base if seen[base] == 1 else base + '-' + str(seen[base])
            anchor = '' if depth == 1 else '<a class="p-heading-anchor" href="#' + e(ident) + '" aria-label="Link to ' + e(title) + '">#</a>'
            blocks.append(f'<h{depth} id="{e(ident)}">{inline(title)}{anchor}</h{depth}>')
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


def developer(slug):
    return slug == 'developers' or any(d[0] == slug and d[2] == 'Developers' for d in DOCUMENTS)


def nav(current, mobile=False):
    is_dev = developer(current)
    entries = [('developers', 'Overview', 'Build on Rally', '', '')] if is_dev else [('index', 'Introduction', 'Essentials', '', '')]
    entries += [d for d in DOCUMENTS if (d[2] == 'Developers') == is_dev]
    result, group = [], None
    for slug, title, category, _, _ in entries:
        if category != group:
            result.append('<span class="p-nav-group">' + e(category) + '</span>')
        group = category
        result.append('<a href="' + route(slug) + '"' + (' aria-current="page"' if slug == current else '') + '>' + e(title) + '</a>')
    return '<nav aria-label="' + ('Mobile documentation' if mobile else 'Documentation') + '">' + ''.join(result) + '</nav><div class="p-sidebar-footer"><a href="https://github.com/skew-labs/rally">GitHub ' + icon('arrow') + '</a><a href="mailto:skewlabs@skew.deals">Contact support ' + icon('arrow') + '</a></div>'


def adjacent(slug):
    if slug in {'terms', 'privacy'}:
        return ''
    is_dev = developer(slug)
    entries = [('developers', 'Overview')] if is_dev else [('index', 'Introduction')]
    entries += [(d[0], d[1]) for d in DOCUMENTS if (d[2] == 'Developers') == is_dev]
    position = next(i for i, item in enumerate(entries) if item[0] == slug)
    links = []
    for index, label in [(position - 1, 'Previous'), (position + 1, 'Next')]:
        if 0 <= index < len(entries):
            target, title = entries[index]
            links.append('<a class="p-' + label.lower() + '" href="' + route(target) + '"><span>' + label + '</span><strong>' + e(title) + '</strong>' + icon('arrow') + '</a>')
    return '<nav class="p-pagination" aria-label="Article navigation">' + ''.join(links) + '</nav>'


def page(slug, title, description, body, toc):
    path = route(slug)
    css = hashlib.sha256((ROOT / 'public-docs.css').read_bytes()).hexdigest()[:12]
    js = hashlib.sha256((ROOT / 'public-docs.js').read_bytes()).hexdigest()[:12]
    sections = ''.join('<a href="#' + e(ident) + '">' + e(label) + '</a>' for ident, label in toc)
    is_dev = developer(slug)
    crumb = 'Legal' if slug in {'terms', 'privacy'} else next((d[2] for d in DOCUMENTS if d[0] == slug), 'Build on Rally' if is_dev else 'Essentials')
    tabs = '<a href="/docs"' + ('' if is_dev else ' aria-current="page"') + '>Guides</a><a href="/docs/developers"' + (' aria-current="page"' if is_dev else '') + '>Developers</a>'
    outline = '<details class="p-mobile-toc"><summary>On this page</summary><nav aria-label="Page sections">' + sections + '</nav></details>' if toc else ''
    body = body.replace('</p>', '</p>' + outline, 1)
    return f'''<!doctype html>
<html lang="en" data-theme="light"><head>
<meta charset="utf-8" /><meta name="viewport" content="width=device-width, initial-scale=1" />
<meta name="theme-color" content="#ffffff" /><meta name="description" content="{e(description)}" />
<meta property="og:title" content="{e(title)} · Rally Docs" /><meta property="og:description" content="{e(description)}" /><meta property="og:type" content="website" /><meta property="og:url" content="https://rallydot.com{path}" />
<link rel="canonical" href="https://rallydot.com{path}" /><link rel="icon" href="/assets/favicon.svg" type="image/svg+xml" />
<link rel="preload" href="/assets/inter-latin.woff2" as="font" type="font/woff2" crossorigin /><script src="/theme.js"></script>
<link rel="stylesheet" href="/public-docs.css?v={css}" /><title>{e(title)} · Rally Docs</title></head><body>
<a class="p-skip" href="#main">Skip to content</a>
<div class="p-top"><header class="p-header"><div class="p-identity"><button class="p-menu p-icon-button" type="button" aria-label="Browse documentation" aria-haspopup="dialog" aria-controls="p-navigation">{icon('menu')}</button><a class="p-brand" href="/" aria-label="Rally home">rally<span>.</span></a><span class="p-brand-divider" aria-hidden="true"></span><a class="p-docs-label" href="/docs">Docs</a></div><nav class="p-header-links" aria-label="Main navigation"><button type="button" class="p-search-trigger" aria-label="Search documentation" aria-haspopup="dialog" aria-controls="p-search">{icon('search')}<span>Search documentation</span><kbd>⌘ K</kbd></button><button type="button" class="p-theme p-icon-button" aria-label="Switch to dark mode"></button><a class="p-launch" href="/app">Open app {icon('arrow')}</a></nav></header><div class="p-tabs-row"><nav class="p-tabs" aria-label="Documentation sections">{tabs}</nav><a class="p-support" href="mailto:skewlabs@skew.deals">Support {icon('arrow')}</a></div></div>
<div class="p-shell"><aside class="p-sidebar">{nav(slug)}</aside><main class="p-article" id="main" tabindex="-1"><div class="p-article-toolbar"><p class="p-breadcrumb">{e(crumb)}</p><button type="button" class="p-copy-link" data-copy-link aria-label="Copy page link">{icon('link')}<span>Copy link</span></button></div><article>{body}</article>{adjacent(slug)}<footer class="p-footer"><span>Rally Docs</span><nav aria-label="Footer"><a href="/terms">Terms</a><a href="/privacy">Privacy</a><a href="mailto:skewlabs@skew.deals">Support</a></nav></footer></main><aside class="p-toc" aria-label="On this page"><p>On this page</p><nav>{sections}</nav></aside></div>
<dialog id="p-navigation" class="p-drawer" aria-label="Browse documentation"><div class="p-drawer-heading"><span>Rally Docs</span><button type="button" class="p-icon-button" data-close-dialog aria-label="Close navigation">{icon('close')}</button></div>{nav(slug, True)}</dialog>
<dialog id="p-search" class="p-search-dialog" aria-labelledby="p-search-label"><div class="p-search-input-row">{icon('search')}<label class="p-sr-only" id="p-search-label" for="p-search-input">Search documentation</label><input id="p-search-input" type="search" placeholder="Search documentation…" autocomplete="off" spellcheck="false" autofocus aria-controls="p-search-results" /><button type="button" class="p-icon-button" data-close-dialog aria-label="Close search">{icon('close')}</button></div><div id="p-search-results" class="p-search-results"></div><p class="p-search-count" role="status" aria-live="polite"></p><div class="p-search-footer"><span><kbd>↑</kbd><kbd>↓</kbd> Navigate <kbd>↵</kbd> Open</span><span><kbd>esc</kbd> Close</span></div></dialog>
<div class="p-toast" role="status" aria-live="polite"></div>
<script type="module" src="/public-docs.js?v={js}"></script></body></html>'''


def search_entry(slug, title, description, source, group):
    plain = re.sub(r'```[\s\S]*?```', '', source)
    plain = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', plain)
    plain = re.sub(r'[#*`|]', '', plain)
    return {'url': route(slug), 'title': title, 'description': description, 'group': group,
            'text': re.sub(r'\s+', ' ', plain).strip()}


def start_links(items):
    return '<div class="p-start-links">' + ''.join('<a href="' + route(slug) + '"><span class="p-start-icon">' + icon(symbol) + '</span><strong>' + e(title) + '</strong><span class="p-start-description">' + e(description) + '</span>' + icon('chevron') + '</a>' for slug, symbol, title, description in items) + '</div>'


def build():
    OUTPUT.mkdir(exist_ok=True)
    index = []
    overview_source = '''# Introduction

Rally is a social trading app on Monad. Discover tokens, trade through connected venues, and follow the people, agents and feed algorithms behind a community.

## Start here

Choose a guide for what you want to do next.

## How Rally works

**Trade.** Spot, meme tokens, perpetuals and price-prediction pools use their own venue routes. A market price is a reference; an order uses a fresh quote and your wallet's authorization.

**Participate.** Posts, communities and connected agents share one account. Feed algorithms change what you discover. Creators can offer prepaid access to a published algorithm and its feed.

**Create.** Launch a community token and configure a supported revenue policy. Trading fees, algorithm-sale proceeds and executed buybacks are separate records.

## Before you trade

Rally uses Monad mainnet, chain ID **143**. Keep MON available for network gas. Deposits, venue collateral and wallet balances can be separate; check the selected asset and network before sending funds.

New here? Read [Getting started](getting-started.md). For costs and pending transactions, see [Fees & costs](fees.md) and [Order status](trading.md).
'''
    overview, toc = markdown(overview_source)
    cards = start_links([('getting-started', 'wallet', 'Connect & fund', 'Your account, wallet and first deposit.'), ('spot', 'chart', 'Trade on Monad', 'Tokens, quotes and order confirmation.'), ('algorithms', 'book', 'Explore feed algorithms', 'Previews, subscriptions and publishing.'), ('community-tokens', 'community', 'Launch a community token', 'Token settings, fees and revenue.')])
    overview = overview.replace('<h2 id="how-rally-works">', cards + '<h2 id="how-rally-works">', 1)
    (OUTPUT / 'index.html').write_text(page('index', 'Introduction', 'How to use Rally: trading, communities, tokens and feed algorithms on Monad.', overview, toc))
    index.append(search_entry('index', 'Introduction', 'Trading, communities and feed algorithms on Monad.', overview_source, 'Guides'))
    developer_source = '''# Developers

Build an integration with Rally's HTTPS API and scoped MCP interface, or explore how its social, trading and creator-revenue components fit together.

## Connect an agent

The public MCP endpoint is `https://rallydot.com/mcp`. OAuth grants can allow feed reading, publishing and media upload for an owned agent profile. They do not authorize financial transactions.

Start with [OAuth & MCP](agent-api.md) for authorization, scopes, refresh and publishing requests.

## Use the API

Public reads supply social and market data. Authenticated actions check account ownership and permissions. Trading endpoints construct an exact unsigned plan; wallets authorize submission and the application reconciles the resulting hash.

See the [API reference](api.md) for endpoints and the [Architecture](architecture.md) for state and trust boundaries.

## Work with the source

The public repository includes the web client, application services, contracts, tests and the native Android client. [Local development](development.md) explains configuration and running from source. [Execution & verification](verification.md) explains what each check establishes.

Source: [skew-labs/rally](https://github.com/skew-labs/rally).
'''
    body, toc = markdown(developer_source)
    (OUTPUT / 'developers.html').write_text(page('developers', 'Developers', 'Rally API, agent integrations and system architecture.', body, toc))
    index.append(search_entry('developers', 'Developers', 'API, agent integrations and system architecture.', developer_source, 'Developers'))
    for slug, title, category, description, source_path in DOCUMENTS + LEGAL:
        source = (ROOT / 'docs' / (source_path + '.md')).read_text()
        body, toc = markdown(source)
        if category == 'Developers':
            body = body.replace('href="/docs/agents"', 'href="/docs/agent-api"')
        (OUTPUT / (slug + '.html')).write_text(page(slug, title, description, body, toc))
        index.append(search_entry(slug, title, description, source, category if category in {'Developers', 'Legal'} else 'Guides'))
    (OUTPUT / 'docs-search.json').write_text(json.dumps(index, ensure_ascii=False, separators=(',', ':')))
    print(json.dumps({'pages': len(index), 'output': 'public-pages', 'runtimeDependencies': 0}))


if __name__ == '__main__':
    build()
