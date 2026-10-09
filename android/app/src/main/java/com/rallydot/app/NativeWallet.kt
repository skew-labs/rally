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
import org.json.JSONObject

data class WalletView(val configured: Boolean=false,val ready: Boolean=false,val address: String?=null,val busy: Boolean=false,
    val email: String="",val codeSent: Boolean=false,val error: String?=null)

class NativeWallet(private val application: Application,private val api: RallyApi,private val boot: suspend ()->JSONObject): NativeSigner {
    private val mutable=MutableStateFlow(WalletView())
    val state=mutable.asStateFlow()
    private var sdk: Privy?=null
    private suspend fun client(): Privy {
        sdk?.let { return it }
        val config=api.get("/api/auth/config",true).getJSONObject("privy")
        val id=config.string("androidClientId")
        require(config.optBoolean("enabled") && id.isNotBlank()) { "Email and Google wallet login is being configured. Try again shortly." }
        val app=application as RallyApplication
        return app.privy(config.string("appId"),id).also { sdk=it;mutable.update { it.copy(configured=true) } }
    }
    suspend fun restore() {
        try {
            val p=client();val user=withTimeout(20000) { p.getUser() }
            val data=boot();val wallet=data.string("wallet")
            mutable.update { it.copy(ready=user!=null,address=user?.embeddedEthereumWallets?.firstOrNull { w->w.address.equals(wallet,true) }?.address ?: user?.embeddedEthereumWallets?.firstOrNull()?.address) }
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
        mutable.update { it.copy(ready=true,address=wallet.address,codeSent=false,error=null) }
        if(linked.isBlank())link()
    }
    private suspend fun task(action: suspend ()->Unit) {
        require(!mutable.value.busy) { "A wallet request is already in progress" }
        mutable.update { it.copy(busy=true,error=null) }
        try { action() } catch(e:CancellationException) { throw e } catch(e:Exception) {
            val message=if(e.message=="Failed to launch OAuth browser")"Google sign-in couldn't open. Check your connection and try again." else e.message?.take(500) ?: "Could not connect. Try again."
            mutable.update { it.copy(error=message) }
        } finally { mutable.update { it.copy(busy=false) } }
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
    suspend fun google()=task { val p=client();p.oAuth.login(OAuthProvider.Google,"rallywallet").getOrThrow();authenticated(p) }
    suspend fun continueSession()=task { authenticated(client()) }
    suspend fun renewSession() {
        val user=client().getUser() ?: error("Sign in again")
        api.post("/api/auth/privy",JSONObject().put("accessToken",user.getAccessToken().getOrThrow()).put("identityToken",user.identityToken ?: error("Sign in again")))
        boot()
    }
    suspend fun link() {
        val wallet=selected();val challenge=api.post("/api/wallet/challenge",JSONObject().put("address",wallet.address))
        val message=challenge.string("message")
        require(message.contains("URI: $ORIGIN\n") && message.contains("Chain ID: 143\n")) { "Wallet request does not belong to Rally" }
        val signature=wallet.provider.request(EthereumRpcRequest.personalSign(message,wallet.address)).getOrThrow().data
        api.post("/api/wallet/verify",JSONObject().put("id",challenge.string("id")).put("signature",signature));boot()
    }
    private suspend fun selected(): EmbeddedEthereumWallet {
        val user=client().getUser() ?: error("Connect your Rally wallet")
        val chosen=mutable.value.address ?: error("Connect your Rally wallet")
        return user.embeddedEthereumWallets.singleOrNull { it.address.equals(chosen,true) } ?: error("Wallet changed. Reconnect it.")
    }
    override suspend fun address(): String=selected().address
    override suspend fun send(transaction: JSONObject): String {
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
    suspend fun signOut() { sdk?.logout();mutable.value=WalletView(configured=sdk!=null) }
}
class DurableOrders(application: Application): PendingOrders {
    private val store=CredentialStore(application,"native-pending-order",true)
    override fun read(): JSONObject?=store.load()?.let { JSONObject(it) }
    override fun save(value: JSONObject)=store.save(value.toString())
    override fun clear()=store.clear()
}
