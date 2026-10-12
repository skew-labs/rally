package com.rallydot.app

import android.webkit.*
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.material3.MaterialTheme
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.toArgb
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.Lifecycle
import androidx.lifecycle.LifecycleEventObserver
import androidx.lifecycle.compose.LocalLifecycleOwner

private val referenceCoins=mapOf("MON" to "monad","BTC" to "bitcoin","ETH" to "ethereum","SOL" to "solana","HYPE" to "hyperliquid","PENGU" to "pudgy-penguins","LINK" to "chainlink","ONDO" to "ondo-finance","AAVE" to "aave","PEPE" to "pepe","UNI" to "uniswap","USDC" to "usd-coin","ZEC" to "zcash","LIT" to "lighter","VVV" to "venice-token","PUMP" to "pump-fun","NEAR" to "near")
data class ProviderTarget(val token: String?=null,val coin: String?=null) {
    fun url(dark: Boolean,interval: String="1m"): String?=token?.let { "https://www.geckoterminal.com/monad/tokens/$it?embed=1&info=0&swaps=0&light_chart=${if(dark)0 else 1}&chart_type=price&resolution=${if(interval in listOf("1m","15m","1h","4h"))interval else "1m"}&bg_color=${if(dark)"17181c" else "ffffff"}" }
}
fun providerTarget(asset: Asset): ProviderTarget? {
    if(asset.kind!="spot")return null
    val address=asset.raw.string("address",asset.id).lowercase()
    if(asset.kind=="spot" && Regex("0x[0-9a-f]{40}").matches(address) && address!="0x"+"0".repeat(40)) {
        if(asset.raw.optInt("chainId",143)!=143 || asset.raw.optBoolean("nadfun") && !asset.raw.optBoolean("graduated"))return null
        return ProviderTarget(token=address)
    }
    return referenceCoins[if(asset.kind=="spot")asset.id else asset.symbol]?.let { ProviderTarget(coin=it) }
}
fun allowedProviderNavigation(url: String): Boolean=runCatching {
    val uri=java.net.URI(url)
    uri.scheme=="https" && uri.userInfo==null && uri.port in listOf(-1,443) && uri.host in listOf("www.geckoterminal.com","widgets.coingecko.com")
}.getOrDefault(false)

@Composable fun ProviderPriceChart(target: ProviderTarget,dark: Boolean,interval: String="1m",onFailure: ()->Unit) {
    val failed by rememberUpdatedState(onFailure)
    val lifecycle=LocalLifecycleOwner.current.lifecycle
    val background=MaterialTheme.colorScheme.surface.toArgb()
    var view by remember { mutableStateOf<WebView?>(null) }
    DisposableEffect(lifecycle,view) {
        val observer=LifecycleEventObserver { _,event->if(event==Lifecycle.Event.ON_PAUSE)view?.onPause() else if(event==Lifecycle.Event.ON_RESUME)view?.onResume() }
        lifecycle.addObserver(observer);onDispose { lifecycle.removeObserver(observer) }
    }
    key(target,dark,interval) {
        AndroidView(modifier=Modifier.fillMaxSize(),factory={ context->WebView(context).apply {
            view=this;setBackgroundColor(background)
            settings.javaScriptEnabled=true;settings.domStorageEnabled=true
            settings.allowFileAccess=false;settings.allowContentAccess=false
            settings.cacheMode=WebSettings.LOAD_NO_CACHE
            settings.mixedContentMode=WebSettings.MIXED_CONTENT_NEVER_ALLOW
            settings.setSupportMultipleWindows(false);settings.mediaPlaybackRequiresUserGesture=true
            CookieManager.getInstance().setAcceptThirdPartyCookies(this,false)
            webChromeClient=object:WebChromeClient() {
                override fun onPermissionRequest(request: PermissionRequest) { request.deny() }
            }
            webViewClient=object:WebViewClient() {
                override fun shouldOverrideUrlLoading(view: WebView,request: WebResourceRequest): Boolean= !allowedProviderNavigation(request.url.toString())
                override fun onReceivedError(view: WebView,request: WebResourceRequest,error: WebResourceError) { if(request.isForMainFrame)failed() }
                override fun onReceivedHttpError(view: WebView,request: WebResourceRequest,response: WebResourceResponse) { if(response.statusCode>=400 && (request.isForMainFrame || request.url.host=="api.coingecko.com" || request.url.host=="widgets.coingecko.com"))view.post { failed() } }
                override fun onReceivedSslError(view: WebView,handler: android.webkit.SslErrorHandler,error: android.net.http.SslError) { handler.cancel();failed() }
            }
            if(target.token!=null)loadUrl(target.url(dark,interval)!!)
            else {
                val coin=target.coin?.takeIf { Regex("[a-z0-9-]{1,80}").matches(it) } ?: return@apply
                val html="""<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1"><style>html,body{margin:0;height:100%;background:${if(dark)"#17181c" else "#ffffff"};overflow:hidden}</style><script>Object.defineProperty(window,'sessionStorage',{value:{getItem:()=>null,setItem:()=>{},removeItem:()=>{}}});</script></head><body><gecko-coin-price-chart-widget coin-id="$coin" locale="en" initial-currency="usd" height="200" width="0" dark-mode="$dark" transparent-background="true" outlined="false"></gecko-coin-price-chart-widget><script src="https://widgets.coingecko.com/gecko-coin-price-chart-widget.js"></script></body></html>"""
                loadDataWithBaseURL("https://widgets.coingecko.com/",html,"text/html","UTF-8",null)
            }
        }},onRelease={ it.stopLoading();it.loadUrl("about:blank");it.destroy();if(view===it)view=null })
    }
}
