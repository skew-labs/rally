package com.rallydot.app

import kotlinx.coroutines.runBlocking
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Test
import org.junit.Assert.*

class OrderEngineTest {
    private val wallet="0x"+"1".repeat(40)
    private val target="0x"+"2".repeat(40)
    private val hash="0x"+"a".repeat(64)
    private fun tx()=JSONObject().put("from",wallet).put("to",target).put("chainId",143).put("value","0x0").put("data","0x1234")
    private fun plan()=JSONObject().put("id","test-plan").put("expires",System.currentTimeMillis()/1000+300)
    private fun entry(business: String="filled",state: String="finalized")=JSONObject().put("tx",hash).put("kind","execution").put("state",state).put("outcome",JSONObject().put("businessState",business))
    private class Store: PendingOrders {
        var value:JSONObject?=null
        override fun read()=value?.let { JSONObject(it.toString()) }
        override fun save(value:JSONObject) { this.value=JSONObject(value.toString()) }
        override fun clear() { value=null }
    }
    private inner class Fixture: OrderBackend {
        val calls=mutableListOf<String>()
        var posts: suspend (String,JSONObject)->JSONObject={p,_->when { p.endsWith("prepare")->JSONObject().put("transaction",tx());else->JSONObject().put("state","submitted") } }
        var reads: suspend (String)->JSONObject={JSONObject().put("entries",JSONArray().put(entry()))}
        override suspend fun post(path:String,body:JSONObject):JSONObject { calls+=path;return posts(path,body) }
        override suspend fun get(path:String):JSONObject { calls+=path;return reads(path) }
    }
    private inner class Signer(val store:Store):NativeSigner {
        var sends=0
        var send:suspend ()->String={hash}
        override suspend fun address()=wallet
        override suspend fun send(transaction:JSONObject):String { assertNotNull("Intent must be durable before signing",store.read());sends++;return send() }
    }
    @Test fun successfulOrderSendsOnceAndWaitsForBusinessResult()=runBlocking {
        val store=Store();val backend=Fixture();val signer=Signer(store);var result=OrderProgress()
        OrderEngine(backend,signer,store,{"owner" to wallet},{result=it},{ }).execute("execution",{plan()})
        assertEquals(1,signer.sends);assertEquals("Order filled",result.label);assertTrue(result.completed);assertNull(store.read())
    }
    @Test fun lostRecordResponseRecoversOnlyTheSameHash()=runBlocking {
        val store=Store();val backend=Fixture();val signer=Signer(store);var attempts=0;var result=OrderProgress()
        backend.posts={p,b->if(p.endsWith("prepare"))JSONObject().put("transaction",tx()) else { assertEquals(hash,b.string("tx"));if(++attempts==1)throw ApiFailure(503,"Unavailable");JSONObject().put("state","submitted") } }
        OrderEngine(backend,signer,store,{"owner" to wallet},{result=it},{ }).execute("execution",{plan()})
        assertEquals(1,signer.sends);assertEquals(2,attempts);assertTrue(result.completed)
    }
    @Test fun ambiguousWalletTimeoutBlocksResubmissionAndRecoveryDoesNotSign()=runBlocking {
        val store=Store();val backend=Fixture();val signer=Signer(store);signer.send={throw java.io.IOException("Connection lost")};var result=OrderProgress()
        val engine=OrderEngine(backend,signer,store,{"owner" to wallet},{result=it},{ })
        engine.execute("execution",{plan()});assertEquals("unknown",result.stage);assertNotNull(store.read());assertEquals(1,signer.sends)
        try { engine.execute("execution",{plan()});fail("Duplicate submission accepted") } catch(_:IllegalArgumentException) { }
        engine.recover(hash);assertTrue(result.completed);assertEquals(1,signer.sends)
    }
    @Test fun definitiveWalletCancellationClearsOnlyTheUnsignedIntent()=runBlocking {
        val store=Store();val backend=Fixture();val signer=Signer(store);signer.send={throw WalletRejected()};var result=OrderProgress()
        OrderEngine(backend,signer,store,{"owner" to wallet},{result=it},{ }).execute("execution",{plan()})
        assertEquals("failed",result.stage);assertNull(store.read())
    }
    @Test fun failedChainReadBeforeSendingDoesNotLeaveAnAmbiguousTrade()=runBlocking {
        val store=Store();val backend=Fixture();val signer=Signer(store);signer.send={throw WalletNotSent("Wrong network")};var result=OrderProgress()
        OrderEngine(backend,signer,store,{"owner" to wallet},{result=it},{ }).execute("execution",{plan()})
        assertEquals("failed",result.stage);assertNull(store.read())
    }
    @Test fun manuallyEnteredWrongHashCanBeCorrectedWithoutSigning()=runBlocking {
        val store=Store();val backend=Fixture();val signer=Signer(store);var result=OrderProgress()
        store.save(JSONObject().put("account","owner").put("wallet",wallet).put("kind","execution").put("id","test-plan"))
        backend.posts={_,body->if(body.string("tx")!=hash)throw ApiFailure(400,"Wrong transaction");JSONObject().put("state","submitted")}
        val engine=OrderEngine(backend,signer,store,{"owner" to wallet},{result=it},{ })
        engine.recover("0x"+"b".repeat(64));assertEquals("unknown",result.stage);assertNotNull(store.read())
        engine.recover(hash);assertTrue(result.completed);assertEquals(0,signer.sends);assertNull(store.read())
    }
    @Test fun expiredPreparationNeverReachesTheWallet()=runBlocking {
        val store=Store();val backend=Fixture();val signer=Signer(store)
        backend.posts={_,_->JSONObject().put("transaction",tx()).put("expires",System.currentTimeMillis()/1000-1)}
        OrderEngine(backend,signer,store,{"owner" to wallet},{},{ }).execute("execution",{plan()})
        assertEquals(0,signer.sends);assertNull(store.read())
    }
    @Test fun accountSwitchDuringPreparationDoesNotSign()=runBlocking {
        val store=Store();val backend=Fixture();val signer=Signer(store);var account="owner"
        backend.posts={_,_->account="other";JSONObject().put("transaction",tx())}
        OrderEngine(backend,signer,store,{account to wallet},{},{ }).execute("execution",{plan()})
        assertEquals(0,signer.sends);assertNull(store.read())
    }
    @Test fun wrongChainOrWalletCannotReachTheSigner() {
        for(value in listOf(tx().put("chainId",1),tx().put("from",target),tx().put("to","0x"+"0".repeat(40)),tx().put("data","0x1"))) {
            try { checkedNativeTransaction(value,wallet);fail("Invalid transaction accepted") } catch(_:IllegalArgumentException) { }
        }
    }
    @Test fun confirmedRequestAndUnfinalizedKeeperFillAreNotCompletion() {
        assertFalse(orderOutcome(entry("filled","confirmed")).completed)
        val e=entry();e.getJSONObject("outcome").put("settlementState","confirmed")
        assertFalse(orderOutcome(e).completed)
        e.getJSONObject("outcome").put("settlementState","finalized");assertTrue(orderOutcome(e).completed)
        assertFalse(orderOutcome(entry("keeper_pending")).completed)
        assertEquals("No fill",orderOutcome(entry("unfilled")).label)
    }
    @Test fun paidSubscriptionRequiresActiveEntitlement() {
        val invoice=JSONObject().put("kind","payment").put("state","paid").put("accessExpires",System.currentTimeMillis()/1000+86400)
        assertTrue(orderOutcome(invoice).completed)
        invoice.put("accessExpires",0);assertFalse(orderOutcome(invoice).completed)
    }
    @Test fun approvalNeedsCanonicalResultBeforeFreshExecution()=runBlocking {
        val store=Store();val backend=Fixture();val signer=Signer(store);var approved=false;var reads=0;var prepared=0
        backend.posts={p,_->when { p.endsWith("prepare")-> { prepared++;JSONObject().put(if(approved)"transaction" else "approval",tx()) };p.endsWith("approval/check")-> { if(++reads==1)throw ApiFailure(409,"Not indexed");approved=true;JSONObject().put("state","approved") };else->JSONObject().put("state","submitted") } }
        OrderEngine(backend,signer,store,{"owner" to wallet},{},{ }).execute("execution",{plan()})
        assertEquals(2,signer.sends);assertEquals(2,prepared);assertNull(store.read())
    }
    @Test fun recoveringApprovalNeverAutomaticallyBuys()=runBlocking {
        val store=Store();val backend=Fixture();val signer=Signer(store)
        store.save(JSONObject().put("account","owner").put("wallet",wallet).put("kind","execution").put("id","test-plan").put("approval",true).put("tx",hash))
        backend.posts={_,_->JSONObject().put("state","approved")}
        OrderEngine(backend,signer,store,{"owner" to wallet},{},{ }).recover()
        assertEquals(0,signer.sends);assertNull(store.read())
    }
    @Test fun perpetualRequestsCarrySizeProtectionAndDirection() {
        val raw=JSONObject().put("id",1).put("baseSymbol","BTC").put("venue","Perpl").put("open",true).put("execution","wallet_transactions")
        val args=executionArguments(NativeTrade(Asset.parse(raw,"perps"),"sell","0.001","81000",2))
        assertEquals("short",args.string("direction"));assertEquals("0.001",args.string("quantity"));assertEquals("81000",args.string("limit"));assertEquals(2,args.optInt("leverage"))
    }
    @Test fun changedSubscriptionTermsNeverReachTheWallet()=runBlocking {
        val displayed=JSONObject().put("id","feed-a").put("priceRaw","1000000").put("periodDays",30).put("version",2)
        val invoice=JSONObject().put("feed","feed-a").put("amountRaw","1000000").put("periodDays",30).put("version",2).put("currency","USDC")
        for(changed in listOf(JSONObject(invoice.toString()).put("amountRaw","2000000"),JSONObject(invoice.toString()).put("version",3),JSONObject(invoice.toString()).put("periodDays",7))) {
            val store=Store();val backend=Fixture();val signer=Signer(store)
            OrderEngine(backend,signer,store,{"owner" to wallet},{},{ }).execute("payment",{checkedNativeSubscription(changed,displayed)})
            assertEquals(0,signer.sends);assertTrue(backend.calls.isEmpty());assertNull(store.read())
        }
    }
}
