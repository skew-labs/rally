# Community tokens

Pair a community and creator identity with a token. Rally's launch flow connects token settings, a supported liquidity path and the revenue policy you choose.

## Choose a launch path

| Path | How it launches | Revenue connection |
| --- | --- | --- |
| Custom community token | Rally factory and a token/USDC liquidity pool | Compatible community vault for algorithm-sale revenue |
| nad.fun token | Supported launch engine, bonding curve and migrated route | Supported venue fee vaults and optional Rally algorithm-revenue vault |

Creating an account or filling in token settings does not mint a token. A launch is activated only after its matching onchain result is confirmed.

## Prepare the launch

1. Open **Home → Launch**.
2. Choose the supported launch path and publishing identity you control.
3. Add the token image, name and symbol.
4. Configure the offered revenue allocation and initial funding.
5. Approve the exact launch request and any necessary allowance.
6. Check the confirmed token, community and activity links.

The custom factory currently creates a fixed billion-token supply and seeds it into the requested pool. The creator receives its liquidity position; that position is not automatically locked.

## X and GitHub beneficiaries

Supported nad.fun fee allocations can point to an X or GitHub handle. The venue's identity and claim requirements still apply. Typing a handle does not prove that you control the account or make its fees immediately claimable.

Use the applicable launch income or claim screen to prepare a claim. A pending request becomes received income only after delivery is confirmed.

## Algorithm-sale buybacks

A compatible revenue vault can allocate a chosen part of received algorithm payments to a buyback reserve. The remainder goes to the creator under that policy.

For example, an 80% buyback policy applied to a 10 USDC algorithm payment reserves 8 USDC for eligible token purchases and allocates 2 USDC to the creator. This illustrates allocation only; it is not a statement that a buyback has executed or a creator has earned that amount.

Price protection, liquidity and configured limits determine whether a purchase executes immediately or remains pending. Reserved USDC, purchased tokens and a burn are different activity states.

## Burn and token rights

Custom community tokens support a burn that reduces supply. The external-token revenue route sends its configured burn allocation to a dead address, which does not itself reduce total token supply.

Token ownership does not automatically provide equity, dividends, governance rights or guaranteed appreciation. Venue trading fees and algorithm-sale proceeds are different revenue sources. Check the exact token, pool and policy rather than relying on its community name.
