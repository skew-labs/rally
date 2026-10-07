# Android

Rally's Android application opens the same HTTPS product in a Chrome Trusted Web Activity. Markets, social feeds, algorithm access and transaction reconciliation share the web application's code and origin. The Android package has no wallet keys, custody backend, JavaScript signing bridge or separate trading engine.

The browser owns cookies, passkeys, uploads, embedded-wallet signing and external wallet handoffs. A verified Digital Asset Link binds `rallydot.com` to the package's release certificate. An unverified origin retains browser chrome; the app does not conceal a failed origin check.

## Mobile interaction

- Installed mode uses a stable bottom navigation bar and system safe areas.
- Sheets use the visible viewport when the keyboard opens. Background navigation hides during input.
- Android Back closes the top sheet before leaving its market. Nested asset pickers keep the underlying trade open.
- Drag a sheet header downward to dismiss it; short drags return to their starting position. Keyboard input, pending financial actions and submitted trades block this gesture.
- Sheet entry and dismissal use one interruptible motion track. Touch controls give immediate pressed feedback and respect reduced-motion preferences.
- Swipe reuses the existing bounded card window, gesture handling and reduced-motion controls.
- Financial preparation, wallet authorization, deadlines and receipt verification are the existing application handlers.

Authentication and trading require a network connection. A navigation-only service worker supplies a Rally recovery screen when the app cannot connect or its upstream returns a server error. It stores no responses, excludes API and authentication requests, and has no transaction queue. Reconnecting restores the requested URL through the existing live application.

The connection layer bounds read requests and response bodies, preserves caller cancellation, and shows an offline indicator without replacing an open form. It adds no deadline or automatic retry to writes. Android links cover the app entry paths and authorization page; API and download URLs remain browser links.

## Build

Requirements: JDK 17, Android SDK 36, build tools, and the pinned Gradle wrapper. Minimum Android version is 7.0 (API 24); target API is 36. The launcher uses Android Browser Helper 2.7.4. Release builds use R8 code optimization and resource shrinking; retain each build's mapping file privately for crash analysis. Build on a suitable remote Linux host.

```sh
cd android
./gradlew :app:assembleDebug :app:lintDebug
```

Release signing uses `RALLY_ANDROID_KEYSTORE` and `RALLY_ANDROID_STORE_PASSWORD` from the build environment. Keep the keystore and password private. They are not application assets or wallet credentials. The alias is `rally`.

```sh
./gradlew :app:assembleRelease :app:lintRelease
```

Publish the release certificate's SHA-256 fingerprint in `android-assetlinks.json`, served at `/.well-known/assetlinks.json`, before testing trusted fullscreen mode. A replacement signing key requires updating that association and affects application upgrades. Reuse the existing release key for subsequent APKs.

The public web manifest describes installed display mode and brand icons. Mobile-specific presentation lives in `mobile-ui.js` and `mobile.css`; it has no account or financial authority.

## Release 0.1.2

The signed APK is [available here](https://rallydot.com/assets/rally-android-0.1.2.apk). It uses the same package and release certificate as the previous releases for in-place upgrades. The optimized package is 567,235 bytes. Android Browser Helper remains pinned to the current stable 2.7.4 release.

## Design references

The mobile revision reviewed [FOMO's official product imagery](https://fomo.family/) for compact token identity and trade controls, [Meta's Threads performance report](https://engineering.fb.com/2024/12/18/ios/how-we-think-about-threads-ios-performance/) for separate navigation and rendering measurements, and [Android accessibility guidance](https://developer.android.com/guide/topics/ui/accessibility/apps) for touch targets. These references describe design goals, not a claim of matching another app's performance.

[Service worker lifecycle and network handling](https://developer.chrome.com/docs/workbox/service-worker-overview) describes the offline recovery boundary.

[Chrome's Trusted Web Activity documentation](https://developer.chrome.com/docs/android/trusted-web-activity) explains the browser and origin-verification boundary.
