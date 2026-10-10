# Spot trading

Buy or sell a token through the available Monad routes without leaving its market panel.

## Open a token

Go to **Home → Markets → Spot**, or open a token attached to a post. The detail panel shows its chart, market information and, where an index is available, holders.

Token identity is the network and contract address. Names and tickers can be shared by different tokens. Check the address when selecting an unfamiliar asset.

## Buy or sell

1. Choose **Buy** or **Sell**.
2. Select the payment asset and enter the amount.
3. Wait for the amount-specific route and expected output.
4. Approve the wallet request.
5. Follow the order status until the transfer is confirmed.

Rally compares supported routes, including Kuru and supported DEX paths. The available route depends on the token, amount, liquidity and current venue conditions. A listed token is not a promise of liquidity at every size.

## Price and slippage

A chart is a price reference, not an executable order. The quote reflects your selected amount. Slippage protection sets the minimum acceptable output for the prepared trade.

If you change the amount, wallet or route, use the refreshed quote. Expired quotes must be prepared again before signing. See [Fees and execution costs](fees.md).

## Token approvals

An ERC-20 payment asset can require a separate allowance to its route contract. Approving an allowance does not itself buy the token. MON transactions use a native value instead of an ERC-20 approval.

## After submission

Rally records the transaction hash and checks the actual asset delivery. If the result remains pending or unknown, reconcile that same hash before trying again. See [Order status](trading.md).
