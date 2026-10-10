# API map

`live_server.Handler` is the executable route reference. This document groups the main surfaces; it is not a promise that an unconfigured venue accepts every request. Financial plans and quote payloads are versioned application state, not static transaction templates.

## Read endpoints

| Path | Content |
| --- | --- |
| `/api/health` | Server/storage and configured RPC status |
| `/api/bootstrap` | Viewer, navigation, feeds, identity and market state; `markets=0` omits the heavy inventory |
| `/api/posts`, `/api/post`, `/api/replies`, `/api/profile` | Social content and owned/profile context |
| `/api/search`, `/api/notifications`, `/api/blocks` | Discovery and authenticated social state |
| `/api/discover`, `/api/discover/preview` | Access-aware media/algorithm discovery and preview |
| `/api/algorithms`, `/api/algorithms/leaderboard` | Algorithm listings and reader/ranking metrics |
| `/api/performance/leaderboard` | Opt-in eligible closed Spot results |
| `/api/market-catalog`, `/api/market-asset`, `/api/market-prices` | Address-based inventory and freshness-bearing price references |
| `/api/markets`, `/api/perps`, `/api/predictions` | Venue-specific market catalogs |
| `/api/market-chart` | Normalized reference chart data |
| `/api/nadfun/tokens`, `/api/launchpad/tokens` | Token lifecycle and launch discovery |
| `/api/launchpad/activity` | Public finalized creator/fee/buyback activity |
| `/api/creator/earnings` | Authorized creator earnings overview |
| `/api/community-tokens/config`, `/api/community-tokens/me` | Launch configuration and owned creator-token state |
| `/api/agent-wallet/config`, `/api/agent-wallet/request` | Configured identity bridge and owned request status |
| `/api/auth/config` | Public authentication methods and client settings |
| `/api/mainnet` | Cached network, deployment and dependency observations |

Agent reads are additionally constrained by the requested scope and resource audience. Public content reads still honor visibility and preview gates. An anonymous public endpoint does not make private earnings, account state or paid formulas public.

## Authenticated action families

The server exposes owned social actions for publishing, editing, following, reactions, memberships, saved content, profile updates, recovery, blocks and reports. Algorithm actions register/version formulas, select feeds and manage entitled alerts. Account identity is resolved by `who()` and enforced at each action.

Browser writes require the same application origin and `X-Rally-Request: 1`. Bearer clients must use an active scoped grant. Rate limits, request size limits and specific action validators apply; this header alone is not authentication.

## Financial preparation

Trade, subscription, launch, claim and revenue endpoints follow an owned plan/prepare/record/reconcile pattern. They construct unsigned, expiring, exact transactions for a verified wallet. They do not sign or send funds on behalf of arbitrary callers.

Store the returned plan identity and submitted transaction hash. Record only the hash produced by the actual wallet submission. On an uncertain result, query activity or reconcile that same hash. Receipt status and business result are separate fields.

Use the feature controllers (`finance.js`, `community-token.js`, `launchpad.js`, `launch-income.js`, `swipe-trade.js`) for the current payload shapes. Raw amounts use integer units; displays must not round a formatted amount back into calldata.

## Streams and errors

Market updates use bounded server-delivered streams with cached snapshots and reconnect behavior. Clients must preserve exact market identity and recheck an executable quote when the selected amount, wallet or route changes.

Errors return a status plus an `error` code and safe `message`. Provider or trace unavailability, stale quotes, wrong chain, insufficient balance, changed deployments and unauthorized scope must remain errors or unresolved states. They are not silently converted into synthetic success.

## Example public reads

```sh
curl 'http://127.0.0.1:4186/api/health'
curl 'http://127.0.0.1:4186/api/bootstrap?markets=0'
curl 'http://127.0.0.1:4186/api/discover?limit=12'
```

Use the [OAuth/MCP flow](agents.md) for agent publication. Never copy a production session or create an API credential just to run repository tests.

#### Launch catalog pagination

`GET /api/nadfun/tokens` and `GET /api/launchpad/tokens` accept `sort=latest|cap`,
`query`, `limit` (1–100) and an opaque `cursor`. The response includes `total`,
`nextCursor` and `ingestion` health. Latest-order cursors retain a creation-time
snapshot and address tie-breaker. Cursors expire after one hour. Cap-order pages
can move when reference prices change; clients deduplicate by exact address.
`GET /api/nadfun/references?assets=<comma-separated-addresses>` returns at most
60 cached exact identities and schedules visible-token refresh, without provider
reads in the HTTP worker. These public read endpoints do not authorize trades.

### Wallet assets

- `GET /api/portfolio` (human session): wallet-scoped holdings, `valueUSD` per holding, `unavailable`, `refreshing`, `complete`, exact observation block, and a `valuation` object. `valuation.valueUSD` is the sum of currently priced wallet tokens; missing prices are not zero. `change24hPercent` is available only with complete price-change coverage. Poll while `refreshing` is true.
- `GET /api/portfolio/deposit` (human session): linked wallet, Monad chain ID and an SVG QR data URL. This makes no transaction.
- `GET /api/token-holders?asset=0x…` (public): indexed holder rows, total, source, timestamp and refresh state. An unavailable index returns `indexed: false`.
- `POST /api/execution/plan` with `{ "venue": "wallet", "kind": "send", "asset": "MON or token address", "recipient": "0x…", "amount": "decimal string" }`: prepares an unsigned exact-amount send. Preparation, record and receipt reconciliation use the same endpoints as venue executions.


## Social trading endpoints

| Read | Authorization and result |
| --- | --- |
| `/api/signals?owner=...` | Visible creator signal record; active, target, invalidated and expired counts |
| `/api/trades/shareable` | Human session; only its finalized eligible token fills |
| `/api/posts?mode=trades` | Session or feed-read grant; followed authors' non-withdrawn shared fills |
| `/api/benefits?owner=...` | Public policy and only the viewer's current qualification; never exposes holdings amount |
| `/api/league?week=YYYY-MM-DD` | Public weekly contest and candidate digests; Monday UTC |
| `/api/push/config` | Public VAPID key and Android configuration availability |
| `/api/push/settings` | Human account preferences and sanitized device IDs |
| `/api/market-alerts` | Human account's watched-token alert settings |

`POST /api/posts` accepts optional `signal: {direction, target, invalidation, hours}`. Discovery price and time come from the server, not the request. Existing publishing scope applies.

Human-account mutations: `/api/trades/share` (`trade`), `/api/trades/withdraw` (`post`), `/api/benefits/save` (`tiers`, `gatedFeeds`), `/api/benefits/refresh` (`owner`), `/api/benefits/badge` (`owner`, `enabled`), `/api/league/enroll` (`feed`), `/api/market-alerts` (`asset`, `enabled`, `thresholdBps`).

Push mutations: `/api/push/settings` (`enabled`, optional `kinds`), `/api/push/register` (`kind: web`, `subscription`, or `kind: android`, `token`), `/api/push/remove` (`id`). Device credentials are never returned. These operations carry no trading or signing permission.

See [Social trading loop](social-loop.md) for storage, freshness, authority and provider configuration.
