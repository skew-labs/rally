package com.rallydot.app

import android.app.Application
import android.content.Intent
import android.net.Uri
import com.reown.android.Core
import com.reown.android.CoreClient
import com.reown.android.relay.ConnectionType
import com.reown.sign.client.Sign
import com.reown.sign.client.SignClient
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject

/** WalletConnect keeps signing in the selected wallet. No keys enter Rally. */
class ExternalWallet(private val application: Application) {
    private val store=CredentialStore(application,"external-wallet-session")
    private var initialized=false
    private var initJob: CompletableDeferred<Unit>?=null
    private var connection: CompletableDeferred<Sign.Model.ApprovedSession>?=null
    private var connectionTopic: String?=null
    private var pending: CompletableDeferred<String>?=null
    private var requestTopic: String?=null
    private var requestMethod: String?=null
    private var requestChain: String?=null
    private var requestId: Long?=null
    private var early: Sign.Model.SessionRequestResponse?=null
    private var selection: JSONObject?=null
    private val callbacks=CoroutineScope(SupervisorJob()+Dispatchers.Main.immediate)
    var onDisconnected: ()->Unit={}
    private val delegate=object: SignClient.DappDelegate {
        override fun onSessionApproved(approvedSession: Sign.Model.ApprovedSession) { callbacks.launch {
            val session=withContext(Dispatchers.IO) { SignClient.getActiveSessionByTopic(approvedSession.topic) }
            if(session?.pairingTopic==connectionTopic)connection?.complete(approvedSession)
        } }
        override fun onSessionRejected(rejectedSession: Sign.Model.RejectedSession) { callbacks.launch { if(rejectedSession.topic==connectionTopic)connection?.completeExceptionally(IllegalStateException("Wallet connection cancelled")) } }
        override fun onSessionUpdate(updatedSession: Sign.Model.UpdatedSession) { callbacks.launch { if(updatedSession.topic==selection?.string("topic"))onDisconnected() } }
        @Deprecated("Use the topic-scoped event")
        override fun onSessionEvent(sessionEvent: Sign.Model.SessionEvent) {}
        override fun onSessionEvent(sessionEvent: Sign.Model.Event) { callbacks.launch { if(sessionEvent.topic==selection?.string("topic"))onDisconnected() } }
        override fun onSessionExtend(session: Sign.Model.Session) {}
        override fun onSessionDelete(deletedSession: Sign.Model.DeletedSession) { callbacks.launch {
            if(deletedSession is Sign.Model.DeletedSession.Success && deletedSession.topic==selection?.string("topic")) { selection=null;store.clear();onDisconnected() }
        } }
        override fun onSessionRequestResponse(response: Sign.Model.SessionRequestResponse) { callbacks.launch {
            if(response.topic!=requestTopic || response.method!=requestMethod || response.chainId!=requestChain || pending==null)return@launch
            if(requestId==null) { early=response;return@launch }
            if(response.result.id!=requestId)return@launch
            when(val result=response.result) {
                is Sign.Model.JsonRpcResponse.JsonRpcResult -> pending?.complete(result.result?.toString().orEmpty())
                is Sign.Model.JsonRpcResponse.JsonRpcError -> pending?.completeExceptionally(when(result.code) {
                    4001 -> WalletRejected()
                    4200,-32601 -> WalletNotSent("This wallet does not support the request")
                    else -> IllegalStateException("Wallet could not complete this request")
                })
            }
        } }
        override fun onProposalExpired(proposal: Sign.Model.ExpiredProposal) { callbacks.launch { if(proposal.pairingTopic==connectionTopic)connection?.completeExceptionally(IllegalStateException("Connection expired. Try again.")) } }
        override fun onRequestExpired(request: Sign.Model.ExpiredRequest) { callbacks.launch { if(request.topic==requestTopic && request.id==requestId)pending?.completeExceptionally(IllegalStateException("Wallet request expired")) } }
        override fun onConnectionStateChange(state: Sign.Model.ConnectionState) {}
        override fun onError(error: Sign.Model.Error) { callbacks.launch { connection?.completeExceptionally(IllegalStateException("Wallet connection unavailable. Try again."));pending?.completeExceptionally(IllegalStateException("Wallet connection interrupted")) } }
    }
    suspend fun initialize(project: String) {
        require(Regex("[a-fA-F0-9]{32}").matches(project)) { "Direct wallet connections are being configured" }
        if(initialized)return
        initJob?.let { it.await();return }
        val job=CompletableDeferred<Unit>();initJob=job
        try {
            CoreClient.initialize(application=application,projectId=project,connectionType=ConnectionType.AUTOMATIC,telemetryEnabled=false,
                metaData=Core.Model.AppMetaData("Rally","Social trading on Monad",ORIGIN,listOf("$ORIGIN/assets/community-rally.png"),"rallyconnect://wallet"),
                onError={job.completeExceptionally(IllegalStateException("Wallet relay unavailable"))})
            SignClient.initialize(Sign.Params.Init(CoreClient),onSuccess={SignClient.setDappDelegate(delegate);initialized=true;job.complete(Unit)},onError={job.completeExceptionally(IllegalStateException("Wallet connection unavailable"))})
            withTimeout(20000) { job.await() }
        } finally { initJob=null }
    }
    fun installed(brand: ExternalWalletBrand): Boolean=try { application.packageManager.getPackageInfo(brand.packageName,0);true } catch(_:Exception){false}
    private fun open(brand: ExternalWalletBrand,uri: String?=null) {
        require(installed(brand)) { "Install ${brand.name} to connect this wallet" }
        val link=if(uri==null)"${brand.scheme}://" else "${brand.scheme}://wc?uri="+Uri.encode(uri)
        application.startActivity(Intent(Intent.ACTION_VIEW,Uri.parse(link)).setPackage(brand.packageName).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK))
    }
    suspend fun connect(brand: ExternalWalletBrand): String {
        require(connection==null && pending==null) { "Finish the open wallet request" }
        require(installed(brand)) { "Install ${brand.name} to connect this wallet" }
        val saved=selection ?: store.load()?.let { JSONObject(it) }
        if(saved?.string("brand")==brand.id)restored()?.let { return it }
        val result=CompletableDeferred<Sign.Model.ApprovedSession>();connection=result
        try {
            val pairing=CoreClient.Pairing.create() ?: error("Could not start a wallet connection")
            connectionTopic=pairing.topic
            SignClient.connect(Sign.Params.ConnectParams(pairing=pairing,sessionNamespaces=mapOf("eip155" to Sign.Model.Namespace.Proposal(
                chains=listOf("eip155:143","eip155:1"),methods=listOf("personal_sign","eth_sendTransaction"),events=listOf("accountsChanged","chainChanged")))),
                onSuccess={uri->try { open(brand,uri) } catch(_:Exception){result.completeExceptionally(IllegalStateException("Could not open ${brand.name}"))}},onError={result.completeExceptionally(IllegalStateException("Could not connect wallet"))})
            val session=withTimeout(180000) { result.await() }
            val (_,address)=caipWallet(session.namespaces.values.flatMap { it.accounts })
            require(session.namespaces["eip155"]?.methods?.contains("personal_sign")==true) { "Wallet does not support login signatures" }
            selection=JSONObject().put("topic",session.topic).put("address",address).put("brand",brand.id)
            return address
        } finally { connection=null;connectionTopic=null }
    }
    suspend fun restored(): String? {
        if(!initialized)return null
        val saved=selection ?: store.load()?.let { JSONObject(it) } ?: return null
        val session=withContext(Dispatchers.IO) { SignClient.getActiveSessionByTopic(saved.string("topic")) } ?: return null
        if(session.expiry<=System.currentTimeMillis()/1000)return null
        val address=caipWallet(session.namespaces.values.flatMap { it.accounts },saved.string("address")).second
        selection=saved;return address
    }
    fun persist() { store.save((selection ?: error("Connect your wallet")).toString()) }
    suspend fun rpc(method: String,params: JSONArray,chain: String?=null): String {
        if(pending!=null)throw WalletNotSent("Finish the open wallet request")
        val chosen=selection ?: throw WalletNotSent("Reconnect your wallet")
        val session=withContext(Dispatchers.IO) { SignClient.getActiveSessionByTopic(chosen.string("topic")) } ?: throw WalletNotSent("Reconnect your wallet")
        if(session.expiry<=System.currentTimeMillis()/1000 || session.namespaces["eip155"]?.methods?.contains(method)!=true)throw WalletNotSent("Reconnect your wallet for this request")
        val caip=try { caipWallet(session.namespaces.values.flatMap { it.accounts },chosen.string("address"),chain).first } catch(_:Exception){throw WalletNotSent("Reconnect this wallet on Monad")}
        val result=CompletableDeferred<String>();pending=result;requestTopic=session.topic;requestMethod=method;requestChain=caip
        try {
            SignClient.request(Sign.Params.Request(session.topic,method,params.toString(),caip),onSuccess={sent->
                callbacks.launch {
                    requestId=sent.requestId;early?.let { delegate.onSessionRequestResponse(it) };early=null
                    try { externalWalletBrands.firstOrNull { it.id==chosen.string("brand") }?.let { open(it) } }
                    catch(_:Exception){result.completeExceptionally(IllegalStateException("Open your wallet to complete the request"))}
                }
            },onError={result.completeExceptionally(IllegalStateException("Wallet request unavailable"))})
            return withTimeout(180000) { result.await() }
        } finally { pending=null;requestTopic=null;requestMethod=null;requestChain=null;requestId=null;early=null }
    }
    fun disconnect() {
        selection?.string("topic")?.takeIf { it.isNotBlank() }?.let { SignClient.disconnect(Sign.Params.Disconnect(it),onError={}) }
        selection=null;store.clear()
    }
}
