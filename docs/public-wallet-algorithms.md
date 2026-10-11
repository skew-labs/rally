# Public wallet discovery

Rally offers three free, first-party feed algorithms: **Wallet Re-entry**, **Wallet Confluence** and **Wallet Exit Watch**. They prioritize social posts about exact Monad token addresses associated with researched public wallets. They do not place trades or claim that following a wallet reproduces its return.

The marketplace also provides **individual public-wallet feeds**. Each profit card opens a trader-results sheet with sampled realized MON PnL, closed-trade ROI and transaction evidence, followed by the free feed action. Top PnL and Top ROI sort the displayed cohort. Paid creator feeds retain their own subscription prices and entitlement checks.

An individual wallet feed ranks token posts using only that address's observed buys and sells. It is published by Rally, not sold or endorsed by the wallet owner. Its displayed ROI is total matched round-trip MON profit divided by total matched buy cost, including matched swap gas. Multiple trade returns are weighted by their cost, not averaged or added. Results belong to the sampled wallet trades, not the feed algorithm or its subscribers.

Published wallet evidence retains its original observation time when a later collector selects different wallets. Missing or stale activity contributes zero to ranking. The registry is bounded to 100 wallet feeds; saved formulas and feed identities remain immutable.

## Research and attribution

The public research endpoint is [`/api/wallet-research`](https://rallydot.com/api/wallet-research). Feed previews provide a wallet research panel with public address links, observation times and transaction proofs. The author is Rally's service account. Wallet owners have not endorsed these feeds or published their private strategies through Rally.

The collector samples six recent nad.fun markets by holder count and six leading markets by reference market capitalization. Each market supplies up to 400 public swaps, with smaller complete histories marked separately. This is a sampled cohort, not a global Monad profitability leaderboard. API points, token market capitalization and unrealized holdings do not establish trading profit.

## Closed round-trip calculation

Provider swap data selects candidate round trips. It does not establish their realized return. The reconciler checks Monad chain 143, successful finalized canonical receipts, wallet identity and exact landed token quantities. A native call trace determines the wallet's actual MON debit and credit; failed calls and inherited `DELEGATECALL` value are excluded. Matched swap gas is deducted.

Token inventory must be zero immediately before the first trade's block and after the final trade's block. Token transfer logs inside that interval must belong to the matched transactions. Unknown transfers, partial open positions, unavailable historical state, failed or noncanonical receipts and unsupported quote assets are excluded. Verification is bounded to twelve swaps and 50,000 blocks per round trip, using log batches of at most 1,000 blocks.

The displayed MON result covers the verified round trips only. Separate approvals, failed transactions and costs outside those matched swaps are excluded. It is not audited whole-wallet profit, a USD return or an algorithm backtest. The candidate cap also means the report is not an exhaustive ranking even within its sampled markets.

## Ranking and freshness

- `wallet_reentry`: researched wallets observed buying after their latest verified profitable close.
- `wallet_buyers`: distinct researched wallets observed buying the asset within the collected 24-hour window, normalized to at most one.
- `wallet_exits`: distinct researched wallets observed selling within the same window, normalized to at most one.

Recent activity remains a **provider observation** until individually reconciled. It is separate from the finalized round trips used to select the researched wallets. These features indicate discovery context, not a buy recommendation, conviction score or proof of current holdings.

Distinct addresses do not prove independent traders. The first cohort's largest verified round trips were concentrated in one token and short holding intervals. That concentration is disclosed in the research report; it does not establish repeatable skill or coordination. A feed with no matching 24-hour wallet activity displays that state and falls back to its ordinary recency/personalization terms.

Collection runs outside request handlers. Feed ranking reads the stored snapshot; it never makes a provider call. A snapshot older than two hours contributes zero wallet features. An unsuccessful collection preserves the previous evidence and its original timestamp. Hourly collection obeys nad.fun's existing rate limiter and the shared RPC budget.

The scoring language retains its process and AST limits. Old frozen league snapshots receive zero for the new wallet fields rather than gaining information collected after their capture. Custom paid formulas and account authorization remain subject to existing access checks.

Sources: [nad.fun official API integration](https://github.com/Naddotfun/api-intergration), [QuickNode Monad transaction tracing](https://www.quicknode.com/docs/monad/debug_traceTransaction).
