package com.rallydot.app
import org.junit.Test
import org.junit.Assert.*
import org.json.JSONObject
class PerpAmountTest {
    @Test fun positionAndMarginHaveSeparateMeaning() {
        val r=perpEstimate("0.3","quantity","60000",8,5)
        assertTrue(r.valid);assertEquals("18000",r.notional);assertEquals("3600",r.margin)
    }
    @Test fun dollarBudgetRoundsDownToVenueLotWithoutExceedingIt() {
        val r=perpEstimate("10","usd","60000",5,2)
        assertEquals("0.00016",r.quantity);assertEquals("9.6",r.notional);assertTrue(r.rounded)
        assertFalse(perpEstimate("0.001","usd","60000",5).valid)
    }
    @Test fun exactDecimalsAndInvalidValuesCannotBecomeLargerOrders() {
        assertEquals("0.3",perpEstimate("0.3000000000","quantity","60000",5).quantity)
        assertFalse(perpEstimate("0.000001","quantity","60000",5).valid)
        for(v in listOf("-1","1e6","Infinity","NaN","0","1,000"))assertFalse(perpEstimate(v,"quantity","60000",8).valid)
        assertFalse(perpEstimate("1","usd","0",8).valid)
        assertEquals("9007199254740993",perpEstimate("9007199254740993","quantity","1",0).notional)
    }
    @Test fun dollarModeSubmitsQuantityAndPreservesSideAndCollateralSemantics() {
        val a=Asset.parse(JSONObject().put("id","1").put("symbol","BTC").put("venue","Perpl").put("mark",60000).put("lotDecimals",5).put("open",true).put("execution","wallet_transactions"),"perps")
        val args=executionArguments(NativeTrade(a,"sell","10","60000",2,amountMode="usd"))
        assertEquals("0.00016",args.string("quantity"));assertEquals("short",args.string("direction"));assertFalse(args.has("amountMode"));assertFalse(args.has("amount"))
    }
}
