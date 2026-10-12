package com.rallydot.app
import org.json.JSONObject
import org.junit.Test
import org.junit.Assert.*

class ModelsTest {
    @Test fun providerTokenChartsUseExactContractsAndExcludeUnmigratedCurves() {
        val address="0x"+"a".repeat(40)
        val token=Asset.parse(JSONObject().put("id",address).put("chainId",143).put("nadfun",true).put("graduated",true))
        assertEquals(address,providerTarget(token)?.token)
        assertNull(providerTarget(token.copy(raw=JSONObject(token.raw.toString()).put("graduated",false))))
        assertNull(providerTarget(token.copy(raw=JSONObject(token.raw.toString()).put("chainId",1))))
        assertNull(providerTarget(Asset.parse(JSONObject().put("id","unknown").put("symbol","BTC"))))
    }
    @Test fun providerChartsCannotNavigateIntoWalletsOrRallyAuthentication() {
        assertTrue(allowedProviderNavigation("https://www.geckoterminal.com/monad/tokens/0x1"))
        listOf("javascript:alert(1)","http://www.geckoterminal.com/","https://rallydot.com/","https://www.geckoterminal.com.evil.test/","https://user@www.geckoterminal.com/","https://www.geckoterminal.com:444/","metamask://connect","file:///private").forEach { assertFalse(it,allowedProviderNavigation(it)) }
    }
    @Test fun firstAnonymousBootstrapDoesNotCancelAlreadyLoadingPublicMarkets() {
        assertFalse(accountIdentityChanged(null,JSONObject().put("wallet","")))
        assertFalse(accountIdentityChanged(JSONObject(),JSONObject().put("wallet","")))
    }
    @Test fun realAccountOrWalletChangesStillInvalidatePreviousAccountData() {
        val previous=JSONObject().put("me",JSONObject().put("id","a")).put("wallet","0xABC")
        assertFalse(accountIdentityChanged(previous,JSONObject(previous.toString()).put("wallet","0xabc")))
        assertTrue(accountIdentityChanged(previous,JSONObject(previous.toString()).put("me",JSONObject().put("id","b"))))
        assertTrue(accountIdentityChanged(previous,JSONObject(previous.toString()).put("wallet","0xdef")))
        assertTrue(accountIdentityChanged(previous,JSONObject().put("wallet","")))
    }
    @Test fun holderObservationsKeepIdentityAndRejectExpiredOrCrossTokenSnapshots() {
        val now=System.currentTimeMillis()/1000;val address="0x"+"1".repeat(40)
        val data=JSONObject().put("asset",address).put("indexed",true).put("fetchedAt",now).put("holders",org.json.JSONArray().put(JSONObject().put("address",address).put("amount","890567000.123456789")))
        assertSame(data,checkedHolders(data,address,now))
        listOf(JSONObject(data.toString()).put("asset","0x"+"2".repeat(40)),JSONObject(data.toString()).put("fetchedAt",now-901),JSONObject(data.toString()).put("fetchedAt",now+1)).forEach { assertTrue(runCatching { checkedHolders(it,address,now) }.isFailure) }
    }
    @Test fun holderAmountsStayCompactWithoutLosingTheExactModelAmount() {
        assertEquals("890.6M",holderAmount("890567000.123456789"))
        assertTrue(holderAmount("0.00000000123456").length<14)
        assertEquals("—",holderAmount("NaN"));assertEquals("—",holderAmount("-1"))
    }
    @Test fun quoteOnlyChartPreservesItsActualIdentityPriceAndTimestamp() {
        val now=System.currentTimeMillis()/1000
        val asset=Asset.parse(JSONObject().put("id","0x1").put("price",.002536).put("referenceAt",now-10).put("priceSource","Fixture quote"))
        val chart=referenceChart(asset,now)!!
        assertTrue(chart.optBoolean("quoteOnly"));assertEquals(asset.id,chart.string("asset"));assertEquals("Fixture quote",chart.string("reference"))
        val points=chartPoints(chart);assertEquals(1,points.size);assertEquals(asset.time,points.single().time);assertEquals(asset.price!!.toFloat(),points.single().value,0f)
    }
    @Test fun staleMissingInvalidAndFutureQuotesCannotBecomeChartHistory() {
        val now=System.currentTimeMillis()/1000
        val asset=Asset.parse(JSONObject().put("id","0x1").put("price",1).put("referenceAt",now))
        listOf(asset.copy(price=null),asset.copy(price=0.0),asset.copy(price=Double.NaN),asset.copy(stale=true),asset.copy(time=0),asset.copy(time=now-121),asset.copy(time=now+1)).forEach { assertNull(referenceChart(it,now)) }
    }
    @Test fun shortSlowSwipeKeepsTheCurrentCard() { assertEquals(2,swipeTargetPage(2,6,-50f,400f,-100f)) }
    @Test fun quickFlickMovesOneCardInTheFingerDirection() {
        assertEquals(3,swipeTargetPage(2,6,-40f,400f,-1800f))
        assertEquals(1,swipeTargetPage(2,6,40f,400f,1800f))
        assertEquals(2,swipeTargetPage(2,6,-40f,400f,1800f))
    }
    @Test fun deliberateSwipeScalesWithTheScreenAndCannotEscapeTheDeck() {
        assertEquals(3,swipeTargetPage(2,6,-100f,400f,0f))
        assertEquals(2,swipeTargetPage(2,6,-100f,1200f,0f))
        assertEquals(0,swipeTargetPage(0,6,180f,400f,1800f))
        assertEquals(5,swipeTargetPage(5,6,-180f,400f,-1800f))
        assertEquals(2,swipeTargetPage(2,6,Float.NaN,400f,0f))
    }
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

    @Test fun swipeAssetLookupRejectsAnotherTokenAndMissingIdentity() {
        assertNull(exactAsset(JSONObject().put("id","MON").put("symbol","MON"),"0x1111111111111111111111111111111111111111"))
        assertNull(exactAsset(JSONObject().put("symbol","MON"),"MON"))
    }
    @Test fun swipeAssetLookupAcceptsOnlyTheRequestedAddressRegardlessOfCase() {
        val id="0xAbCd111111111111111111111111111111111111"
        val asset=exactAsset(JSONObject().put("address",id).put("symbol","TOKEN").put("price",1),id.lowercase())
        assertEquals(id,asset?.id)
        assertEquals("TOKEN",asset?.symbol)
    }

}
