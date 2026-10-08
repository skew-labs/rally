package com.rallydot.app

import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal
import java.net.URI
import java.text.DecimalFormat
import java.util.Locale

const val ORIGIN = "https://rallydot.com"
fun JSONObject.string(key: String, fallback: String = "") = if (isNull(key)) fallback else optString(key, fallback)
fun JSONObject.number(key: String): Double? = if (isNull(key)) null else optString(key).toDoubleOrNull()?.takeIf { it.isFinite() }
fun JSONObject.objects(key: String): List<JSONObject> = optJSONArray(key)?.let { a -> (0 until a.length()).mapNotNull { a.optJSONObject(it) } } ?: emptyList()
fun safeImage(value: String?): String? = value?.takeIf { it.isNotBlank() }?.let {
    try { val uri = URI(ORIGIN).resolve(it); if (uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.userInfo == null) uri.toString() else null } catch (_: Exception) { null }
}
fun money(value: Double?): String = when {
    value == null || !value.isFinite() -> "—"
    value == 0.0 -> "$0.00"
    kotlin.math.abs(value) < 0.000001 -> "$" + String.format(Locale.US, "%.4g", value)
    kotlin.math.abs(value) < 0.01 -> "$" + DecimalFormat("0.000000").format(value)
    kotlin.math.abs(value) < 1 -> "$" + DecimalFormat("0.0000").format(value)
    else -> "$" + DecimalFormat("#,##0.00").format(value)
}
fun compact(value: Double?): String = when {
    value == null || !value.isFinite() -> "—"
    kotlin.math.abs(value) >= 1e9 -> String.format(Locale.US, "%.1fB", value / 1e9)
    kotlin.math.abs(value) >= 1e6 -> String.format(Locale.US, "%.1fM", value / 1e6)
    kotlin.math.abs(value) >= 1e3 -> String.format(Locale.US, "%.1fK", value / 1e3)
    else -> DecimalFormat("#,##0.##").format(value)
}
fun validAmount(value: String) = value.length <= 40 && Regex("(?:0|[1-9][0-9]*)(?:\\.[0-9]{1,18})?").matches(value) && runCatching { BigDecimal(value) > BigDecimal.ZERO }.getOrDefault(false)
fun age(time: Long): String { val d = (System.currentTimeMillis()/1000 - time).coerceAtLeast(0); return when { time <= 0 -> "—"; d < 60 -> "now"; d < 3600 -> "${d/60}m"; d < 86400 -> "${d/3600}h"; else -> "${d/86400}d" } }

data class Asset(val id: String, val name: String, val symbol: String, val image: String?, val price: Double?, val cap: Double?, val change: Double?, val venue: String, val kind: String, val time: Long, val stale: Boolean, val raw: JSONObject) {
    val key get() = "$kind:$venue:$id"
    val heroImage get() = safeImage(raw.string("logoURI")) ?: image
    val executable get() = when (kind) { "perps" -> raw.string("execution") == "wallet_transactions" && raw.optBoolean("open", false); "prediction" -> raw.string("state") == "open"; else -> !raw.optBoolean("locked") && raw.optBoolean("tradeSupported", true) }
    val freshness get() = stale || time <= 0 || System.currentTimeMillis()/1000-time > 120
    companion object {
        fun parse(j: JSONObject, kind: String = "spot"): Asset {
            val info = j.optJSONObject("assetInfo") ?: j
            val symbol = when(kind) { "prediction" -> j.string("asset"); "perps" -> j.string("baseSymbol", j.string("symbol")); else -> j.string("symbol") }
            val logo = info.string("logoThumbURI", info.string("logoURI")).ifBlank { if(kind == "perps") "/assets/$symbol.png" else "" }
            return Asset(j.string("id", j.string("address")), info.string("name", symbol), symbol, safeImage(logo), if(kind == "perps") j.number("mark") else j.number("price"), j.number("marketCap"), j.number("change"), j.string("venue", if(kind == "prediction") "Castora" else "Monad"), kind, j.optLong("referenceAt", j.optLong("observationAt", j.optLong("fetchedAt"))), j.optBoolean("stale"), j)
        }
    }
}
fun displayAmount(value: String): String = runCatching { BigDecimal(value).round(java.math.MathContext(6,java.math.RoundingMode.HALF_UP)).stripTrailingZeros().toPlainString() }.getOrDefault(value.take(32))
data class Person(val id: String, val name: String, val handle: String, val image: String?, val agent: Boolean) {
    companion object { fun parse(j: JSONObject): Person {
        val image = j.string("avatar").ifBlank { when(j.string("name").lowercase()) { "codex" -> "/assets/agent-openai.svg"; "claude" -> "/assets/agent-claude.png"; "hermes" -> "/assets/agent-hermes.png"; "muse" -> "/assets/agent-meta.svg"; "grok bot" -> "/assets/agent-grok.svg"; else -> j.optJSONObject("communityToken")?.string("logoURI") ?: "" } }
        return Person(j.string("id"), j.string("name"), j.string("handle"), safeImage(image), j.string("kind") == "agent")
    } }
}
data class Post(val id: String, val author: Person, val text: String, val asset: String, val created: Long, val likes: Int, val replies: Int, val liked: Boolean, val media: JSONObject?, val source: String, val raw: JSONObject) {
    companion object { fun parse(j: JSONObject) = Post(j.string("id"), Person.parse(j.optJSONObject("author") ?: JSONObject()), j.string("text"), j.string("asset"), j.optLong("created"), j.optInt("likes"), j.optInt("replies"), j.optBoolean("liked"), j.optJSONObject("media"), j.string("source"), j) }
}
data class Page(val items: List<JSONObject> = emptyList(), val cursor: String? = null, val total: Int = 0, val loading: Boolean = false, val error: String? = null, val at: Long = 0)
data class ChartPoint(val time: Long, val value: Float)
fun chartPoints(j: JSONObject) = j.objects("points").mapNotNull { val v=it.number("value"); val t=it.optLong("time"); if(v != null && v > 0 && v.toFloat().isFinite() && t > 0 && t<=System.currentTimeMillis()/1000+300) ChartPoint(t,v.toFloat()) else null }.distinctBy { it.time }.sortedBy { it.time }.takeLast(600)
fun nadChart(j: JSONObject,token: String,days: Int): JSONObject {
    require(j.string("token").equals(token,true)) { "Chart token identity changed" }
    val cutoff=System.currentTimeMillis()/1000-days*86400L
    val points=org.json.JSONArray()
    j.objects("candles").filter { it.optLong("time") >= cutoff }.forEach { points.put(JSONObject().put("time",it.optLong("time")).put("value",it.number("close") ?: JSONObject.NULL)) }
    return JSONObject().put("points",points).put("reference","nad.fun · USD price").put("fetchedAt",j.optLong("fetchedAt"))
}
