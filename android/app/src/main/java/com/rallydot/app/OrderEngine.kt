package com.rallydot.app

import org.json.JSONObject
import kotlinx.coroutines.delay
import kotlinx.coroutines.CancellationException

interface OrderBackend {
    suspend fun get(path: String): JSONObject
    suspend fun post(path: String,body: JSONObject): JSONObject
}
interface NativeSigner {
    suspend fun address(): String
    suspend fun send(transaction: JSONObject): String
}
interface PendingOrders {
    fun read(): JSONObject?
    fun save(value: JSONObject)
    fun clear()
}
class WalletRejected: Exception("Wallet request canceled")
class WalletNotSent(message: String): Exception(message)
data class OrderProgress(val stage: String="idle",val label: String="",val hash: String?=null,val error: String?=null,val completed: Boolean=false) {
    val working get()=stage in setOf("preparing","approving","signing","confirming")
    val blocksOrder get()=working || stage in setOf("unknown","pending")
}
fun checkedNativeTransaction(input: JSONObject,wallet: String): JSONObject {
    require(Regex("0x[0-9a-fA-F]{40}").matches(wallet)) { "Connect a wallet first" }
    require(input.string("from").equals(wallet,true)) { "Wallet changed. Reconnect it." }
    require(Regex("0x[0-9a-fA-F]{40}").matches(input.string("to"))) { "Invalid transaction recipient" }
    require(input.string("to")!="0x"+"0".repeat(40)) { "Invalid transaction recipient" }
    val chain=input.opt("chainId")?.toString() ?: "143"
    require(chain=="143" || chain.equals("0x8f",true)) { "Use Monad mainnet" }
    val data=input.string("data","0x")
    require(data.length<=130000 && Regex("0x(?:[0-9a-fA-F]{2})*").matches(data)) { "Invalid transaction data" }
    val tx=JSONObject().put("from",wallet).put("to",input.string("to")).put("data",data).put("chainId","0x8f")
    for(key in listOf("value","gas","gasPrice","maxFeePerGas","maxPriorityFeePerGas","nonce")) {
        val value=input.string(key,if(key=="value")"0x0" else "")
        if(value.isNotEmpty()) {
            require(Regex("0x[0-9a-fA-F]{1,64}").matches(value)) { "Invalid transaction $key" }
            if(key=="gas")require(value.removePrefix("0x").toBigInteger(16) in java.math.BigInteger.ONE..java.math.BigInteger.valueOf(30000000)) { "Invalid gas limit" }
            tx.put(key,value)
        }
    }
    return tx
}
fun orderOutcome(entry: JSONObject): OrderProgress {
    val chain=entry.string("state");val hash=entry.string("tx").takeIf { it.isNotEmpty() }
    val raw=entry.opt("outcome")
    val outcome=when(raw) { is JSONObject->raw;is String->runCatching { JSONObject(raw) }.getOrNull();else->null }
    val business=outcome?.string("businessState").orEmpty()
    if(chain=="failed" || business=="reverted")return OrderProgress("failed","Transaction failed",hash,completed=true)
    if(chain !in setOf("confirmed","finalized","settled","paid"))return OrderProgress("pending","Submitted",hash)
    val label=when(business) {
        "filled"->"Order filled";"partial_fill"->"Partially filled";"unfilled"->"No fill"
        "swap_delivered"->"Swap complete";"prediction_entered"->"Prediction entered";"winnings_claimed"->"Winnings received"
        "collateral_deposit"->"Deposit complete";"collateral_withdraw"->"Withdrawal complete"
        "token_created"->"Token launched";"position_opened"->"Position opened";"position_closed","closed"->"Position closed"
        "credited"->"Deposit complete";"withdrawn"->"Withdrawal complete";"portfolio_created"->"Trading account ready"
        "refunded"->"Order refunded";"cancelled"->"Order cancelled"
        else->if(entry.string("kind")=="payment" && chain=="paid" && entry.optLong("accessExpires")>System.currentTimeMillis()/1000)"Subscription active" else if(entry.string("kind")=="spot" && chain=="finalized")"Swap confirmed" else "Waiting for venue result"
    }
    val finished=label!="Waiting for venue result" && chain in setOf("finalized","paid","settled") && (outcome?.string("settlementState").orEmpty() in setOf("","finalized"))
    return OrderProgress(if(finished)"complete" else "pending",if(!finished && label!="Waiting for venue result")"$label · finalizing" else label,hash,completed=finished)
}

/** Records a hash before any network read. Recovery only checks that hash; it never sends again. */
class OrderEngine(private val backend: OrderBackend,private val signer: NativeSigner,private val pending: PendingOrders,
    private val identity: ()->Pair<String,String>,private val update: (OrderProgress)->Unit,private val pause: suspend ()->Unit={delay(1600)}) {
    private fun guard(account: String,wallet: String) { require(identity()==(account to wallet)) { "Account changed. Restore the original wallet." } }
    suspend fun execute(kind: String,create: suspend ()->JSONObject) {
        require(kind in setOf("spot","execution","payment"))
        require(pending.read()==null) { "Check your pending transaction first" }
        val (account,wallet)=identity();require(account.isNotEmpty() && wallet.isNotEmpty()) { "Connect your wallet" }
        require(signer.address().equals(wallet,true)) { "Connect the wallet linked to this account" }
        var requesting=false
        try {
            update(OrderProgress("preparing","Getting your price…"));var plan=create();var approvals=0
            repeat(3) {
                guard(account,wallet)
                if(plan.optLong("expires")<=System.currentTimeMillis()/1000)plan=create()
                val refKey=if(kind=="spot")"quote" else if(kind=="payment")"invoice" else "plan"
                val ref=JSONObject().put(refKey,plan.string("id"))
                val prep=backend.post(if(kind=="spot")"/api/orders/prepare" else if(kind=="payment")"/api/payments/prepare" else "/api/execution/prepare",ref)
                guard(account,wallet)
                require(plan.optLong("expires")>System.currentTimeMillis()/1000 && (!prep.has("expires") || prep.optLong("expires")>System.currentTimeMillis()/1000)) { "Price expired. Try again." }
                val approval=prep.optJSONObject("approval")!=null
                require(!approval || approvals==0) { "Token approval has not completed" }
                val tx=checkedNativeTransaction(prep.optJSONObject("approval") ?: prep.getJSONObject("transaction"),wallet)
                require(signer.address().equals(wallet,true)) { "Wallet changed" };guard(account,wallet)
                val saved=JSONObject().put("account",account).put("wallet",wallet).put("kind",kind).put("id",plan.string("id")).put("approval",approval).put("created",System.currentTimeMillis()/1000)
                pending.save(saved);requesting=true
                update(OrderProgress(if(approval)"approving" else "signing",if(approval)"Approving token amount…" else "Signing…"))
                val hash=signer.send(tx)
                require(Regex("0x[0-9a-fA-F]{64}").matches(hash)) { "Check your transaction in the wallet" }
                saved.put("tx",hash);pending.save(saved);requesting=false
                update(OrderProgress("confirming",if(approval)"Confirming approval…" else "Confirming…",hash))
                if(approval) {
                    val path=if(kind=="spot")"/api/orders/approval/check" else if(kind=="payment")"/api/payments/approval/check" else "/api/execution/approval/check"
                    var approved=false
                    for(attempt in 0 until 30) {
                        guard(account,wallet)
                        val result=try { backend.post(path,JSONObject(ref.toString()).put("tx",hash)) } catch(e:ApiFailure) { if(e.status !in setOf(409,503))throw e;pause();continue }
                        if(result.string("state") in setOf("approved","confirmed")) { approved=true;break }
                        if(result.string("state")=="failed") { pending.clear();update(OrderProgress("failed","Approval failed",hash,completed=true));return }
                        pause()
                    }
                    if(!approved) { update(OrderProgress("pending","Approval pending",hash));return }
                    pending.clear();approvals++;plan=create()
                } else { reconcile(saved);return }
            }
        } catch(e:Exception) {
            if((e is WalletRejected || e is WalletNotSent) && requesting) { pending.clear();requesting=false }
            val item=pending.read()
            update(OrderProgress(if(requesting)"unknown" else if(item!=null)"pending" else "failed",if(requesting)"Check your wallet" else if(item!=null)"Transaction pending" else "Could not continue",item?.string("tx")?.takeIf { it.isNotBlank() },e.message))
            if(e is CancellationException)throw e
        }
    }
    suspend fun recover(hash: String?=null) {
        val saved=pending.read() ?: return
        if(saved.string("tx").isEmpty() || (saved.optBoolean("manualHash") && hash!=null)) {
            require(hash!=null && Regex("0x[0-9a-fA-F]{64}").matches(hash)) { "Paste the transaction hash from your wallet" }
            saved.put("tx",hash).put("manualHash",true);pending.save(saved)
        }
        try { reconcile(saved) } catch(e:Exception) { update(OrderProgress(if(saved.optBoolean("manualHash"))"unknown" else "pending","Check transaction again",saved.string("tx"),e.message));if(e is CancellationException)throw e }
    }
    private suspend fun reconcile(saved: JSONObject) {
        val account=saved.string("account");val wallet=saved.string("wallet");guard(account,wallet)
        val kind=saved.string("kind");val hash=saved.string("tx");val key=if(kind=="spot")"quote" else if(kind=="payment")"invoice" else "plan"
        val ref=JSONObject().put(key,saved.string("id")).put("tx",hash)
        val approval=saved.optBoolean("approval")
        val path=if(approval)if(kind=="spot")"/api/orders/approval/check" else if(kind=="payment")"/api/payments/approval/check" else "/api/execution/approval/check"
            else if(kind=="spot")"/api/orders" else if(kind=="payment")"/api/payments/record" else "/api/execution/record"
        var registered=false
        for(attempt in 0 until 30) {
            guard(account,wallet)
            if(!registered || approval) {
                try {
                    val record=backend.post(path,ref);registered=true
                    if(saved.optBoolean("manualHash")) { saved.remove("manualHash");pending.save(saved) }
                    if(approval) {
                        if(record.string("state") in setOf("approved","confirmed","failed")) { pending.clear();update(OrderProgress(if(record.string("state")=="failed")"failed" else "complete",if(record.string("state")=="failed")"Approval failed" else "Token approved. Tap Buy or Sell to continue.",hash,completed=true));return }
                    }
                } catch(e:ApiFailure) { if(e.status!=409 && e.status!=503)throw e }
            }
            if(registered && !approval) {
                val entry=if(kind=="payment")backend.get("/api/payment?id="+saved.string("id")).put("kind","payment")
                    else backend.get("/api/activity").objects("entries").firstOrNull { it.string("tx").equals(hash,true) }
                if(entry!=null) { val progress=orderOutcome(entry);update(progress);if(progress.completed) { pending.clear();return } }
            }
            pause()
        }
        update(OrderProgress(if(!registered && saved.optBoolean("manualHash"))"unknown" else "pending",if(approval)"Approval pending" else "Waiting for venue result",hash))
    }
}
