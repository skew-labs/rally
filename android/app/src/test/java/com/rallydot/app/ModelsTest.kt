package com.rallydot.app
import org.json.JSONObject
import org.junit.Test
import org.junit.Assert.*

class ModelsTest {
    @Test fun missingPriceRemainsMissing() { val a=Asset.parse(JSONObject("{\"id\":\"x\",\"symbol\":\"X\"}"));assertNull(a.price);assertEquals("—",money(a.price));assertTrue(a.freshness) }
    @Test fun invalidPriceIsNotAZeroQuote() { listOf("null","\"NaN\"","\"Infinity\"","\"bad\"").forEach { assertNull(Asset.parse(JSONObject("{\"price\":$it}")).price) } }
    @Test fun numericStringsKeepPrecision() { val a=Asset.parse(JSONObject("{\"price\":\"0.000000001\",\"marketCap\":\"3000000\"}"));assertEquals(1e-9,a.price!!,1e-18);assertEquals(3000000.0,a.cap!!,0.0) }
    @Test fun venueIdsAreDistinct() { val a=Asset.parse(JSONObject("{\"id\":1,\"venue\":\"Perpl\"}"),"perps");val b=Asset.parse(JSONObject("{\"id\":1,\"venue\":\"Drake\"}"),"perps");assertNotEquals(a.key,b.key) }
    @Test fun closedPredictionsCannotTrade() { assertFalse(Asset.parse(JSONObject("{\"state\":\"awaiting_settlement\"}"),"prediction").executable);assertFalse(Asset.parse(JSONObject("{}"),"prediction").executable);assertTrue(Asset.parse(JSONObject("{\"state\":\"open\"}"),"prediction").executable) }
    @Test fun referencePerpCannotSubmit() { assertFalse(Asset.parse(JSONObject("{\"open\":true,\"execution\":\"reference_only\"}"),"perps").executable);assertTrue(Asset.parse(JSONObject("{\"open\":true,\"execution\":\"wallet_transactions\"}"),"perps").executable) }
    @Test fun lockedTokensCannotSubmit() { assertFalse(Asset.parse(JSONObject("{\"locked\":true}")).executable) }
    @Test fun freshAndExpiredReferencesDiffer() { val j=JSONObject().put("fetchedAt",System.currentTimeMillis()/1000);assertFalse(Asset.parse(j).freshness);j.put("fetchedAt",1);assertTrue(Asset.parse(j).freshness) }
    @Test fun invalidAmountsAreRejectedBeforeRequest() { listOf("","0","-1","NaN","Infinity","1e4","01","1,000","1.","0.0000000000000000001").forEach { assertFalse(it,validAmount(it)) };listOf("1","0.1","0.000000000000000001","10.50").forEach { assertTrue(it,validAmount(it)) } }
    @Test fun imageUrlsRejectExecutableOrCredentialSchemes() { listOf("javascript:alert(1)","data:image/png,x","http://x/image","https://user:pass@x/img").forEach { assertNull(safeImage(it)) };assertEquals("https://rallydot.com/assets/MON.png",safeImage("/assets/MON.png")) }
    @Test fun chartsAreSortedDeduplicatedAndClean() { val j=JSONObject("{\"points\":[{\"time\":2,\"value\":3},{\"time\":1,\"value\":2},{\"time\":2,\"value\":4},{\"time\":3,\"value\":null},{\"time\":4,\"value\":-1}]}");val p=chartPoints(j);assertEquals(2,p.size);assertEquals(1,p[0].time);assertEquals(3f,p[1].value,0f) }
    @Test fun codexGetsOfficialArtwork() { assertEquals("https://rallydot.com/assets/agent-openai.svg",Person.parse(JSONObject("{\"name\":\"Codex\",\"avatar\":\"\"}")).image) }
    @Test fun nativeChartRejectsDifferentToken() { try { nadChart(JSONObject().put("token","other"),"expected",1);fail("mismatched chart accepted") } catch (_: IllegalArgumentException) {} }
    @Test fun nativeChartKeepsOnlySelectedWindow() { val now=System.currentTimeMillis()/1000;val j=JSONObject().put("token","0x1").put("candles",org.json.JSONArray().put(JSONObject().put("time",now-90000).put("close",1)).put(JSONObject().put("time",now-10).put("close",2)));val points=chartPoints(nadChart(j,"0x1",1));assertEquals(1,points.size);assertEquals(2f,points[0].value,0f) }
    @Test fun backgroundQuotesPreserveVisibleTokenIdentity() {
        fun row(id: String,price: Double)=JSONObject().put("id",id).put("price",price)
        val previous=listOf(row("a",1.0),row("b",2.0),row("c",3.0))
        val next=mergePageItems(previous,listOf(row("b",4.0),row("a",5.0),row("d",6.0)),true)
        assertEquals(listOf("a","b","c","d"),next.map { it.string("id") })
        assertEquals(5.0,next[0].number("price")!!,0.0)
        assertEquals(4.0,next[1].number("price")!!,0.0)
    }
    @Test fun manualRefreshUsesNewRankingWhilePaginationDoesNotDuplicate() {
        val a=JSONObject().put("id","a");val b=JSONObject().put("id","b")
        assertEquals(listOf("b","a"),mergePageItems(listOf(a,b),listOf(b,a),false).map { it.string("id") })
        assertEquals(2,mergePageItems(listOf(a),listOf(a,b),true).size)
    }
    @Test fun chartScrubbingUsesActualObservationTimes() {
        val points=listOf(ChartPoint(1,1f),ChartPoint(2,2f),ChartPoint(100,3f))
        assertEquals(2,nearestChartPoint(points,.4f).time)
        assertEquals(100,nearestChartPoint(points,.9f).time)
        assertEquals(1,nearestChartPoint(points,-1f).time)
        assertEquals(100,nearestChartPoint(points,2f).time)
    }

    @Test fun closedDraftRetainsTextMediaAndRequestIdentity() {
        val cache=DraftCache();val key=DraftIdentity("owner","group")
        val draft=cache.get(key).copy(text="Draft",file="content://picked/file",media="upload-id")
        cache.save(key,draft)
        assertEquals(draft,cache.get(key))
        assertEquals(draft.requestKey,cache.get(key).requestKey)
    }
    @Test fun accountSwitchCannotRecoverOrResavePreviousOwnersDraft() {
        val cache=DraftCache();val first=DraftIdentity("a","group");val second=DraftIdentity("b","group")
        cache.get(first);cache.save(first,PostDraft(text="private"))
        assertEquals("",cache.get(second).text)
        cache.save(first,PostDraft(text="late disposal"))
        assertEquals("",cache.get(second).text)
        assertEquals("",cache.get(first).text)
    }
    @Test fun draftsAreBoundedAndPublishedDraftCanBeRemoved() {
        val cache=DraftCache(2);val a=DraftIdentity("a","one");val b=DraftIdentity("a","two");val c=DraftIdentity("a","three")
        cache.get(a);cache.save(a,PostDraft(text="one"));cache.save(b,PostDraft(text="two"));cache.save(c,PostDraft(text="three"))
        assertEquals("",cache.get(a).text);assertEquals("two",cache.get(b).text)
        cache.remove(c);assertEquals("",cache.get(c).text)
    }

}
