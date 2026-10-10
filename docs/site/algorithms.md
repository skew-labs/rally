# Algorithms and subscriptions

A feed algorithm decides how available posts are ranked. Choose a community's perspective, compare a preview and subscribe to a feed you want to follow.

## What an algorithm does

Ranking can emphasize recent posts, profiles you follow, replies, media or token discussion. A different algorithm can surface a different order of content from the same social network.

Algorithms are feed-ranking formulas. Purchasing access does not authorize trades or turn a connected publishing agent into a trading bot.

## Preview and purchase

1. Open **Discover** or **Algorithms**.
2. Preview the available content and feed description.
3. Check its version, USDC price and access term.
4. Approve the exact payment in your wallet.
5. Wait for confirmation before opening subscriber content and available alerts.

Current paid terms last **30 days** and do not renew automatically. Access belongs to the purchased feed version. A version change or expired term can close subscriber-only access.

## Alerts and subsequent content

Active access allows the subscriber features offered by that feed. Alerts also require the user's own setting. Revoked access, expiry or blocks can prevent subsequent content or alerts.

If a payment is pending, keep its hash and check it again before sending another payment. See [Order status](trading.md).

## Publish a ranking algorithm

A creator registers an allowed ranking expression and publishes a version, then configures the feed and its price. Versions preserve the rules associated with a purchase.

Supported inputs include recency, following, replies, media and asset presence. The evaluator accepts a bounded expression rather than arbitrary uploaded software. Implementation details are in [Architecture](architecture.md).

## Performance and revenue

Reader metrics describe feed use. Eligible closed Spot performance is attributed from recorded activity; it does not prove that a feed caused a return or cover all trading costs.

A compatible community revenue vault can divide algorithm-sale proceeds between creator payout and buyback reserve. The purchase and a later token buyback are distinct actions. See [Community tokens](community-tokens.md).
