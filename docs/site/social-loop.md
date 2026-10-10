# Signals, shared trades and community benefits

Rally connects discovery, a creator's community and your own trade. These features use the same account in the web app and Android.

## Notifications

Open **Profile → Notifications** in Android, or **Profile → Push settings** on the web. Enable notifications explicitly on each device. Browser or Android notification permission is also required.

Turn on an algorithm's alert in its preview after subscribing or obtaining token-based access. In **Manage price alerts**, enable a watched token to receive a notice after a 5% price change, at most once every five minutes. A new nad.fun DEX migration alert requires a change from an observed curve state to a DEX state verified at a finalized Monad block. Existing graduated tokens do not generate a new-migration notice.

Tapping a notification opens its post or token in Rally. Lock screens display generic activity text. Turning off alerts, removing a watched token, blocking an author or losing feed access cancels queued notices. Delivery depends on the browser, device permission, network and push provider.

Android push requires the deployment's Firebase configuration. The Android app displays its availability; in-app notifications continue to work while Firebase is not configured.

## Publish a signal

In **Create post**, choose a token and enable **Add a signal**. Set direction, target and invalidation in USD. The web supports durations from one day to thirty days; Android starts with a 24-hour signal.

Rally records the current server-observed price, source and observation time. Publishing requires a reference no more than three minutes old. Upside targets must sit above entry and invalidation below it; downside reverses these relationships.

The card records subsequent observed prices and becomes **Target reached**, **Invalidated** or **Expired**. These are observations, not orders or realized investment returns. A move between observations may not be captured. Editing post text cannot edit signal terms. Deleted calls remain in the creator's track-record counts.

## Following Trades

Open **Profile → Share a trade** on the web or **Share trades** in Android. Choose a finalized eligible Spot, nad.fun or Perpl fill from your own activity. Only the selected fill is published; Rally does not publish your entire wallet history.

The card uses verified token delivery and a finalized receipt, rather than quoted output. The **Trades** feed shows fills shared by people you follow. **Buy** opens the token's existing trade sheet; **Trade** opens the original Perpl market: choose your amount and approve through your wallet. No trades are copied automatically. You can stop sharing a fill.

## Token benefits

A creator with a launched Rally community token can set up to five increasing holding tiers. A tier may include owned algorithms, a subscription discount up to 90% and an optional public member badge. Select feeds that should require holdings or an existing subscription.

Open **Token benefits → Check my holdings** to verify your connected wallet at a finalized Monad block. Proofs expire after two minutes and refresh while recently active. A wallet change, expired proof or insufficient holdings removes holding-based access and discounts. An already-paid subscription remains valid until its recorded expiration.

## Weekly league

Open **Leaderboard → Weekly league**. Enter a published custom algorithm for the UTC week starting Monday. Its version is fixed for that week. An entry joins future hourly rounds; no past rounds are backfilled.

All entrants in a round receive the same frozen posts and user-neutral features. Their top five distinct token discoveries are compared using observed USD prices 24 hours later. Missing prices are marked unmeasured, not zero. Three measured samples are needed to rank.

Post-to-pick delay measures time from a selected post's publication to its hourly selection. It is separate from token launch time. Price discovery, reader engagement and opt-in realized USDC Spot results appear as separate metrics. A price-discovery score is not a simulated trade return. Actual results require recorded finalized round trips; network fees are excluded.
