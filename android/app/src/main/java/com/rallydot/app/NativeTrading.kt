package com.rallydot.app

import org.json.JSONObject
import java.math.BigDecimal

data class NativeTrade(val asset: Asset,val side: String,val amount: String,val limit: String="",val leverage: Int=1,val quantity: String="")
fun checkedNativeSubscription(invoice: JSONObject,displayed: JSONObject): JSONObject {
    val expected=displayed.string("priceRaw").toBigIntegerOrNull() ?: BigDecimal(displayed.string("price")).movePointRight(6).toBigIntegerExact()
    require(expected.signum()>0 && invoice.string("feed")==displayed.string("id") && invoice.string("amountRaw").toBigIntegerOrNull()==expected && invoice.string("currency")=="USDC" && invoice.optInt("periodDays")==displayed.optInt("periodDays",30)) { "Subscription terms changed. Reopen the algorithm." }
    require(!displayed.has("version") || invoice.string("version")==displayed.string("version")) { "Algorithm changed. Reopen it before subscribing." }
    return invoice
}
fun executionArguments(t: NativeTrade): JSONObject {
    require(t.side in setOf("buy","sell") && validAmount(t.amount)) { "Enter a valid amount" }
    val a=t.asset
    if(a.raw.optBoolean("nadfun"))return JSONObject().put("venue","nadfun").put("kind",t.side).put("token",a.id).put("amount",t.amount).put("slippage",100)
    if(a.kind=="prediction")return JSONObject().put("venue","castora").put("kind","predict").put("pool",a.id).put("price",t.amount)
    require(a.kind=="perps" && a.executable) { "This market cannot accept orders" }
    val venue=a.venue.lowercase();require(venue in setOf("perpl","leverup","pingu","drake")) { "This venue is not supported" }
    val data=JSONObject().put("venue",venue).put("kind","order").put("market",a.id).put("direction",if(t.side=="buy")"long" else "short")
    if(venue in setOf("perpl","drake","pingu")) { require(validAmount(t.limit)) { "Enter a protection price" };data.put("limit",t.limit) }
    when(venue) {
        "perpl"->{ require(t.leverage in 1..5);data.put("quantity",t.amount).put("leverage",t.leverage).put("reduceOnly",a.raw.optBoolean("nativeReduceOnly")) }
        "drake"->data.put("quantity",t.amount).put("portfolioType","imp")
        "pingu"->{ require(t.leverage in 1..minOf(10,a.raw.optInt("maxLeverage",1)));data.put("amount",t.amount).put("leverage",t.leverage) }
        "leverup"->{ require(validAmount(t.quantity)) { "Enter the position quantity" };data.put("amount",t.amount).put("quantity",t.quantity).put("collateral","USDC").put("slippage","50") }
    }
    return data
}
suspend fun createNativeTrade(api: RallyApi,t: NativeTrade): JSONObject {
    if(t.asset.kind!="spot" || t.asset.raw.optBoolean("nadfun"))return api.post("/api/execution/plan",executionArguments(t))
    require(validAmount(t.amount) && t.side in setOf("buy","sell"))
    val args=JSONObject().put("input",if(t.side=="buy")"MON" else t.asset.id).put("output",if(t.side=="buy")t.asset.id else "MON").put("amount",t.amount).put("slippage",100)
    val routes=api.post("/api/routes",args)
    val choices=routes.objects("routes").filter { it.string("state")=="quoted" }
        .sortedByDescending { it.string("outputRaw").toBigIntegerOrNull() ?: java.math.BigInteger.ZERO }
        .distinctBy { it.string("provider") }
    require(choices.isNotEmpty()) { "No route for this amount" }
    var error: Exception?=null
    for(route in choices.take(4)) {
        try { return api.post("/api/quotes",JSONObject(args.toString()).put("provider",route.string("provider"))) }
        catch(e:ApiFailure) { if(e.status in setOf(401,403))throw e;error=e }
    }
    throw error ?: IllegalStateException("No executable route")
}
fun defaultProtection(asset: Asset,side: String): String {
    val mark=asset.price?.takeIf { it>0 && it.isFinite() } ?: return ""
    val precision=asset.raw.optInt("priceDecimals",6).coerceIn(0,10)
    return BigDecimal.valueOf(mark).multiply(if(side=="buy")BigDecimal("1.005") else BigDecimal("0.995"))
        .setScale(precision,if(side=="buy")java.math.RoundingMode.UP else java.math.RoundingMode.DOWN).stripTrailingZeros().toPlainString()
}

/** The device verifies the concrete recipient and amount before the SDK sees a send. */
fun checkedNativeTransfer(plan: JSONObject,holding: JSONObject,recipient: String,amount: String): JSONObject {
    val asset=holding.string("asset");val native=asset=="MON"
    val token=holding.optJSONObject("token") ?: JSONObject()
    val decimals=if(native)18 else token.optInt("decimals",-1)
    require(decimals in 0..36) { "Token precision unavailable" }
    val raw=java.math.BigDecimal(amount).movePointRight(decimals).toBigIntegerExact()
    require(raw>java.math.BigInteger.ZERO && raw.bitLength()<=256) { "Invalid amount" }
    val s=plan.getJSONObject("summary");val tx=plan.getJSONObject("transaction")
    require(s.string("action")=="send") { "Transfer action changed" }
    require(s.string("recipient").equals(recipient,true) && s.string("token").equals(asset,true) && s.string("amountRaw")==raw.toString()) { "Transfer changed. Try again." }
    require(tx.string("to").equals(if(native)recipient else token.string("address",asset),true)) { "Recipient changed" }
    require(tx.string("value","0x0").removePrefix("0x").toBigInteger(16)==if(native)raw else java.math.BigInteger.ZERO) { "Transfer value changed" }
    val data=if(native)"0x" else "0xa9059cbb"+recipient.lowercase().removePrefix("0x").padStart(64,'0')+raw.toString(16).padStart(64,'0')
    require(tx.string("data").equals(data,true) && (!plan.has("approval") || plan.isNull("approval"))) { "Transfer data changed" }
    return plan
}

/** Gas may change during preparation; the verified send's destination and amount may not. */
fun checkedPreparedTransfer(plan: JSONObject,prepared: JSONObject) {
    if(plan.optJSONObject("summary")?.string("action")!="send")return
    require(prepared.optJSONObject("approval")==null) { "A send cannot request a token allowance" }
    val expected=plan.getJSONObject("transaction");val actual=prepared.getJSONObject("transaction")
    require(listOf("to","data").all { actual.string(it).equals(expected.string(it),true) }) { "Transfer changed during preparation" }
    fun value(tx: JSONObject)=tx.string("value","0x0").removePrefix("0x").toBigInteger(16)
    require(value(expected)==value(actual)) { "Transfer amount changed during preparation" }
}
