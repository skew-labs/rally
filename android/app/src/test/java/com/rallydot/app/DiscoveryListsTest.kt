package com.rallydot.app
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class DiscoveryListsTest {
 @Test fun playbookLanesKeepResearchResultsSeparateFromWalletReturns() {
  val meme=JSONObject("""{"id":"rally-ref-098","sourceId":"nad","category":"Token research"}""")
  val year=JSONObject("""{"id":"rally-ref-001","sourceId":"aqr","category":"Institutional","performance1Y":{"basis":"published_factor","months":12,"returnPct":10}}""")
  assertEquals("Memes",strategyLane(meme));assertEquals(listOf(meme),orderedStrategies(listOf(year,meme),"Memes"))
  assertEquals(listOf(year),orderedStrategies(listOf(year,meme),"1Y returns"));assertNull(algorithmReturn(year))
  assertEquals(listOf(meme,year),orderedStrategies(listOf(year,meme),"All"))
 }
 @Test fun roiRequiresAnIdentifiedWalletAndNeverInventsAlgorithmReturns() {
  assertNull(algorithmReturn(JSONObject("""{"research":{"returnPct":300}}""")))
  assertNull(algorithmReturn(JSONObject("""{"research":{"wallet":"0xabc"}}""")))
  assertEquals(12.5,algorithmReturn(JSONObject("""{"research":{"wallet":"0xabc","returnPct":"12.5"}}"""))!!,0.0)
 }
 @Test fun rankingSwitchesMetricWithoutTreatingFreeFeedsAsProfitable() {
  val a=JSONObject("""{"id":"a","research":{"wallet":"0xa","returnPct":10,"pnlMON":100}}""")
  val b=JSONObject("""{"id":"b","research":{"wallet":"0xb","returnPct":50,"pnlMON":20}}""")
  val free=JSONObject("""{"id":"free","price":0}""")
  assertEquals(listOf("a","b","free"),rankedAlgorithms(listOf(free,b,a)).map { it.string("id") })
  assertEquals(listOf("b","a","free"),rankedAlgorithms(listOf(free,b,a),true).map { it.string("id") })
 }
 @Test fun communityCapExpiresAndZeroStaysZero() {
  val c=JSONObject("""{"token":{"verifiedAt":1000,"stats":{"referenceMarketCapUSDC":0}}}""")
  assertEquals(0.0,communityReference(c,1100)!!,0.0)
  assertNull(communityReference(c,1121))
  c.getJSONObject("token").put("stale",true);assertNull(communityReference(c,1001))
 }
}
