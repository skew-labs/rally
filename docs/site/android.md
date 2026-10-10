# Android app

Rally's Android app renders markets, charts, Swipe, feeds and profiles natively, using the same account and server data as the web app.

## Install Rally

Download the [signed Android APK](https://rallydot.com/assets/rally-android-0.4.1.apk) from rallydot.com. The current package is `com.rallydot.app`, version **0.4.1**. Android 9 or later is required.

When installing a downloaded APK, Android may ask you to allow installation from the app used to download it. Use the official file rather than a re-signed copy from an unknown source.

## Log in and connect a wallet

Choose Google, email or a wallet from Profile. Google opens its secure authorization page and returns to Rally. The login sheet closes after a successful connection.

If you leave Google before finishing, return to Rally and cancel the pending attempt to choose a method again. Repeated taps do not start additional login requests.

When direct wallet connections are enabled, select an installed MetaMask, Rainbow or Trust Wallet, then approve its connection and Rally sign-in request. Your wallet controls its approval screens. Other connections can use the first-party browser pairing flow. Embedded-wallet signing happens through Privy's native SDK. Rally does not receive either wallet's keys. Verify the linked address before funding it.

## Trade inside the app

Open a market, choose Buy or Sell, set the amount and approve the wallet request. Native panels use the server's current transaction plans and follow the resulting transfer or position.

If an app interruption occurs after submission, the saved pending request can be reconciled on return. Do not send a second transaction just because the app was closed. See [Order status](trading.md).

## Display and motion

The app follows device-supported refresh behavior for navigation, pressed controls and scrolling. Actual frame rates depend on the device, operating system and power or thermal conditions.

Support for larger text and different screen sizes remains part of the native layout. A high-refresh display does not change a venue's execution or chain finality.


## Signals, communities and alerts

The Feed includes **Following** and **Trades**. Create a 24-hour price signal, share selected finalized fills from Profile, set token-holder benefits and enter the weekly algorithm league. See [Signals and benefits](social-loop.md). Android lock-screen push becomes available when the deployment has configured Firebase; in-app notifications work separately.
