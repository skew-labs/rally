package com.rallydot.app

import android.app.Application
import android.net.Uri
import android.util.Base64
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONObject
import java.security.MessageDigest
import java.security.SecureRandom

data class AppState(val boot: JSONObject?=null, val pages: Map<String,Page> = emptyMap(), val message: String?=null, val connecting: Boolean=false, val connectionCode: String?=null, val busy: Boolean=false, val bootError: String?=null,val walletOpen: Boolean=false,val orderDetails: Boolean=false,val order: OrderProgress=OrderProgress())
class RallyViewModel(application: Application): AndroidViewModel(application) {
    val api=RallyApi(application)
    private val mutable=MutableStateFlow(AppState())
    val state=mutable.asStateFlow()
    private val jobs=mutableMapOf<String,Job>()
    private var connection: Job?=null
    private val chartReads=linkedMapOf<String,Pair<Long,Deferred<JSONObject>>>()
    private val assetReads=linkedMapOf<String,Pair<Long,Deferred<Asset?>>>()
    val wallet=NativeWallet(application,api) { refreshBoot() }
    private val pendingOrders=DurableOrders(application)
    private var orderJob: Job?=null
    private val orderEngine=OrderEngine(object:OrderBackend {
        override suspend fun get(path: String)=api.get(path,true)
        override suspend fun post(path: String,body: JSONObject)=api.post(path,body)
    },wallet,pendingOrders,{(me?.string("id") ?: "") to (mutable.value.boot?.string("wallet")?.lowercase() ?: "")},{p->mutable.update { it.copy(order=p) }})
    suspend fun resolveAsset(id: String): Asset?=withContext(Dispatchers.Main.immediate) {
        if(id!="MON" && !Regex("0x[0-9a-fA-F]{40}").matches(id))return@withContext null
        val key=id.lowercase()
        val saved=assetReads[key]?.takeIf { System.currentTimeMillis()-it.first<30000 && !it.second.isCancelled }
        val task=saved?.second ?: viewModelScope.async(start=CoroutineStart.LAZY) {
            val data=api.get(if(id=="MON")"/api/markets" else "/api/market-asset?address="+Uri.encode(id))
            val value=if(id=="MON")data.objects("tokens").firstOrNull { it.string("id")=="MON" } else data.optJSONObject("token") ?: data.optJSONObject("asset") ?: data.takeIf { it.has("symbol") }
            value?.let { exactAsset(it,id) }
        }.also {
            assetReads.remove(key)?.second?.cancel();assetReads[key]=System.currentTimeMillis() to it
            while(assetReads.size>12)assetReads.remove(assetReads.keys.first())?.second?.cancel()
        }
        task.await()
    }
    private fun chartRead(asset: Asset,period: String): Deferred<JSONObject> {
        val key=asset.key+":"+period
        chartReads[key]?.takeIf { System.currentTimeMillis()-it.first<20000 && !it.second.isCancelled }?.let { return it.second }
        chartReads.remove(key)?.second?.cancel()
        val pending=viewModelScope.async(start=CoroutineStart.LAZY) {
            if(asset.raw.optBoolean("nadfun")) {
                val candles=api.get("/api/nadfun/chart?token="+Uri.encode(asset.id)+"&interval="+if(period=="1D")"15" else "60")
                nadChart(candles,asset.id,if(period=="1D")1 else 7)
            } else {
                if(asset.kind=="spot" && asset.id.startsWith("0x"))api.get("/api/market-asset?address="+Uri.encode(asset.id))
                val id=if(asset.kind=="prediction")asset.raw.optJSONObject("assetInfo")?.string("chartMarket") ?: asset.id else asset.id
                api.get("/api/market-chart?asset="+Uri.encode(id)+"&kind="+(if(asset.kind=="prediction")"perps" else asset.kind)+"&period=$period")
            }
        }
        chartReads[key]=System.currentTimeMillis() to pending
        while(chartReads.size>6)chartReads.remove(chartReads.keys.first())?.second?.cancel()
        return pending
    }
    fun warmChart(asset: Asset) { chartRead(asset,"1D").start() }
    suspend fun chart(asset: Asset,period: String): JSONObject=withContext(Dispatchers.Main.immediate) { chartRead(asset,period).await() }
    private fun clearCharts() { chartReads.values.forEach { it.second.cancel() };chartReads.clear();assetReads.values.forEach { it.second.cancel() };assetReads.clear() }
    private val drafts=DraftCache()
    fun draftKey(community: String?)=DraftIdentity(me?.string("id") ?: "guest",community.orEmpty())
    fun draft(key: DraftIdentity)=drafts.get(key)
    fun saveDraft(key: DraftIdentity,value: PostDraft) {
        if(key.account==(me?.string("id") ?: "guest"))drafts.save(key,value)
    }
    fun discardDraft(key: DraftIdentity) { drafts.remove(key) }
    private fun bounded(pages: Map<String,Page>): Map<String,Page> = if(pages.size<=16)pages else pages.entries.sortedByDescending { it.value.at }.take(16).associate { it.toPair() }
    val me get() = mutable.value.boot?.optJSONObject("me")
    init { bootstrap();viewModelScope.launch { delay(1200);wallet.restore() } }
    fun message(value: String?) { mutable.update { it.copy(message=value) } }
    private suspend fun refreshBoot(): JSONObject {
        val data=api.get("/api/bootstrap?markets=0",true)
        val changed=me?.string("id")!=data.optJSONObject("me")?.string("id")
        if(changed) { jobs.values.forEach { it.cancel() };jobs.clear();clearCharts();drafts.clear() }
        mutable.update { it.copy(boot=data,bootError=null,pages=if(changed)emptyMap() else it.pages) };return data
    }
    fun bootstrap() { viewModelScope.launch { try { refreshBoot();val pending=pendingOrders.read();if(pending!=null && pending.string("account")==me?.string("id") && orderJob?.isActive!=true)mutable.update { it.copy(order=OrderProgress(if(pending.has("tx"))"pending" else "unknown",if(pending.has("tx"))"Check transaction" else "Check your wallet",pending.string("tx").takeIf { h->h.isNotBlank() })) } } catch(e:CancellationException) { throw e } catch (_: Exception) { mutable.update { it.copy(bootError="Account connection unavailable") } } } }
    fun showOrderDetails(open: Boolean=true) { mutable.update { it.copy(orderDetails=open) } }
    fun showWallet(open: Boolean=true) { mutable.update { it.copy(walletOpen=open) } }
    fun walletAction(action: suspend NativeWallet.()->Unit) { viewModelScope.launch { try { wallet.action();refreshBoot() } catch(e:Exception) { message(e.message) } } }
    private fun nativeAction(kind: String,create: suspend ()->JSONObject) {
        if(me==null || !wallet.state.value.ready || wallet.state.value.address?.lowercase()!=mutable.value.boot?.string("wallet")?.lowercase()) { showWallet();return }
        if(orderJob?.isActive==true || mutable.value.order.blocksOrder) { message("Check your pending transaction first");return }
        orderJob=viewModelScope.launch {
            try { val expected=me?.string("id");wallet.renewSession();require(me?.string("id")==expected) { "Account changed" };orderEngine.execute(kind,create);api.clearCache();refreshBoot() } catch(e:Exception) { message(e.message) }
        }
    }
    fun trade(value: NativeTrade)=nativeAction(if(value.asset.kind=="spot" && !value.asset.raw.optBoolean("nadfun"))"spot" else "execution") { createNativeTrade(api,value) }
    fun execute(args: JSONObject)=nativeAction("execution") { api.post("/api/execution/plan",args) }
    fun subscribe(feed: JSONObject)=nativeAction("payment") { checkedNativeSubscription(api.post("/api/payments/checkout",JSONObject().put("feed",feed.string("id"))),feed) }
    fun launchToken(data: JSONObject,key: String,fee: String)=nativeAction("execution") {
        val draft=api.post("/api/nadfun/draft",data,key)
        api.post("/api/execution/plan",JSONObject().put("venue","nadfun").put("kind","create").put("draft",draft.string("id"))).also {
            require(java.math.BigDecimal(it.getJSONObject("summary").string("amount")).compareTo(java.math.BigDecimal(fee))==0) { "Creation fee changed. Reopen the launch form." }
        }
    }
    fun recoverOrder(hash: String?=null) {
        if(orderJob?.isActive==true)return
        orderJob=viewModelScope.launch { try { wallet.renewSession();orderEngine.recover(hash);api.clearCache();refreshBoot() } catch(e:Exception) { message(e.message) } }
    }
    fun load(key: String,path: String,field: String,force: Boolean=false,append: Boolean=false,retain: Boolean=false) {
        if(!force && !append && (mutable.value.pages[key]?.at ?: 0) > System.currentTimeMillis()-20000) return
        if(!force && jobs[key]?.isActive==true)return
        jobs[key]?.cancel()
        jobs[key]=viewModelScope.launch {
            val previous=mutable.value.pages[key] ?: Page()
            mutable.update { it.copy(pages=it.pages+(key to previous.copy(loading=!(retain && previous.items.isNotEmpty()),error=null))) }
            try {
                val data=api.get(path,force || append)
                val incoming=data.objects(field)
                val preserving=retain && previous.items.isNotEmpty()
                val merged=mergePageItems(previous.items,incoming,append || preserving)
                val cursor=if(preserving)previous.cursor else data.string("nextCursor",data.string("cursor")).ifBlank { if(!data.isNull("nextOffset"))data.optInt("nextOffset").toString() else "" }.takeIf { it.isNotBlank() }
                mutable.update { it.copy(pages=bounded(it.pages+(key to Page(merged,cursor,data.optInt("total",data.optInt("totalPools",merged.size)),false,null,System.currentTimeMillis())))) }
            } catch(e: CancellationException) { throw e } catch(e: Exception) {
                mutable.update { it.copy(pages=it.pages+(key to previous.copy(loading=false,error=if(e is ApiFailure)e.message else "Can't connect. Check your connection and retry."))) }
            }
        }
    }
    suspend fun quote(asset: Asset,side: String,amount: String): JSONObject {
        require(validAmount(amount))
        return if(asset.raw.optBoolean("nadfun")) api.post("/api/nadfun/quote",JSONObject().put("token",asset.id).put("kind",side).put("amount",amount).put("slippage",100))
        else api.post("/api/routes", JSONObject().put("input",if(side=="buy")"MON" else asset.id).put("output",if(side=="buy")asset.id else "MON").put("amount",amount))
    }
    fun action(path: String,body: JSONObject,key: String?=null,done: (JSONObject)->Unit = {}) {
        if(me==null) { message("Sign in from Profile to continue");return }
        if(mutable.value.busy)return
        mutable.update { it.copy(busy=true) }
        viewModelScope.launch { try { val data=api.post(path,body,key);api.clearCache();done(data);bootstrap() } catch(e:Exception) { message(e.message ?: "Could not complete this action") } finally { mutable.update { it.copy(busy=false) } } }
    }
    fun refreshSocial() { mutable.update { it.copy(pages=it.pages.filterKeys { key->!key.startsWith("feed:") }) } }
    private var connectionURL: String?=null
    fun resumeConnect(open: (String)->Unit) { connectionURL?.let(open) }
    fun connect(open: (String)->Unit) {
        if(mutable.value.connecting)return
        connection?.cancel()
        connection=viewModelScope.launch {
            mutable.update { it.copy(connecting=true,message=null) }
            try {
                val random=ByteArray(32).also { SecureRandom().nextBytes(it) }
                val verifier=Base64.encodeToString(random,Base64.NO_WRAP or Base64.URL_SAFE or Base64.NO_PADDING)
                val challenge=Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray()),Base64.NO_WRAP or Base64.URL_SAFE or Base64.NO_PADDING)
                val request=api.post("/api/native/start",JSONObject().put("challenge",challenge))
                mutable.update { it.copy(connectionCode=request.string("code")) }
                connectionURL=request.string("url");open(request.string("url"))
                var failures=0
                withTimeout(request.optLong("expiresIn",600).coerceIn(60,600)*1000) {
                    while(true) {
                        delay(2500)
                        val result=try { api.post("/api/native/poll",JSONObject().put("id",request.string("id")).put("verifier",verifier)).also { failures=0 } } catch(e: CancellationException) { throw e } catch(e: Exception) {
                            if(e is ApiFailure && e.status in 400..499 && e.status!=429)throw e
                            if(++failures>=8)throw e
                            delay(2500);continue
                        }
                        when(result.string("state")) {
                            "approved" -> { jobs.values.forEach { it.cancel() };jobs.clear();clearCharts();drafts.clear();api.signIn(result.string("session"));mutable.update { it.copy(boot=null,pages=emptyMap()) };bootstrap();message("Connected");break }
                            "denied" -> { message("Connection cancelled");break }
                        }
                    }
                }
            } catch(e: CancellationException) { if(e is TimeoutCancellationException)message("Connection expired. Try again.") } catch(e: Exception) { message(e.message ?: "Could not connect") }
            finally { connectionURL=null;mutable.update { it.copy(connecting=false,connectionCode=null) } }
        }
    }
    fun cancelConnect() { connection?.cancel() }
    fun signOut() { if(mutable.value.busy || orderJob?.isActive==true) { message("Finish the current request first");return };mutable.value=AppState(busy=true);jobs.values.forEach { it.cancel() };jobs.clear();clearCharts();drafts.clear();viewModelScope.launch { try { wallet.signOut();api.post("/api/auth/logout",JSONObject()) } catch (_: Exception) { } finally { api.signOut(); mutable.value=AppState();bootstrap() } } }
    fun walletURL(asset: Asset,side: String,amount: String): String = Uri.parse(ORIGIN+"/native-wallet").buildUpon().appendQueryParameter("nativeAction","trade").appendQueryParameter("asset",asset.id).appendQueryParameter("kind",asset.kind).appendQueryParameter("side",side).appendQueryParameter("amount",amount).appendQueryParameter("venue",if(asset.raw.optBoolean("nadfun"))"nadfun" else asset.venue).appendQueryParameter("account",me?.string("id")).build().toString()
}
