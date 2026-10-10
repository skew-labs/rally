# Order status

The order panel follows your request from a quote to the intended onchain result. A transaction hash and a completed trade are different stages.

## From quote to confirmation

| Stage | What it means | What to do |
| --- | --- | --- |
| Quote | A route has returned amounts for the selected order | Check the asset, amount and route |
| Wallet approval | The exact allowance or transaction is ready for your wallet | Approve it if the details match |
| Submitted | A transaction hash has been recorded | Follow that hash; do not duplicate it |
| Confirming | The app is checking the receipt and result | Keep checking the same order |
| Confirmed result | The expected transfer, entry, launch or position change is verified | Review the resulting balance or activity |

The text shown can vary by venue. A venue that uses delayed execution can accept an order before its final position is available.

## Pending or unknown result

Keep the transaction hash. Check the recorded order and its public explorer link. An interrupted app session can recover the saved pending request.

Do not submit a replacement just because the panel has not confirmed the first result. A provider timeout can leave the outcome unknown even when a transaction was broadcast.

## Failed transaction

If the chain confirms a revert, the requested action did not complete. A failed transaction can still consume network fees. Refresh the quote and address the reported balance, deadline or route issue before another attempt.

## Why is another approval needed?

Some ERC-20 actions require an allowance before the trade or payment. That is a separate token-contract permission. An unrelated approval cannot activate your purchase or launch.

Rally removes extra application review screens, but the wallet or venue may still require its own signature or security approval.

## Incorrect balance or access

Wait for reconciliation of the existing hash. Paid-feed access is tied to its exact payment, and creator claims are tied to their actual delivery.

For support, share the public transaction hash and order or feed identity. Never share a private key, seed phrase, login token or provider secret.
