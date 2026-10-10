package com.rallydot.app

import android.app.Application
import android.net.Uri
import android.util.Base64
import androidx.lifecycle.AndroidViewModel
import androidx.lifecycle.viewModelScope
import kotlinx.coroutines.*
import kotlinx.coroutines.channels.Channel
import kotlinx.coroutines.selects.select
import kotlinx.coroutines.selects.onTimeout
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import org.json.JSONObject
import java.security.MessageDigest
import java.security.SecureRandom

data class AppState(val boot: JSONObject?=null, val portfolio: JSONObject?=null,val portfolioError: String?=null,val walletPanel: String?=null, val pages: Map<String,Page> = emptyMap(), val reactions: Map<String,PostReaction> = emptyMap(),val message: String?=null, val connecting: Boolean=false, val connectionCode: String?=null, val busy: Boolean=false, val bootError: String?=null,val walletOpen: Boolean=false,val orderDetails: Boolean=false,val order: OrderProgress=OrderProgress())
class RallyViewModel @JvmOverloads constructor(application: Application,val api: RallyApi=RallyApi(application),private val pendingPairing: DurablePairing=DurablePairing(application)): AndroidViewModel(application) {
    private val mutable=MutableStateFlow(AppState())
    val state=mutable.asStateFlow()
    private val jobs=mutableMapOf<String,Job>()
    private var portfolioJob: Job?=null
    private var connection: Job?=null
    private val connectionWake=Channel<Unit>(Channel.CONFLATED)
    private var walletJob: Job?=null
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
    init { bootstrap();restoreConnect();viewModelScope.launch { delay(1200);wallet.restore() } }
    fun message(value: String?) { mutable.update { it.copy(message=value) } }
    private suspend fun refreshBoot(): JSONObject {
        val version=api.sessionVersion
        val data=api.get("/api/bootstrap?markets=0",true)
        if(version!=api.sessionVersion)throw CancellationException("Account changed")
        val changed=me?.string("id")!=data.optJSONObject("me")?.string("id") || mutable.value.boot?.string("wallet")!=data.string("wallet")
        if(changed) { portfolioJob?.cancel();jobs.values.forEach { it.cancel() };jobs.clear();clearCharts();drafts.clear() }
        mutable.update { it.copy(boot=data,bootError=null,portfolio=if(changed)null else it.portfolio,portfolioError=if(changed)null else it.portfolioError,walletPanel=if(changed)null else it.walletPanel,pages=if(changed)emptyMap() else it.pages,reactions=if(changed)emptyMap() else it.reactions) };return data
    }
    fun bootstrap() { viewModelScope.launch { try { refreshBoot();val pending=pendingOrders.read();if(pending!=null && pending.string("account")==me?.string("id") && orderJob?.isActive!=true)mutable.update { it.copy(order=OrderProgress(if(pending.has("tx"))"pending" else "unknown",if(pending.has("tx"))"Check transaction" else "Check your wallet",pending.string("tx").takeIf { h->h.isNotBlank() })) } } catch(e:CancellationException) { throw e } catch (_: Exception) { mutable.update { it.copy(bootError="Account connection unavailable") } } } }
    fun showWalletPanel(panel: String?) { if(panel!=null && mutable.value.boot?.string("wallet").isNullOrBlank()) { showWallet();return };mutable.update { it.copy(walletPanel=panel) };if(panel=="send")loadPortfolio() }
    fun loadPortfolio(force: Boolean=false) {
        val wallet=mutable.value.boot?.string("wallet").orEmpty();val account=me?.string("id").orEmpty()
        if(wallet.isBlank() || account.isBlank())return
        if(portfolioJob?.isActive==true)return
        if(!force && mutable.value.portfolio?.let { !it.optBoolean("refreshing") && System.currentTimeMillis()/1000-it.optLong("attemptAt")<30 }==true)return
        portfolioJob=viewModelScope.launch {
            repeat(16) { attempt->
                try {
                    val p=api.get("/api/portfolio",true)
                    if(me?.string("id")!=account || mutable.value.boot?.string("wallet")!=wallet)return@launch
                    require(p.string("wallet").equals(wallet,true)) { "Wallet changed" }
                    mutable.update { it.copy(portfolio=p,portfolioError=null) }
                    if(!p.optBoolean("refreshing"))return@launch
                } catch(e:CancellationException) { throw e } catch(_:Exception) { mutable.update { it.copy(portfolioError="Balances are temporarily unavailable. Your last snapshot is kept.") };return@launch }
                delay(if(attempt==0)350 else 1500)
            }
        }
    }
    fun showOrderDetails(open: Boolean=true) { mutable.update { it.copy(orderDetails=open) } }
    fun showWallet(open: Boolean=true) { mutable.update { it.copy(walletOpen=open) } }
    fun walletAction(action: suspend NativeWallet.()->Unit) {
        if(walletJob?.isActive==true)return
        walletJob=viewModelScope.launch { try { wallet.action();refreshBoot() } catch(e:CancellationException){throw e} catch(e:Exception) { message(e.message) } }
    }
    fun cancelWalletLogin() { walletJob?.cancel() }
    fun resumeAccount() { restoreConnect();connectionWake.trySend(Unit);bootstrap();viewModelScope.launch { wallet.restore() } }
    fun returnedToApp(url: String?) { if(pairingReturn(url)) { restoreConnect();connectionWake.trySend(Unit) } }
    private fun nativeAction(kind: String,create: suspend ()->JSONObject) {
        if(me==null || !wallet.state.value.ready || wallet.state.value.address?.lowercase()!=mutable.value.boot?.string("wallet")?.lowercase()) { showWallet();return }
        if(orderJob?.isActive==true || mutable.value.order.blocksOrder) { message("Check your pending transaction first");return }
        orderJob=viewModelScope.launch {
            try { val expected=me?.string("id");wallet.renewSession();require(me?.string("id")==expected) { "Account changed" };orderEngine.execute(kind,create);api.clearCache();refreshBoot();loadPortfolio(true) } catch(e:Exception) { message(e.message) }
        }
    }
    fun trade(value: NativeTrade)=nativeAction(if(value.asset.kind=="spot" && !value.asset.raw.optBoolean("nadfun"))"spot" else "execution") { createNativeTrade(api,value) }
    fun execute(args: JSONObject)=nativeAction("execution") { api.post("/api/execution/plan",args) }
    fun sendAsset(holding: JSONObject,recipient: String,amount: String)=nativeAction("execution") {
        val args=JSONObject().put("venue","wallet").put("kind","send").put("asset",holding.string("asset")).put("recipient",recipient).put("amount",amount)
        checkedNativeTransfer(api.post("/api/execution/plan",args),holding,recipient,amount)
    }
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
                val refreshed=if(field=="posts")incoming.map { it.string("id") }.toSet() else emptySet()
                mutable.update { it.copy(pages=bounded(it.pages+(key to Page(merged,cursor,data.optInt("total",data.optInt("totalPools",merged.size)),false,null,System.currentTimeMillis()))),reactions=it.reactions.filter { (id,value)->id !in refreshed || value.pending }) }
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
        if(me==null) { showWallet();return }
        if(mutable.value.busy)return
        mutable.update { it.copy(busy=true) }
        viewModelScope.launch { try { val data=api.post(path,body,key);api.clearCache();done(data);bootstrap() } catch(e:Exception) { message(e.message ?: "Could not complete this action") } finally { mutable.update { it.copy(busy=false) } } }
    }
    fun react(post: Post) {
        val account=me?.string("id") ?: run { showWallet();return }
        if(mutable.value.reactions[post.id]?.pending==true)return
        val version=api.sessionVersion;val current=post.withReaction(mutable.value.reactions[post.id])
        val before=PostReaction(current.liked,current.likes);val next=PostReaction(!current.liked,(current.likes+if(current.liked)-1 else 1).coerceAtLeast(0),true)
        fun patch(value: PostReaction) { mutable.update { state->
            val values=LinkedHashMap(state.reactions);values.remove(post.id);values[post.id]=value
            while(values.size>128) { val old=values.entries.firstOrNull { !it.value.pending } ?: break;values.remove(old.key) }
            state.copy(reactions=values)
        } }
        patch(next)
        viewModelScope.launch {
            try {
                val result=api.post("/api/reaction",JSONObject().put("post",post.id).put("kind","like").put("active",next.liked))
                if(version!=api.sessionVersion || me?.string("id")!=account)return@launch
                require(result.has("liked") && result.has("likes")) { "Reaction confirmation unavailable" }
                patch(PostReaction(result.optBoolean("liked"),result.optInt("likes").coerceAtLeast(0)));api.clearCache()
            }catch(e:CancellationException){
                if(me?.string("id")==account && mutable.value.reactions[post.id]==next)patch(before)
                throw e
            }catch(e:Exception){
                if(version==api.sessionVersion && me?.string("id")==account){patch(before);message(e.message ?: "Couldn't save reaction. Try again.")}
            }
        }
    }
    fun refreshSocial() { mutable.update { it.copy(pages=it.pages.filterKeys { key->!key.startsWith("feed:") }) } }
    private var connectionURL: String?=null
    fun resumeConnect(open: (String)->Unit) { connectionURL?.let(open) }
    private fun restoreConnect() {
        if(connection?.isActive==true)return
        val saved=try { pendingPairing.read() } catch(_:Exception) { runCatching { pendingPairing.clear() };null }
        if(saved!=null)connection=viewModelScope.launch { completeConnect(saved) }
    }
    @OptIn(ExperimentalCoroutinesApi::class)
    private suspend fun completeConnect(request: NativePairing) {
        mutable.update { it.copy(connecting=true,connectionCode=request.code,message=null) };connectionURL=request.url
        try {
            var failures=0
            withTimeout((request.expires-System.currentTimeMillis()/1000).coerceAtLeast(1)*1000) {
                while(true) {
                    val result=try { api.post("/api/native/poll",request.poll()).also { failures=0 } } catch(e:CancellationException) { throw e } catch(e:Exception) {
                        if(e is ApiFailure && e.status in 400..499 && e.status!=429) { pendingPairing.clear();throw e }
                        if(++failures>=8)throw e
                        delay(2500);continue
                    }
                    when(result.string("state")) {
                        "approved" -> {
                            api.signIn(result.string("session"))
                            jobs.values.forEach { it.cancel() };jobs.clear();clearCharts();drafts.clear()
                            // Keep the proof until the authenticated bootstrap succeeds.
                            val boot=refreshBoot();require(boot.optJSONObject("me")!=null) { "Account connection did not complete" }
                            pendingPairing.clear();mutable.update { it.copy(walletOpen=false) };message("Connected");break
                        }
                        "denied" -> { pendingPairing.clear();message("Connection cancelled");break }
                    }
                    select<Unit> { connectionWake.onReceive { };onTimeout(2500) { } }
                }
            }
        } catch(e:CancellationException) { if(e is TimeoutCancellationException) { pendingPairing.clear();message("Connection expired. Try again.") } else throw e }
        catch(e:Exception) { message(e.message ?: "Connection interrupted. Return to Rally to continue.") }
        finally { connectionURL=null;mutable.update { it.copy(connecting=false,connectionCode=null) } }
    }
    fun connect(open: (String)->Unit) {
        if(mutable.value.connecting) { return }
        val saved=runCatching { pendingPairing.read() }.getOrNull()
        if(saved!=null) { restoreConnect();open(saved.url);return }
        connection?.cancel()
        connection=viewModelScope.launch {
            mutable.update { it.copy(connecting=true,message=null) }
            try {
                val random=ByteArray(32).also { SecureRandom().nextBytes(it) }
                val verifier=Base64.encodeToString(random,Base64.NO_WRAP or Base64.URL_SAFE or Base64.NO_PADDING)
                val challenge=Base64.encodeToString(MessageDigest.getInstance("SHA-256").digest(verifier.toByteArray()),Base64.NO_WRAP or Base64.URL_SAFE or Base64.NO_PADDING)
                val request=api.post("/api/native/start",JSONObject().put("challenge",challenge))
                val durable=NativePairing.fromStart(request,verifier)
                pendingPairing.save(durable)
                mutable.update { it.copy(connectionCode=durable.code) }
                connectionURL=durable.url;open(durable.url);completeConnect(durable)
            } catch(e: CancellationException) { if(e is TimeoutCancellationException)message("Connection expired. Try again.") } catch(e: Exception) { message(e.message ?: "Could not connect") }
            finally { connectionURL=null;mutable.update { it.copy(connecting=false,connectionCode=null) } }
        }
    }
    fun cancelConnect() { connection?.cancel();runCatching { pendingPairing.clear() } }
    fun signOut() { portfolioJob?.cancel();if(mutable.value.busy || orderJob?.isActive==true) { message("Finish the current request first");return };cancelConnect();mutable.value=AppState(busy=true);jobs.values.forEach { it.cancel() };jobs.clear();clearCharts();drafts.clear();viewModelScope.launch { try { try{RallyPush.disable(getApplication(),api)}catch(_:Exception){};wallet.signOut();api.post("/api/auth/logout",JSONObject()) } catch (_: Exception) { } finally { api.signOut(); mutable.value=AppState();bootstrap() } } }
    fun walletURL(asset: Asset,side: String,amount: String): String = Uri.parse(ORIGIN+"/native-wallet").buildUpon().appendQueryParameter("nativeAction","trade").appendQueryParameter("asset",asset.id).appendQueryParameter("kind",asset.kind).appendQueryParameter("side",side).appendQueryParameter("amount",amount).appendQueryParameter("venue",if(asset.raw.optBoolean("nadfun"))"nadfun" else asset.venue).appendQueryParameter("account",me?.string("id")).build().toString()
}
