package com.rallydot.app

import android.app.Application
import io.privy.sdk.Privy
import io.privy.sdk.PrivyConfig
import io.privy.logging.PrivyLogLevel
import io.privy.auth.oAuth.OAuthProvider
import io.privy.wallet.ethereum.EmbeddedEthereumWallet
import io.privy.wallet.ethereum.EthereumRpcRequest
import io.privy.wallet.ethereum.EthereumChain
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.asStateFlow
import kotlinx.coroutines.flow.update
import kotlinx.coroutines.withTimeout
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.coroutines.TimeoutCancellationException
import org.json.JSONArray
import org.json.JSONObject

data class WalletView(val configured: Boolean=false,val ready: Boolean=false,val address: String?=null,val busy: Boolean=false,
    val email: String="",val codeSent: Boolean=false,val error: String?=null,val phase: String?=null,val externalConfigured: Boolean=false,val external: Boolean=false,val completed: Int=0)

class NativeWallet(private val application: Application,private val api: RallyApi,private val boot: suspend ()->JSONObject): NativeSigner {
    private val mutable=MutableStateFlow(WalletView())
    val state=mutable.asStateFlow()
    private var sdk: Privy?=null
    private val external=(application as RallyApplication).externalWallet
    init { external.onDisconnected={mutable.update { it.copy(ready=if(it.external)false else it.ready) }} }
    suspend fun configureExternal(): Boolean {
        val id=api.get("/api/auth/config").getJSONObject("privy").string("walletConnectProjectId")
        val enabled=Regex("[a-fA-F0-9]{32}").matches(id)
        mutable.update { it.copy(externalConfigured=enabled) }
        if(enabled)external.initialize(id)
        return enabled
    }
    private suspend fun client(): Privy {
        sdk?.let { withTimeout(20000) { it.awaitReady() };return it }
        val config=api.get("/api/auth/config",true).getJSONObject("privy")
        val id=config.string("androidClientId")
        require(config.optBoolean("enabled") && id.isNotBlank()) { "Email and Google wallet login is being configured. Try again shortly." }
        val app=application as RallyApplication
        val p=app.privy(config.string("appId"),id);sdk=p
        withTimeout(20000) { p.awaitReady() }
        mutable.update { it.copy(configured=true) };return p
    }
    suspend fun restore() {
        if(mutable.value.busy)return
        try {
            if(configureExternal()) {
                val address=external.restored()
                if(address!=null && boot().string("wallet").equals(address,true)) { mutable.update { it.copy(ready=true,address=address,external=true) };return }
            }
            val p=client();val user=withTimeout(20000) { p.getUser() }
            val data=boot();val wallet=data.string("wallet")
            if(!mutable.value.busy)mutable.update { it.copy(ready=user!=null,address=user?.embeddedEthereumWallets?.firstOrNull { w->w.address.equals(wallet,true) }?.address ?: user?.embeddedEthereumWallets?.firstOrNull()?.address,external=false) }
        } catch(e:CancellationException) { throw e } catch(_:Exception) { mutable.update { it.copy(ready=false) } }
    }
    private suspend fun authenticated(p: Privy) {
        var user=p.getUser() ?: error("Finish signing in first")
        if(user.embeddedEthereumWallets.isEmpty())user.createEthereumWallet().getOrThrow()
        user.refresh().getOrThrow();user=p.getUser() ?: error("Sign in again")
        val token=user.getAccessToken().getOrThrow();val identity=user.identityToken ?: error("Identity verification is unavailable")
        api.post("/api/auth/privy",JSONObject().put("accessToken",token).put("identityToken",identity))
        val data=boot();val linked=data.string("wallet")
        val wallet=user.embeddedEthereumWallets.firstOrNull { it.address.equals(linked,true) } ?: user.embeddedEthereumWallets.firstOrNull() ?: error("Wallet was not created")
        mutable.update { it.copy(ready=true,address=wallet.address,codeSent=false,error=null,external=false,phase="Connecting…") }
        if(linked.isBlank())link()
        if(boot().string("wallet").equals(wallet.address,true))mutable.update { it.copy(completed=it.completed+1) }
    }
    private suspend fun task(action: suspend ()->Unit) {
        require(!mutable.value.busy) { "A wallet request is already in progress" }
        mutable.update { it.copy(busy=true,error=null,phase="Connecting…") }
        try { action() } catch(e:TimeoutCancellationException) {
            mutable.update { it.copy(error="Connection expired. Try again.") }
        } catch(e:CancellationException) { throw e } catch(e:Exception) {
            val message=if(e.message=="Failed to launch OAuth browser")googleFailure() else e.message?.take(500) ?: "Could not connect. Try again."
            mutable.update { it.copy(error=message) }
        } finally { mutable.update { it.copy(busy=false,phase=null) } }
    }
    suspend fun sendCode(email: String)=task {
        require(android.util.Patterns.EMAIL_ADDRESS.matcher(email.trim()).matches()) { "Enter your email" }
        client().email.sendCode(email.trim()).getOrThrow()
        mutable.update { it.copy(email=email.trim(),codeSent=true) }
    }
    suspend fun verifyCode(code: String)=task {
        require(Regex("[0-9]{6}").matches(code)) { "Enter the six-digit code" }
        val p=client();p.email.loginWithCode(code,mutable.value.email).getOrThrow();authenticated(p)
    }
    suspend fun google()=task { val p=client();mutable.update { it.copy(phase="Continue in Google") };withTimeout(300000) { p.oAuth.login(OAuthProvider.Google,"rallywallet").getOrThrow() };authenticated(p) }
    suspend fun continueSession()=task { if(mutable.value.external) { renewSession();mutable.update { it.copy(completed=it.completed+1) } } else authenticated(client()) }
    suspend fun connectExternal(brand: ExternalWalletBrand)=task {
        require(configureExternal()) { "Direct wallet connections are being configured" }
        val before=boot();val owner=before.optJSONObject("me")?.string("id");val linked=before.string("wallet")
        mutable.update { it.copy(phase="Open ${brand.name}") }
        val address=external.connect(brand)
        require(linked.isBlank() || linked.equals(address,true)) { "Choose the wallet linked to this account, or sign out to use a different account." }
        val linking=owner!=null
        val proof=api.post(if(linking)"/api/wallet/challenge" else "/api/auth/wallet/challenge",JSONObject().put("address",address))
        val message=checkedLoginProof(proof,address,linking)
        require(boot().optJSONObject("me")?.string("id")==owner) { "Account changed. Connect again." }
        mutable.update { it.copy(phase="Sign in ${brand.name}") }
        val hex="0x"+message.toByteArray(Charsets.UTF_8).joinToString("") { "%02x".format(it.toInt() and 255) }
        val signature=external.rpc("personal_sign",JSONArray().put(hex).put(address))
        require(Regex("0x[0-9a-fA-F]{130}").matches(signature)) { "Could not read the wallet signature" }
        checkedLoginProof(proof,address,linking)
        require(boot().optJSONObject("me")?.string("id")==owner && external.restored()?.equals(address,true)==true) { "Wallet or account changed. Connect again." }
        api.post(if(linking)"/api/wallet/verify" else "/api/auth/wallet/verify",JSONObject().put("id",proof.string("id")).put("signature",signature))
        require(boot().string("wallet").equals(address,true)) { "Wallet connection did not complete" }
        external.persist();mutable.update { it.copy(ready=true,address=address,external=true,completed=it.completed+1) }
    }
    fun installed(brand: ExternalWalletBrand)=external.installed(brand)
    suspend fun renewSession() {
        if(mutable.value.external) { require(external.restored()?.equals(mutable.value.address,true)==true && boot().string("wallet").equals(mutable.value.address,true)) { "Reconnect your wallet" };return }
        val user=client().getUser() ?: error("Sign in again")
        api.post("/api/auth/privy",JSONObject().put("accessToken",user.getAccessToken().getOrThrow()).put("identityToken",user.identityToken ?: error("Sign in again")))
        boot()
    }
    suspend fun link() {
        val wallet=selected();val challenge=api.post("/api/wallet/challenge",JSONObject().put("address",wallet.address))
        val message=checkedLoginProof(challenge,wallet.address,true)
        val signature=wallet.provider.request(EthereumRpcRequest.personalSign(message,wallet.address)).getOrThrow().data
        api.post("/api/wallet/verify",JSONObject().put("id",challenge.string("id")).put("signature",signature));boot()
    }
    private suspend fun selected(): EmbeddedEthereumWallet {
        val user=client().getUser() ?: error("Connect your Rally wallet")
        val chosen=mutable.value.address ?: error("Connect your Rally wallet")
        return user.embeddedEthereumWallets.singleOrNull { it.address.equals(chosen,true) } ?: error("Wallet changed. Reconnect it.")
    }
    override suspend fun address(): String=if(mutable.value.external)external.restored() ?: error("Reconnect your wallet") else selected().address
    override suspend fun send(transaction: JSONObject): String {
        if(mutable.value.external) {
            val address=mutable.value.address ?: throw WalletNotSent("Reconnect your wallet")
            val tx=try { require(external.restored()?.equals(address,true)==true);checkedNativeTransaction(transaction,address) } catch(_:Exception){throw WalletNotSent("Wallet changed. Reconnect it.")}
            return external.rpc("eth_sendTransaction",JSONArray().put(tx),"eip155:143")
        }
        val wallet=try { selected() } catch(e:Exception) { throw WalletNotSent(e.message ?: "Reconnect your wallet") }
        val tx=try {
            val checked=checkedNativeTransaction(transaction,wallet.address)
            wallet.provider.switchChain(EthereumChain.Custom("https://rpc.monad.xyz"))
            val chain=wallet.provider.request(EthereumRpcRequest("eth_chainId",emptyList())).getOrThrow().data
            require(chain.trim('"').lowercase() in setOf("0x8f","143")) { "Wallet provider is not on Monad mainnet" }
            checked
        } catch(e:Exception) { throw WalletNotSent(e.message ?: "Wallet network unavailable") }
        return wallet.provider.request(EthereumRpcRequest.ethSendTransaction(tx.toString())).getOrThrow().data
    }
    suspend fun signOut() { external.disconnect();sdk?.logout();mutable.value=WalletView(configured=sdk!=null) }

    // Privy 0.16 collapses OAuth configuration errors into a generic browser error.
    // Probe only that failed initialization, using public identifiers and a throwaway PKCE challenge.
    private suspend fun googleFailure(): String=withContext(Dispatchers.IO) {
        try {
            val config=api.get("/api/auth/config",true).getJSONObject("privy")
            val random=java.security.SecureRandom();val bytes=ByteArray(32).also { random.nextBytes(it) }
            val code=android.util.Base64.encodeToString(java.security.MessageDigest.getInstance("SHA-256").digest(bytes),android.util.Base64.NO_WRAP or android.util.Base64.URL_SAFE or android.util.Base64.NO_PADDING)
            val data=JSONObject().put("provider","google").put("redirect_to","rallywallet://privy-oauth").put("code_challenge",code).put("state_code",code)
            val conn=java.net.URL("https://auth.privy.io/api/v1/oauth/init").openConnection() as java.net.HttpURLConnection
            try {
                conn.connectTimeout=5000;conn.readTimeout=5000;conn.requestMethod="POST";conn.doOutput=true;conn.instanceFollowRedirects=false
                mapOf("Content-Type" to "application/json","User-Agent" to "okhttp/4.12.0","privy-app-id" to config.string("appId"),"privy-client-id" to config.string("androidClientId"),"privy-client" to "android:0.16.0","x-native-app-identifier" to BuildConfig.APPLICATION_ID).forEach { (k,v)->conn.setRequestProperty(k,v) }
                conn.outputStream.use { it.write(data.toString().toByteArray()) }
                if(conn.responseCode in 400..499) {
                    val body=conn.errorStream?.use { input->val bytes=ByteArray(8192);val n=input.read(bytes);if(n>0)String(bytes,0,n) else "" }.orEmpty()
                    when(runCatching { JSONObject(body).string("code") }.getOrNull()) {
                        "invalid_native_app_id" -> return@withContext "Google login needs the Rally Android app identifier enabled in Privy. Please try again after setup."
                        "disallowed_login_method" -> return@withContext "Google login needs to be enabled for Rally in Privy. Please try again after setup."
                    }
                }
            } finally { conn.disconnect() }
        } catch(_:Exception) { }
        "Google sign-in couldn't start. Check your connection and try again."
    }
}
class DurableOrders(application: Application): PendingOrders {
    private val store=CredentialStore(application,"native-pending-order",true)
    override fun read(): JSONObject?=store.load()?.let { JSONObject(it) }
    override fun save(value: JSONObject)=store.save(value.toString())
    override fun clear()=store.clear()
}
