# Android

Rally for Android is a Kotlin and Jetpack Compose application. Navigation, markets, launch discovery, Swipe, token sheets, price charts, community feeds, discovery, algorithm previews, rankings and profiles render inside the application. The main interface does not wrap the website or launch a Trusted Web Activity. Privy manages its internal wallet infrastructure. The package is `com.rallydot.app`, with Android 9 (API 28) as the minimum and API 36 as the target.

[Download the signed APK](https://rallydot.com/assets/rally-android-0.3.0.apk)

## Interaction and data

- Five destinations use Rally's floating bottom navigation on phones and a navigation rail on wider displays. Bundled Inter fonts, navigation artwork and the light/dark color palette match the mobile web product. System insets and the on-screen keyboard are included in screen and sheet layout.
- Swipe uses a native vertical pager with one adjacent page prepared. Spot connects public social posts to their exact asset; Perps and Prediction use actual venue markets and pools; Memes opens the nad.fun token deck. Horizontal drags move the card with the finger and settle in the same direction; short drags return to the current page. Buy and Sell open a sheet over the current screen. Landscape switches social cards to two columns, and large text reduces the preview while preserving the actions.
- Token sheets show real provider history on a native Canvas, with a drag crosshair. nad.fun tokens use the token-specific nad.fun chart endpoint; other markets use the normalized market-chart endpoint. Missing history stays missing. Current and next token charts are warmed in a bounded cache; opening a sheet joins the same in-flight read instead of requesting it again. Account changes cancel these reads.
- Light and dark palettes share blue Buy and red Sell controls. Native pressed states and Compose transitions provide feedback. Android's animation-duration setting applies to Compose animations. Official agent artwork uses a white backing so black brand marks remain legible in either theme.
- Token discovery is paginated. Background quote refreshes update the existing token identities without reordering the visible list or showing a pull-to-refresh spinner. Main destinations retain list position, search and pager state, with a bounded, account-scoped state cache. Images use regular Coil composition, bounded caches, public thumbnail URLs and SVG decoding.
- Social posts, replies, reactions and community joins use the existing authenticated API. Selected photos and videos upload from the system document picker; videos play through Media3. Post publishing uses a stable idempotency key per draft. Upload retries remain explicit. In-memory drafts retain text, selected media and request identity across closing/reopening and rotation, and are cleared on account changes. They do not persist after process death.
- Discover uses square artwork tiles and native filters for algorithms, photos and videos. Algorithm tiles display provider-reported performance and actual subscription prices; unavailable returns display a dash. Public asset reads use a bounded shared cache, and a provider response must match the requested token before a social card can open its order sheet.

OkHttp requests use fixed HTTPS API paths, bounded response bodies and cancellable calls. Catalog responses have a short, bounded in-memory cache. Account changes clear data and reject responses from the previous session. An interrupted request preserves the visible list and offers Retry. The app does not queue transactions offline.

The Meta and xAI marks use bundled PNG renderings of the original SVGs listed in [`agent-brand-sources.json`](../assets/agent-brand-sources.json). This preserves the SVG masks and filters that Android's image decoder does not support. The artwork identifies external services; it does not imply endorsement or a connected vendor account.

## Motion and startup

The system splash screen shows Rally branding and exits with a short fade into the first native frame. It never waits for an API response or an artificial minimum duration. Day/night resources and system-bar contrast follow the chosen theme. Reduced motion skips the splash fade and uses Android's duration scale for Compose transitions.

Tab selection uses one moving indicator, and destination transitions use a small offset and fade. The purchase sheet keeps its action separate from the scrollable body and above the keyboard; chart space collapses while typing. Short trade sheets prioritize amount and order controls over charts, and secondary token statistics remain in the browsing view. Close actions animate the token sheet out before removing it. Chart paths and fills are cached for the current data and bounds; crosshair movement redraws without rebuilding that geometry and selects observations by their actual timestamps.

Moving indicators, pressed controls, scrolling lists, pagers and sheets use Compose's `preferredFrameRate(FrameRateCategory.High)` during redraws. Card translations, press scaling and the segmented indicator update through graphics layers without relaying out their content for every animation frame. [Android's adaptive refresh guidance](https://developer.android.com/develop/ui/views/animations/adaptive-refresh-rate) describes the system-controlled vote: compatible displays may use their supported high rates, including 144 Hz where available. The app does not force 144 Hz, cap all screens at 60 Hz or keep a continuous rendering loop running while idle. Device hardware, Android version, thermal limits and power settings determine the actual rate. A 60 Hz emulator does not establish physical-device 144 fps performance.

Inter and Material Symbols license notices are bundled in the APK under `assets/licenses`.

The `baselineprofile` module records startup and public browsing/order-sheet journeys on a connected Android device. Generated startup and baseline profiles are bundled into the release and installed with AndroidX ProfileInstaller. Generate them after changing those journeys:

```sh
cd android
./gradlew :app:generateReleaseBaselineProfile
./gradlew :app:assembleRelease
```

The generator never submits a wallet request. [Android's Baseline Profile guidance](https://developer.android.com/topic/performance/baselineprofiles/create-baselineprofile) recommends physical-device benchmarks for measuring speed improvements; an emulator run confirms profile generation and behavior only.

## Account and wallet boundary

The native Privy SDK supports email codes and Google login. Google authentication opens the provider's browser authorization page and returns through `rallywallet`; trade screens and embedded-wallet signing stay inside Rally. The public Android client configuration is returned by `/api/auth/config`. Register `com.rallydot.app`, the release certificate fingerprint and the `rallywallet` scheme in the Privy Android app client. `RALLY_PRIVY_ANDROID_CLIENT_ID` is separate from the web client; App Secrets and release signing keys never enter the APK.

The server verifies Privy access and identity tokens against the existing app audience, then returns a first-party session cookie. A domain- and chain-bound wallet challenge connects the embedded wallet to the account. If an existing account uses a different wallet, the app shows both addresses and requires the user's explicit choice before linking the new wallet. This does not move balances from the previous wallet.

Native Buy/Sell uses the same quote, approval, preflight and receipt APIs as the web application. Spot routes compare actual quoted venues and try a bounded set of executable compilers. nad.fun curve and DEX trades, perpetual requests, fixed-stake price predictions, token creation and subscriptions retain their venue-specific server builders. Subscription invoices must match the displayed feed, price, currency, period and version before signing; token creation must match the displayed creation fee. Perpl funding uses AUSD, shown separately from wallet balances. Server availability, wallet funds, venue collateral and a valid current market determine whether a request can execute.

Before calling the embedded wallet, the app checks the linked account/address, chain 143, recipient, calldata, bounded gas and quote expiry. The provider switches to Monad's public RPC and verifies `eth_chainId`; private server RPC credentials stay on the server. Exact token approvals are confirmed before preparing a fresh execution request. The SDK retains wallet keys; Rally stores only its account session and encrypted pending intent/hash.

A pending intent is committed to storage before the wallet request. Once returned, its transaction hash is committed before any network reconciliation. A timeout after submission blocks another order. Recovery checks the same owned reference and hash without signing again, including after a process restart. A manually entered incorrect hash can be corrected until the server verifies it. Confirmed inclusion, keeper pending, no fill, partial fill, finalized execution and active subscription entitlement have distinct results.

External wallets retain the optional first-party browser pairing flow. A random S256 verifier, matching device code, authenticated human consent, ten-minute expiry and atomic one-use exchange create a regular Rally session. This is not an agent OAuth grant or native access to an external wallet's private key. External-wallet signing is handled by its existing browser/wallet flow; the native signing path described above uses Privy embedded wallets.

## Build and release

Use JDK 17, Android SDK/build tools 36 and the pinned Gradle wrapper on a remote Linux builder. Kotlin, the Compose compiler and Compose BOM are pinned to a mutually compatible SDK 36 toolchain. Release builds use R8 and resource shrinking; retain each build's mapping file privately.

```sh
cd android
./gradlew :app:assembleRelease :app:testDebugUnitTest :app:lintRelease
```

Release signing reads `RALLY_ANDROID_KEYSTORE` and `RALLY_ANDROID_STORE_PASSWORD` from the build environment, with alias `rally`. Signing material is not stored in source or application assets. Version 0.3.0 (code 9) uses the existing release certificate, allowing upgrades from the earlier APKs.

`/.well-known/assetlinks.json` associates the release certificate with app entry paths and `/native-return`. API, download and consent URLs remain outside those app links. Certificate changes require reviewing the domain association and upgrade path.

## Verification

Model tests cover missing and invalid prices, exact token/venue identity, unavailable execution, amount validation, image URL schemes and chart normalization. Backend tests cover pairing expiry, cross-origin isolation, consent requirements, verifier mismatch, replay and competing claims. Browser integration is tested with isolated QA identities; those tests do not assert funded mainnet fills.

Native Android emulator checks cover operation with Chrome disabled, live public market reads, native token charts, sheets, paging and screen sizes. Physical-device, OEM and funded trading checks remain distinct from emulator and fixture evidence.

Version 0.2.2 passed 22 model tests, both baseline-profile journeys and release lint with zero errors. Native interaction checks verified retained market/search/pager state, horizontal finger tracking and snap-back, keyboard-visible Buy controls, launcher return and reduced motion. The social post deck, Perp and Prediction decks, nad.fun deck and Discover filters were checked with live public data. Layout checks covered a small phone, 1.5× text, landscape and a tablet. A compact caption preserves the complete accessibility label for Prediction at large text sizes. These checks made no wallet requests or financial transactions. Offline recovery was also verified in the preceding native release.

The design uses [FOMO's official product imagery](https://fomo.family/) for compact token and trade presentation, [Meta's Threads performance report](https://engineering.fb.com/2024/12/18/ios/how-we-think-about-threads-ios-performance/) for separate navigation and rendering measurements, and [Android accessibility guidance](https://developer.android.com/guide/topics/ui/accessibility/apps) for touch targets. These are design references, not claims of equivalent performance.

Version 0.2.3 adds branded wallet entry, a focused browser account screen and recovery for interrupted account pairing. Reopening the browser uses the same pending request and device code. Transient polling failures retry within the original expiry; cancellation and missing-browser failures restore the connection control. The release passed 22 model tests and lint with zero errors; emulator checks covered both profile themes, large text, browser handoff, return, reuse and cancellation. These checks did not sign a real wallet or submit a transaction.
Version 0.2.4 unifies public social and nad.fun swipe cards under one native pager. Horizontal releases use distance and velocity, resist deck boundaries and settle without a second full-width entrance. Card translations, chart resizing and chart scrubbing avoid recomposing the full trading sheet on every frame. Artwork decoding is constrained to its rendered size, and social lists reuse typed content. Primary navigation uses short fades, while Home sections use small directional transitions.

The trade sheet uses a large amount field with an explicit denomination, separate Buy and Sell colors, a faster cancellable quote debounce and a footer that remains above the keyboard. Market rows constrain long prices and venue names. Secondary text is darker in the light palette for readability on quiet surfaces. Wallet handoff and server-side execution validation are unchanged.

Version 0.2.4 passed 25 model tests, both baseline-profile journeys and release lint with zero errors. Native checks covered gesture thresholds and deck boundaries, retained navigation state, light/dark order sheets, keyboard-visible Buy and Sell controls, reduced motion, and public market, community and algorithm screens. Small-phone, 1.5× text, landscape and tablet layouts passed. These checks made no wallet requests or financial transactions; they do not establish physical-device 144 Hz frame performance.

Version 0.3.0 adds the Privy Android wallet integration, native order submission, token creation, subscription payment, wallet balances and Perpl funding controls. AndroidX DataStore modules are aligned on 1.1.7 to resolve a first-start file-read race in the SDK's transitive storage dependency. Fresh baseline profiles cover startup and browsing/order-sheet journeys.

The signed release passed 40 native unit tests, 34 backend authentication tests and release lint with zero errors. Unit tests cover transaction identity and chain validation, quote expiry, approval sequencing, interrupted submission, duplicate prevention, account changes, venue outcomes and changed subscription terms. Emulator checks passed three fresh-data starts, small-phone, 1.5× text, landscape and tablet purchase/login layouts, keyboard-visible actions, native Perpl size/protection fields and both login themes. No user completed authentication, signed a real wallet request or submitted a financial transaction in these checks.
