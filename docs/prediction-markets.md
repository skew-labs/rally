# Monad price predictions

Rally routes price predictions to Castora on Monad, chain 143. A pool defines the asset reference, fixed entry stake, closing time, price snapshot time and fee. Users submit a USD price prediction before the pool closes. Winners claim through the existing wallet-controlled execution flow after the venue settles the pool.

These are fixed-stake price predictions. They do not have tradable Yes/No outcome tokens or a secondary order book. Pool creation in Castora's published contract requires its admin role. The application exposes the state actually returned by the contract.

## Public data flow

`venues.predictions()` checks the official getter's target, reads the pool count, and loads records in batches of at most 50 pool IDs. Record counts and identity order must match the request. Concurrent readers share a 30-second catalog cache. A pool's closing time is checked again on every returned view; cached records never keep a pool open past its deadline. Expired provider reads return an error rather than labeling old data as fresh.

`prediction-ui.js` separates public discovery from execution. The visible market view checks for updates every 15 seconds through the shared market polling loop. Keyed cards preserve DOM identity, focus and scroll position when records are unchanged. A lightweight clock updates closing times and removes expired entry actions without waiting for another network response. Hidden views suspend polling.

The price strip uses exact Perpl market IDs for MON, BTC, ETH and SOL. These prices are identified as references, not Castora settlement prices or execution quotes. Missing or stale prices are shown as unavailable. Price reference identifiers stay separate from spendable token addresses.

## Execution boundary

`finance.js` owns the prediction form, wallet handoff and submitted-transaction recovery. `venues.plan()` rechecks the pool directly, validates the stake token and price precision, pins the venue contract and prepares exact calldata. The existing transaction preflight and receipt reconciliation verify the wallet, destination, calldata and chain. Public polling cannot sign or submit a transaction.

Unknown assets cannot acquire a borrowed token identity or enable a prediction action. A closing deadline disables an already open form. Settlement and claimable winnings remain venue-derived states.

Primary implementation references: [Castora contract](https://github.com/castora-xyz/castora/blob/main/contract/src/Castora.sol), [asset reference schema](https://github.com/castora-xyz/castora/blob/main/frontend/src/schemas/tokens.ts), and [official deployment constants](https://github.com/castora-xyz/castora/blob/main/server/shared/src/utils/contract.ts).
