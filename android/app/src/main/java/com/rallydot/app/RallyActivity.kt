package com.rallydot.app

import android.animation.ValueAnimator
import android.app.Application
import android.content.Intent
import android.os.Bundle
import android.net.Uri
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.setValue
import androidx.core.splashscreen.SplashScreen.Companion.installSplashScreen
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.decode.SvgDecoder
import coil.memory.MemoryCache
import coil.disk.DiskCache

class RallyApplication: Application(), ImageLoaderFactory {
    override fun onCreate() { super.onCreate();RallyPush.restore(this) }
    private var walletSDK: io.privy.sdk.Privy?=null
    val externalWallet: ExternalWallet by lazy { ExternalWallet(this) }
    fun privy(app: String,client: String): io.privy.sdk.Privy {
        check(android.os.Looper.myLooper()==android.os.Looper.getMainLooper())
        return walletSDK ?: io.privy.sdk.Privy.init(this,io.privy.sdk.PrivyConfig(app,client,io.privy.logging.PrivyLogLevel.NONE)).also { walletSDK=it }
    }
    override fun newImageLoader()=ImageLoader.Builder(this)
        .components { add(SvgDecoder.Factory()) }
        .memoryCache { MemoryCache.Builder(this).maxSizePercent(.15).build() }
        .diskCache { DiskCache.Builder().directory(cacheDir.resolve("artwork")).maxSizeBytes(32L*1024*1024).build() }
        .crossfade(100).respectCacheHeaders(true).build()
}
class RallyActivity: ComponentActivity() {
    private val model: RallyViewModel by viewModels()
    private var incomingLink by mutableStateOf<Uri?>(null)
    override fun onCreate(savedInstanceState: Bundle?) {
        val splash=installSplashScreen()
        super.onCreate(savedInstanceState)
        enableEdgeToEdge()
        incomingLink=RallyPush.incoming(intent) ?: intent?.data
        // Render immediately; network requests never extend the starting screen.
        splash.setOnExitAnimationListener { provider ->
            if(android.os.Build.VERSION.SDK_INT<26 || ValueAnimator.areAnimatorsEnabled()) {
                provider.view.animate().alpha(0f).setDuration(120L).withEndAction { provider.remove() }.start()
            } else provider.remove()
        }
        setContent { RallyApp(model,::openBrowser,incomingLink) }
    }
    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent);setIntent(intent)
        incomingLink=RallyPush.incoming(intent) ?: intent.data
        model.bootstrap()
    }
    override fun onResume() { super.onResume();model.resumeAccount() }
    private fun openBrowser(url: String) {
        val uri=Uri.parse(url)
        if(uri.scheme!="https" || uri.host.isNullOrBlank() || uri.userInfo!=null) { model.message("Invalid link");return }
        try { startActivity(Intent(Intent.ACTION_VIEW,uri)) } catch (_: Exception) { model.cancelConnect();model.message("Install a browser to connect your account securely.") }
    }
}
