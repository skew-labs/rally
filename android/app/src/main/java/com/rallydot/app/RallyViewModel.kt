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

data class AppState(val boot: JSONObject?=null, val pages: Map<String,Page> = emptyMap(), val message: String?=null, val connecting: Boolean=false, val connectionCode: String?=null, val busy: Boolean=false, val bootError: String?=null)
class RallyViewModel(application: Application): AndroidViewModel(application) {
    val api=RallyApi(application)
    private val mutable=MutableStateFlow(AppState())
    val state=mutable.asStateFlow()
    private val jobs=mutableMapOf<String,Job>()
    private var connection: Job?=null
    private fun bounded(pages: Map<String,Page>): Map<String,Page> = if(pages.size<=16)pages else pages.entries.sortedByDescending { it.value.at }.take(16).associate { it.toPair() }
    val me get() = mutable.value.boot?.optJSONObject("me")
    init { bootstrap() }
    fun message(value: String?) { mutable.update { it.copy(message=value) } }
    fun bootstrap() { viewModelScope.launch { try { val data=api.get("/api/bootstrap?markets=0",true);mutable.update { it.copy(boot=data,bootError=null) } } catch(e:CancellationException) { throw e } catch (_: Exception) { mutable.update { it.copy(bootError="Account connection unavailable") } } } }
    fun load(key: String,path: String,field: String,force: Boolean=false,append: Boolean=false,retain: Boolean=false) {
        if(!force && !append && (mutable.value.pages[key]?.at ?: 0) > System.currentTimeMillis()-20000) return
        jobs[key]?.cancel()
        jobs[key]=viewModelScope.launch {
            val previous=mutable.value.pages[key] ?: Page()
            mutable.update { it.copy(pages=it.pages+(key to previous.copy(loading=true,error=null))) }
            try {
                val data=api.get(path,force || append)
                val incoming=data.objects(field)
                val preserving=retain && previous.items.size>incoming.size
                val merged=when { append->previous.items+incoming;preserving->incoming+previous.items;else->incoming }.distinctBy { it.string("venue")+":"+it.string("id",it.string("address")) }
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
                open(request.string("url"))
                withTimeout(180000) {
                    while(true) {
                        delay(2500)
                        val result=api.post("/api/native/poll",JSONObject().put("id",request.string("id")).put("verifier",verifier))
                        when(result.string("state")) {
                            "approved" -> { jobs.values.forEach { it.cancel() };jobs.clear();api.signIn(result.string("session"));mutable.update { it.copy(boot=null,pages=emptyMap()) };bootstrap();message("Connected");break }
                            "denied" -> { message("Connection cancelled");break }
                        }
                    }
                }
            } catch(e: CancellationException) { message("Connection expired. Try again.") } catch(e: Exception) { message(e.message ?: "Could not connect") }
            finally { mutable.update { it.copy(connecting=false,connectionCode=null) } }
        }
    }
    fun cancelConnect() { connection?.cancel() }
    fun signOut() { if(mutable.value.busy)return;mutable.value=AppState(busy=true);jobs.values.forEach { it.cancel() };jobs.clear();viewModelScope.launch { try { api.post("/api/auth/logout",JSONObject()) } catch (_: Exception) { } finally { api.signOut(); mutable.value=AppState();bootstrap() } } }
    fun walletURL(asset: Asset,side: String,amount: String): String = Uri.parse(ORIGIN+"/native-wallet").buildUpon().appendQueryParameter("nativeAction","trade").appendQueryParameter("asset",asset.id).appendQueryParameter("kind",asset.kind).appendQueryParameter("side",side).appendQueryParameter("amount",amount).appendQueryParameter("venue",if(asset.raw.optBoolean("nadfun"))"nadfun" else asset.venue).appendQueryParameter("account",me?.string("id")).build().toString()
}
