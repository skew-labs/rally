# Wallets, deposits and sends

Your linked wallet holds your assets. Profile shows the address used by Rally, currently priced balances and the available Send and Deposit actions.

## Which wallet is connected?

A wallet login proves ownership with an identity signature. Email or Google login uses Privy; embedded-wallet creation is an explicit choice. Your external wallet and an embedded wallet can have different addresses.

Check the linked address in Profile before funding or preparing a trade. Changing the wallet or network during a signature request can require a fresh ownership check.

## Deposit assets

1. Open **Profile → Deposit**.
2. Copy the address or scan its QR code.
3. Select **Monad mainnet** in the sending wallet or exchange.
4. Send the supported asset and wait for confirmation.

Deposit displays an address; it does not move funds. MON pays network fees. A token address on another network is not the same balance on Monad.

## Send assets

1. Open **Profile → Send**.
2. Select the asset and enter the recipient address.
3. Enter an amount or use an available balance shortcut.
4. Check the recipient and approve the exact transfer in your wallet.
5. Follow the recorded transaction until its transfer is confirmed.

Sending assets does not close a perpetual position or withdraw its collateral first. Use that venue's withdrawal action when assets are held there.

## Balance and 24-hour change

The displayed total adds the wallet assets with available prices. Unpriced assets remain unavailable rather than being assigned a value of zero. Some balances refresh progressively.

The 24-hour figure describes price changes in current holdings. It does not include a complete history of deposits, withdrawals or realized trading profit. If price-change coverage is incomplete, a complete portfolio percentage is unavailable.

## Recovery and provider access

Recovery depends on the wallet or login provider you selected. Keep independent access to your wallet. Clearing app data does not reverse transactions or necessarily revoke provider permissions.

Rally support will not ask for a seed phrase or private key. For an interrupted trade, use [Order status](trading.md) before submitting another transaction.
