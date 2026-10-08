package com.rallydot.app

import android.app.Application
import android.content.Intent
import android.os.Bundle
import android.net.Uri
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.enableEdgeToEdge
import androidx.activity.viewModels
import coil.ImageLoader
import coil.ImageLoaderFactory
import coil.decode.SvgDecoder

class RallyApplication: Application(), ImageLoaderFactory {
    override fun newImageLoader()=ImageLoader.Builder(this).components { add(SvgDecoder.Factory()) }.crossfade(140).respectCacheHeaders(true).build()
}
class RallyActivity: ComponentActivity() {
    private val model: RallyViewModel by viewModels()
    override fun onCreate(savedInstanceState: Bundle?) { super.onCreate(savedInstanceState);enableEdgeToEdge(); setContent { RallyApp(model,::openBrowser,intent?.data) } }
    override fun onNewIntent(intent: Intent) { super.onNewIntent(intent);setIntent(intent); model.bootstrap(); setContent { RallyApp(model,::openBrowser,intent.data) } }
    private fun openBrowser(url: String) {
        val uri=Uri.parse(url)
        if(uri.scheme!="https" || uri.host.isNullOrBlank() || uri.userInfo!=null) { model.message("Invalid link");return }
        try { startActivity(Intent(Intent.ACTION_VIEW,uri)) } catch (_: Exception) { model.message("Install a browser to approve wallet or account requests. Rally's screens work without one.") }
    }
}
