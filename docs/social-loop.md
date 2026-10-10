# Social trading loop

The loop runs alongside existing market collection and financial reconciliation. None of its workers owns a signing key, constructs delegated trade authority or submits financial transactions.

| Module | Responsibility |
| --- | --- |
| `social_loop.py` | Server-observed immutable signal terms, sampled price history, finalized-fill sharing and watched-market notices |
| `token_benefits.py` | Creator-owned tiers, finalized ERC20 holdings proofs, feed access, invoice discounts and opt-in badges |
| `algorithm_league.py` | Forward-only weekly enrollment, common candidate snapshots, bounded scoring and later price marks |
| `push_delivery.py` | Per-device registration, preferences, outbox deduplication, delivery leases, cancellation and bounded retry |
| `social-loop.js` / `SocialLoop.kt` | Existing feed, post, creator, profile and leaderboard surfaces |
| `rally-offline.js` / `PushNotifications.kt` | Notification display and exact app navigation; no financial request queue |

## Storage and authority

Signal terms are committed atomically with a post and checked on idempotent retries. A mutable caption does not change the entry price or target. Terminal state is based on a fresh observed reference at or before expiration. Original observations and closed-call counts survive post deletion.

A fill share references an already-owned application order. It requires finalized state, transaction/receipt identity, successful status and delivered token balance a nad.fun reconciled `swap_delivered` result, or a Perpl reconciled filled quantity and price. Quoted amounts and keeper-pending requests are ineligible. Creation and withdrawal are human-account actions; existing agent grants can publish signals through their existing publishing scopes.

Holder proofs bind creator, token, viewer and the viewer's currently connected wallet. Reads use one finalized block. Proofs expire after 120 seconds; feed checks never perform provider reads. Paid entitlements take precedence over holding-based access. Checkout and displayed subscription prices use the same integer discount calculation. A stale unsigned discounted invoice is replaced on a new checkout; preparation rechecks the current price before constructing payment calldata.

League enrollment freezes a published version for one UTC week. Each round persists one candidate/feature/reference snapshot and its SHA256 digest before scoring. Formula execution uses the existing isolated CPU/memory-limited worker. Missed scoring deadlines and missing 24-hour price references are recorded explicitly. Post-to-pick delay uses the frozen selected post timestamps. Reader and receipt metrics use the same week window and remain distinct from reference-price changes.

## Push delivery

Web Push uses a P-256 VAPID private PEM under the private state directory, mode 0600. Only its public key is returned by `/api/push/config`. HTTPS subscription endpoints are restricted to supported browser push services; redirects are disabled. Device payloads never appear in account exports or public APIs. Delivery checks current preference, post visibility, feed entitlement and watch status again immediately before sending.

The outbox accepts each notification/device pair once, leases work, retries transient failures and retires expired subscriptions. `accepted` means the provider accepted a request; it does not prove display or device receipt. Lock-screen text is generic. An app deep link cannot trigger a wallet request or fill.

For Android, configure a Firebase project with Cloud Messaging enabled. Store its service-account JSON as `private/firebase-service-account.json`, mode 0600, and public client configuration as `private/firebase-android.json`:

```json
{
  "projectId": "your-firebase-project",
  "applicationId": "1:123456789:android:0123456789abcdef",
  "apiKey": "your-public-android-firebase-api-key",
  "senderId": "123456789"
}
```

Use a service account restricted to sending messages for that Firebase project. Do not commit service-account material. Android initializes Firebase from the public configuration only after notification opt-in. Without valid configuration, the API reports `android: false`; login, trading and in-app notifications remain available.

`RALLY_PUSH_DISABLED=1` disables provider delivery in test environments. Fixture tests exercise records, cancellation and provider response handling without wallet signatures, funds or external sends.
