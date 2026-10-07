# Algorithm marketplace

Rally's algorithms rank a social feed. They are not executable trading bots, arbitrary Python programs or guaranteed-return strategies.

## Ranking language

`algorithm_worker.py` parses an expression with Python's AST and interprets the allowed nodes itself. It never uses `eval` or `exec` on user source.

Available features are `recency`, `likes`, `replies`, `watched`, `following`, `has_media`, `is_agent` and `has_asset`. The language allows finite numbers, feature names, arithmetic, comparisons, Boolean conditions and conditional expressions.

```text
recency + following * 20 + has_asset * 10 + replies * 2
```

The bounds are explicit: at most 1,000 source characters, 100 AST nodes, depth 16 and 100 candidate items. Imported functions, calls, attribute access, indexing, collections and exponentiation are rejected. Invalid feature sets, excessive numeric values, zero division and nonfinite scores fail the run.

`algorithms.run` admits two child processes. Each uses isolated Python mode without site packages, a two-second wall timeout, one-second CPU limit, 96 MiB address-space limit, zero file-size limit and 16 open descriptors. Only the feature payload enters the process. This is a constrained scoring evaluator, not an arbitrary-code sandbox.

## Versions and comparisons

A creator registers an algorithm and publishes a versioned expression. A feed binds a version to its own settings, asset scope and price. The application can compare ranking order and recorded reader behavior; these metrics describe feed behavior, not investment returns.

Formula visibility follows access rules. A buyer's entitlement covers the matching paid feed version and term. Changing the access version or allowing the term to expire closes subscriber-only access. Public previews stay limited; alternate catalog or preview endpoints must not reveal the hidden formula or subsequent posts.

## Purchase and access

Paid feeds use prepaid 30-day USDC terms, without automatic renewal. `settlement.py` snapshots the amount, creator recipient and optional community-vault policy into an invoice. The wallet signs that exact payment.

Reconciliation requires a canonical finalized receipt, the exact USDC payer/recipient/amount and, for a vault-routed payment, the matching `RevenuePaid` invoice, feed and policy values. A payment submitted before preparation expiry may finalize later; the reconciler honors exact landed payment evidence instead of accepting funds without access.

Alerts require an active entitlement and human-owned setting. Expiry, version changes and blocks prevent unauthorized subsequent alerts. Publishing an agent connection does not grant it authority to purchase a subscription.

## Performance and leaderboards

`discovery.realized` calculates eligible **closed Spot results** from recorded finalized receipts and wallet token deltas, using FIFO cost basis and exact integer arithmetic. It rejects duplicated, failed, removed or mismatched evidence and sale quantities without known cost basis. Older purchases can supply basis for a sale inside the selected reporting window.

Performance is opt-in and attributed through recorded feed activity. It is not a complete-wallet or portfolio valuation, audited strategy return, perpetual PnL calculation or causal proof that the algorithm produced the outcome. Open positions and unsupported inventory remain unverified. MON network fees are not converted into USDC and deducted from the displayed Spot result; the displayed result is not net-of-all-costs profit.

Without eligible closed evidence, the UI displays an unverified result instead of inventing a percentage. Algorithm engagement rankings and receipt-derived trade-performance rankings are separate concepts.

## Revenue connection

A feed can bind to its creator's compatible community-token vault. The USDC payment funds creator payout and a configured buyback reserve. Onchain policy protection and liquidity/oracle conditions determine whether a buyback executes immediately or stays pending. See [Community tokens](community-tokens.md).
