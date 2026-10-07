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

At the 2026-10-08 publication check, the optional Privy client dependency graph reported 23 moderate npm advisories, with no high or critical advisory after a compatible `ws` patch override for viem dependencies. These remaining upstream advisories are not resolved by the application tests. This scoped check is not a complete dependency/security audit of the repository or a claim that every reported package is exercised in the browser bundle. Development-only EVM tooling has a separate dependency graph.

## Reporting

For sensitive issues, use the repository's private vulnerability reporting when available. Do not disclose credentials, exploitable details or private account records in a public issue. Ordinary reproducible bugs can be filed with synthetic inputs and redacted diagnostics.
