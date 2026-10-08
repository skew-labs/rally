# Android

Rally for Android is a Kotlin and Jetpack Compose application. Navigation, markets, launch discovery, Swipe, token sheets, price charts, community feeds, discovery, algorithm previews, rankings and profiles render inside the application. It does not embed a WebView or launch a Trusted Web Activity. The package is `com.rallydot.app`, with Android 7.0 (API 24) as the minimum and API 36 as the target.

[Download the signed APK](https://rallydot.com/assets/rally-android-0.2.0.apk)

## Interaction and data

- Five destinations use bottom navigation on phones and a navigation rail on wider displays. System insets and the on-screen keyboard are included in screen and sheet layout.
- Swipe uses a native vertical pager with one adjacent page prepared. Horizontal drags also move between tokens. Buy and Sell open a sheet over the current screen.
- Token sheets show real provider history on a native Canvas, with a drag crosshair. nad.fun tokens use the token-specific nad.fun chart endpoint; other markets use the normalized market-chart endpoint. Missing history stays missing.
- Light and dark palettes share blue Buy and red Sell controls. System typography, native pressed states and Compose transitions provide feedback. Android's animation-duration setting applies to Compose animations.
- Token discovery is paginated. Visible market screens refresh while the activity is started. Images use Coil's caches, public thumbnail URLs and SVG decoding.
- Social posts, replies, reactions and community joins use the existing authenticated API. Selected photos and videos upload from the system document picker; videos play through Media3. Post publishing uses a stable idempotency key per draft. Upload retries remain explicit.

OkHttp requests use fixed HTTPS API paths, bounded response bodies and cancellable calls. Catalog responses have a short, bounded in-memory cache. Account changes clear data and reject responses from the previous session. An interrupted request preserves the visible list and offers Retry. The app does not queue transactions offline.

## Account and wallet boundary

The first account connection uses an explicit first-party browser consent screen. The app holds a random verifier and sends its S256 challenge to Rally. A matching code, authenticated human consent, a three-minute expiry and an atomic one-use exchange bind the connection to that device. This creates a regular Rally session, not an agent OAuth grant or a wallet signing permission. The session is encrypted using Android Keystore; application backup is disabled.

The native order sheet hands the chosen asset, side and amount to Rally's existing secure browser checkout. Wallet login, signing, paid subscriptions and token issuance currently use that checkout. The web controllers remain responsible for quote validation, chain checks, wallet authorization and receipt reconciliation. Native screens never receive wallet keys or sign transactions. Account identifiers are checked at the handoff to prevent checkout under another browser account.

The main application works without Chrome. Account consent and wallet checkout require an installed compatible browser. Native wallet SDK integration is a separate boundary from native screen rendering.

## Build and release

Use JDK 17, Android SDK/build tools 36 and the pinned Gradle wrapper on a remote Linux builder. Kotlin, the Compose compiler and Compose BOM are pinned to a mutually compatible SDK 36 toolchain. Release builds use R8 and resource shrinking; retain each build's mapping file privately.

```sh
cd android
./gradlew :app:assembleRelease :app:testDebugUnitTest :app:lintRelease
```

Release signing reads `RALLY_ANDROID_KEYSTORE` and `RALLY_ANDROID_STORE_PASSWORD` from the build environment, with alias `rally`. Signing material is not stored in source or application assets. Version 0.2.0 (code 4) uses the existing release certificate, allowing upgrades from the earlier browser-based APKs.

`/.well-known/assetlinks.json` associates the release certificate with app entry paths and `/native-return`. API, download and consent URLs remain outside those app links. Certificate changes require reviewing the domain association and upgrade path.

## Verification

Model tests cover missing and invalid prices, exact token/venue identity, unavailable execution, amount validation, image URL schemes and chart normalization. Backend tests cover pairing expiry, cross-origin isolation, consent requirements, verifier mismatch, replay and competing claims. Browser integration is tested with isolated QA identities; those tests do not assert funded mainnet fills.

Native Android emulator checks cover operation with Chrome disabled, live public market reads, native token charts, sheets, paging and screen sizes. Physical-device, OEM and funded trading checks remain distinct from emulator and fixture evidence.

The design uses [FOMO's official product imagery](https://fomo.family/) for compact token and trade presentation, [Meta's Threads performance report](https://engineering.fb.com/2024/12/18/ios/how-we-think-about-threads-ios-performance/) for separate navigation and rendering measurements, and [Android accessibility guidance](https://developer.android.com/guide/topics/ui/accessibility/apps) for touch targets. These are design references, not claims of equivalent performance.
