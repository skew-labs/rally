# Security

This repository is an application source release, not an independent audit. Solidity fixture tests, unsigned transaction simulations and provider observations have different scopes from an audited protocol or funded mainnet acceptance.

## Responsibility boundaries

The browser wallet controls final financial signatures. The application builds and validates exact transactions and reconciles the resulting chain state; it does not hold a general-purpose user spending key. The optional MetaMask bridge signs only a predefined account-identity message within its existing pairing.

Social content, access entitlements and moderation are application-managed. External venues, authentication providers, RPC operators, the host OS and the creator's permitted vault policy are separate dependencies. RPC traces can be required for smart-account verification; unavailable verification must leave the result unresolved.

Custom token-launch LP positions belong to the creator and are not automatically locked. Buyback policies do not guarantee price support or profit. The external-token vault's dead-address transfer does not reduce token total supply.

## Deployment handling

- Keep authenticated RPC URLs, sessions, OAuth codes/tokens, provider credentials and CLI login state out of source, public responses and logs.
- Keep runtime databases, uploaded media, pairing records and state volumes private.
- Preserve exact origin/audience validation, owned-actor scopes, entitlement gates and contract pins.
- Never reinterpret an approval, pending hash or receipt status alone as a delivered trade or paid entitlement.
- Reconcile an ambiguous submission before requesting another financial transaction.

## Dependency status

The 2026-10-08 dependency verification reports **zero known advisories** in both locked npm graphs and the resolved Python application requirements. The checks include development dependencies; advisory suppressions are not used.

The wallet bridge uses patched UUID, URI-parser and WebSocket dependencies. Compatibility checks exercise UUID bounds, wallet connection URI parsing and bounded malformed-input decoding. Versioned bridge bundles prevent an updated deployment from reusing the previous entry module. Contract tests run on a disposable loopback Anvil instance instead of the retired Ganache dependency graph. Solidity remains pinned to 0.8.28, with its temporary-file dependency patched; the resulting contract artifacts are unchanged.

Run `npm run audit`, `npm run test:auth-dependencies` and `pip-audit -r requirements.txt` in the isolated verification environment. These are dependency advisory checks, not an independent protocol audit.

## Reporting

For sensitive issues, use the repository's private vulnerability reporting when available. Do not disclose credentials, exploitable details or private account records in a public issue. Ordinary reproducible bugs can be filed with synthetic inputs and redacted diagnostics.
