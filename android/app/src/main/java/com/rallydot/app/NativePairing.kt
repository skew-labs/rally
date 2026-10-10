package com.rallydot.app

import android.content.Context
import org.json.JSONObject
import java.net.URI

/** Persisted before the browser opens. This is an account proof, never a wallet key. */
data class NativePairing(val id: String,val verifier: String,val code: String,val expires: Long) {
    val url get()="$ORIGIN/connect-native?nativeRequest=$id&view=account"
    fun json()=JSONObject().put("id",id).put("verifier",verifier).put("code",code).put("expires",expires)
    fun poll()=JSONObject().put("id",id).put("verifier",verifier)
    companion object {
        fun read(data: JSONObject,now: Long=System.currentTimeMillis()/1000): NativePairing {
            val id=data.string("id");val verifier=data.string("verifier");val code=data.string("code");val expires=data.optLong("expires")
            require(Regex("[a-f0-9]{32}").matches(id) && Regex("[A-Za-z0-9_-]{43}").matches(verifier) && Regex("[0-9]{4}").matches(code) && expires>now && expires<=now+600) { "Connection expired. Try again." }
            return NativePairing(id,verifier,code,expires)
        }
        fun fromStart(data: JSONObject,verifier: String,now: Long=System.currentTimeMillis()/1000): NativePairing {
            val pending=read(JSONObject(data.toString()).put("verifier",verifier).put("expires",now+data.optLong("expiresIn")),now)
            require(data.string("url")==pending.url) { "Connection does not belong to Rally" }
            return pending
        }
    }
}
fun pairingReturn(raw: String?): Boolean = runCatching {
    val uri=URI(raw ?: "")
    (uri.scheme=="https" && uri.host=="rallydot.com" && uri.port==-1 && uri.rawUserInfo==null && uri.path=="/native-return") ||
        (uri.scheme=="rallyconnect" && uri.host=="account" && uri.rawUserInfo==null && uri.port==-1)
}.getOrDefault(false)
class DurablePairing(context: Context,namespace: String="native-pending-pairing") {
    private val store=CredentialStore(context,namespace,true)
    fun read(): NativePairing?=store.load()?.let { NativePairing.read(JSONObject(it)) }
    fun save(value: NativePairing)=store.save(value.json().toString())
    fun clear()=store.clear()
}
