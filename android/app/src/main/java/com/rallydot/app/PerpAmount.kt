package com.rallydot.app

import java.math.BigDecimal
import java.math.RoundingMode
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.unit.dp

data class PerpEstimate(val quantity: String="",val notional: String="",val margin: String="",val rounded: Boolean=false,val error: String?=null) {
    val valid get()=error==null && quantity.isNotBlank()
}
private fun orderDecimal(value: String): BigDecimal {
    require(value.length<=96 && Regex("(?:\\d+\\.?\\d*|\\.\\d+)").matches(value) && value.substringAfter('.',"").length<=36) { "Enter an amount" }
    return BigDecimal(value).also { require(it.signum()>0) { "Enter an amount" } }
}
fun perpEstimate(value: String,mode: String,price: String,precision: Int,leverage: Int=1): PerpEstimate = try {
    require(mode in setOf("quantity","usd") && precision in 0..18 && leverage in 1..10000) { "Invalid order settings" }
    val input=orderDecimal(value);val mark=orderDecimal(price)
    val quantity=if(mode=="usd")input.divide(mark,precision,RoundingMode.DOWN) else input.stripTrailingZeros()
    require(quantity.signum()>0) { "Amount is below the minimum quantity" }
    require(quantity.scale()<=precision) { "Use up to $precision decimals" }
    val notional=quantity.multiply(mark)
    PerpEstimate(quantity.stripTrailingZeros().toPlainString(),notional.stripTrailingZeros().toPlainString(),notional.divide(BigDecimal(leverage),6,RoundingMode.UP).stripTrailingZeros().toPlainString(),mode=="usd" && notional.compareTo(input)!=0)
} catch(e:Exception) { PerpEstimate(error=e.message ?: "Enter an amount") }
fun perpDollars(value: String): String = runCatching {
    val amount=BigDecimal(value);val precision=if(amount.signum()>0 && amount<BigDecimal("0.01"))6 else 2
    "$"+java.text.DecimalFormat(if(precision==6)"#,##0.00####" else "#,##0.00",java.text.DecimalFormatSymbols(java.util.Locale.US)).format(amount)
}.getOrDefault("—")

@Composable fun PerpPositionInput(value: String,mode: String,symbol: String,estimate: PerpEstimate,accent: Color,
    enabled: Boolean,onValue: (String)->Unit,onMode: (String)->Unit,done: ()->Unit,margin: Boolean=true,collateral: String="AUSD",showEquivalent: Boolean=true) {
    Column(Modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
        TradeAmount(value,onValue,"Position size",if(mode=="usd")"USD" else symbol,accent,done,enabled) {
            Segmented(listOf(symbol,"USD"),if(mode=="usd")"USD" else symbol,{if(enabled)onMode(if(it=="USD")"usd" else "quantity")},Modifier.width(148.dp))
        }
        if(showEquivalent)Text(perpEquivalent(value,mode,symbol,estimate),style=MaterialTheme.typography.bodySmall,color=if(value.isNotBlank() && !estimate.valid)MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            listOf("10","25","50").forEach { preset ->
                TextButton(onClick={onMode("usd");onValue(preset);done()},enabled=enabled,modifier=Modifier.weight(1f).heightIn(min=48.dp),shape=androidx.compose.foundation.shape.RoundedCornerShape(100.dp),colors=ButtonDefaults.textButtonColors(containerColor=MaterialTheme.colorScheme.surfaceContainer,contentColor=accent)) { Text("$$preset") }
            }
        }
        Fact("Position value",if(estimate.valid)perpDollars(estimate.notional) else "—")
        if(margin)Fact("Est. margin · $collateral",if(estimate.valid)"${estimate.margin} $collateral" else "—")
        Text(if(margin)"Margin excludes fees." else "The venue checks available margin.",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
fun perpEquivalent(value: String,mode: String,symbol: String,estimate: PerpEstimate): String =
    if(estimate.valid)(if(mode=="quantity")"≈ ${perpDollars(estimate.notional)}" else "≈ ${estimate.quantity} $symbol")+(if(estimate.rounded)" · Rounded down" else "") else if(value.isBlank())"Enter an amount" else estimate.error.orEmpty()
