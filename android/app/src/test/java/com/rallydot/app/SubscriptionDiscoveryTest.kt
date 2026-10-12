package com.rallydot.app

import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class SubscriptionDiscoveryTest {
    @Test fun buybackRequiresARealLinkedRevenueVault() {
        val token=JSONObject().put("address","0xabc").put("buybackBps",2000)
        val feed=JSONObject().put("communityToken",token)
        assertNull(subscriptionAllocation(feed))
        token.put("vault","0xdef")
        assertEquals(2000,subscriptionAllocation(feed)!!.first)
        token.put("buybackBps",10001)
        assertNull(subscriptionAllocation(feed))
        token.put("buybackBps",1.5)
        assertNull(subscriptionAllocation(feed))
    }
    @Test fun subscriptionPriceUsesActualTermAndDoesNotInventMonthlyBilling() {
        assertEquals("2.5 USDC / 30d",subscriptionPrice(JSONObject().put("price","2.5").put("periodDays",30)))
        assertEquals("Free",subscriptionPrice(JSONObject().put("price","0")))
    }
}
