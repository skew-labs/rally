# Price predictions

Rally connects to Castora's fixed-stake price-prediction pools on Monad. Choose a pool and submit a future USD price before entries close.

## Read a pool

Each pool specifies an asset, entry stake, entry deadline, price snapshot time and pool fee. The market view separates open, historical and resolved pools.

These pools are not tradable Yes/No outcome tokens. You submit a numerical price prediction and participate under the pool's settlement rules.

## Enter an open pool

1. Open **Home → Markets → Prediction**.
2. Select a pool that is still open.
3. Enter the USD price you predict for its snapshot time.
4. Check the fixed stake and fee, then approve the wallet request.
5. Follow the entry's transaction status.

The pool deadline is checked again when the entry is prepared. A pool can close while you are reading its card; a cached card cannot extend its entry period.

## Settlement and claims

Settlement comes from the venue. After a pool is resolved, eligible users can prepare a claim through the connected wallet. Submitted claims become received winnings only after delivery is confirmed.

The price references shown alongside pools provide context. They are not a replacement for Castora's settlement source.

## When there are no open pools

You can browse history and resolved pools, but cannot enter a closed pool. Pool creation requires the role specified by Castora's contract. Rally does not create fictitious open markets when the venue has none.
