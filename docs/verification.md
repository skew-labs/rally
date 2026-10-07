# Verification and limits

The repository contains executable checks for ranking limits, actor/scoped authorization, wallet call matching, payment access, receipt-derived performance, public revenue visibility, bundle integrity, artwork admission and community/revenue contracts. Automated checks use synthetic accounts, receipts and venue fixtures. Independently reconciled mainnet records are listed separately below.

## Release verification

The clean source release is built and tested in a separate environment before publication. The optional manually triggered GitHub workflow defines installation, both contract builds, main-client/auth builds, Python suites, isolated EVM contract checks and browser smoke checks for a dedicated isolated runner. Runner registration and automatic public-PR execution are not enabled by this source release. A passing fixture test is not labelled a mainnet fill.

The 2026-10-08 verification passed:

- **141 Python tests:** ranking boundaries, OAuth rotation/replay/audience and actor scopes, discovery/access/performance, public launch activity, bundle integrity, artwork and launch ingestion, exact smart-account calls and approvals, collateral/payment delivery and Privy identity verification.
- **90 isolated contract checks:** 52 custom community factory/vault checks and 38 external-token revenue-vault checks.
- **90 browser checks:** ten pages at three viewport sizes, rendering/errors/overflow.
- **14 auth dependency checks:** UUID bounds, patched wallet URI parsing through its consumers, and bounded malformed-input decoding.
- **Zero known advisories:** both complete locked npm graphs and resolved Python application requirements; no advisory suppressions.
- Solidity compilation, content-addressed application build and separately locked Privy bundle build.

Rebuilt ABI, creation bytecode and runtime bytecode matched the corresponding production artifacts for all three custom community contracts and the external-token revenue vault. This proves artifact reproducibility against that deployed application's artifacts; it does not replace fresh onchain deployment checks or an independent audit.

## Reconciled mainnet records

On 2026-10-08, a read-only recheck independently matched these existing transactions against finalized canonical receipts and the expected application calls:

| Record | Independently checked result | Transaction |
| --- | --- | --- |
| RALLY community launch | Exact 1 USDC seed, token/vault/pair identities, creator ownership, full initial token supply deposited into the pair and creator LP receipt | [MonadVision](https://monadvision.com/tx/0xa4cf72f6855c4e99debebf92b308598f27fe48649d1d75cbdb944f8084fb2766) |
| PancakeSwap V2 USDC → RALLY purchase | Exact 0.01 USDC wallet debit and RALLY delivery above the reviewed minimum; the smart-account wrapper was verified by its exact internal call | [MonadVision](https://monadvision.com/tx/0xa2ac9346c534af1e8f0b98c7b496c6576cc08e8fc02f52e321af76733aff392c) |

RALLY's exact token address is `0x6a834ff24ed4a59c17960a4fbccd46cfd558833a`. These records establish issuance and this purchase. The recheck itself submitted no transactions and requested no wallet signatures. Automated contract checks cover subscription allocation, reserve protection and buyback behavior using explicit mock venues.

The public market screenshot was captured from the deployed app in an anonymous browser with no write requests. Source publication excludes private state and the owner-specific funding-test interface; no production wallet session or provider credential was used for these tests.

The browser suite covers ten representative pages at 390, 768 and 1,440 pixels. It checks rendering, runtime errors and page overflow, with all providers disabled and network writes forbidden. This checks layout and application integration, not live price completeness, every modal gesture or authenticated wallet behavior.

## Measured loading improvements

Recent production loading work coalesced startup fetches, removed unnecessary market inventory from the initial Discover/Memes bootstrap, bundled the main module graph, rendered meme rows progressively and introduced small background-generated public artwork.

The controlled measurements used a 390-pixel viewport, 120 ms network latency, 200,000 bytes/second bandwidth, four-times CPU throttling and three cold-cache samples:

| Page | Previous median | Updated median | Warm-cache sample |
| --- | ---: | ---: | ---: |
| Discover | 2.60 s | 1.63 s | 0.45 s |
| Meme market | 3.51 s | 1.73 s | 0.58 s |

The metric is first rendered content in the test harness, not a global real-user percentile or a claim of instant provider responses. Warm figures are separate individual samples. The production UI pass for that change covered 230 checks and made no wallet requests or financial transactions.

The source retains timestamped prices and full fetched catalogs; unavailable logos have a fallback. Thumbnail generation does not change token identity, price or executable transaction logic.

## Evidence levels

| Check | Can establish | Cannot establish |
| --- | --- | --- |
| Static build | Source/ABI/bundle generation and import consistency | Security audit or deployed state |
| Synthetic tests | Expected state transitions, rejection paths and fixture arithmetic | Real holdings, liquidity or income |
| Live read-only observation | At-time deployment/interface/reference or quote availability | A signed order or delivered funds |
| Submitted hash | A transaction was requested or broadcast | Canonical finality or intended business outcome |
| Finalized reconciled result | Exact onchain transfer, launch, position or payout for that record | Future returns or universal venue coverage |

Execution requires the venue's applicable oracle, keeper, access and market conditions. Payment and buyback accounting uses finalized delivery evidence. See [Trading](trading.md) and [Community tokens](community-tokens.md).
