# Perpetuals

Open long or short exposure through supported perpetual venues on Monad. Collateral, leverage, funding and settlement follow the selected venue's rules.

## Choose a market

Open **Home → Markets → Perps** and select a market. Check its venue as well as the asset name. Two venues offering the same underlying asset can have different prices, collateral and position rules.

Rally connects venue-specific routes, including Perpl and supported LeverUp markets. Availability depends on current market, oracle and keeper conditions; not every catalog entry is an executable order.

## Fund the venue account

Perpl uses **AUSD** collateral. Use its deposit action when the venue requires collateral inside its exchange account. Wallet assets and venue collateral are different balances.

Other venues can use different collateral assets and deposit rules. The selected order panel shows the applicable action.

## Open and close a position

1. Select **Long** or **Short** and enter the order size.
2. Set the protections offered by the venue's order panel.
3. Check collateral, quote and estimated costs.
4. Approve the exact request in your wallet.
5. Follow the resulting order or position status.

A submitted transaction may create a pending order rather than an immediately filled position. Closing and collateral withdrawal are separate venue actions where required.

## Leverage, funding and liquidation

Leverage increases both exposure and the effect of price changes on collateral. Funding and liquidation are calculated by the venue, not by a social-feed algorithm.

Check the venue's position information and liquidation conditions. A chart reference from another source may not be the venue's settlement or liquidation price.

## Venue rules

For Perpl's contract and market rules, use its [official documentation](https://docs.perpl.xyz/). Rally's confirmation flow is described in [Order status](trading.md).
