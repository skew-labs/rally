package com.rallydot.app
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ConnectedDiscoveryTest {
 @Test fun creatorSubscriptionsDoNotImpersonatePublicWalletResearch() {
  val f=JSONObject().put("id","chosen").put("owner","creator").put("research",JSONObject().put("wallet","public"))
  val other=JSONObject().put("id","other").put("owner","rally").put("research",JSONObject().put("wallet","other"))
  val b=JSONObject().put("activeFeed","chosen").put("feeds",JSONArray().put(other).put(f))
  assertEquals(listOf("chosen"),homeAlgorithms(b).map { it.string("id") })
 }
 @Test fun unverifiedAlgorithmsHaveNoInventedPerformance() {
  val f=JSONObject().put("id","new").put("owner","creator").put("algorithm_version",1)
  val list=homeAlgorithms(JSONObject().put("feeds",JSONArray().put(f)))
  assertEquals(1,list.size);assertNull(algorithmReturn(list[0]));assertEquals("—",algorithmPercent(algorithmReturn(list[0])))
 }
 @Test fun creatorUsesPublicProfileNotTrackedWalletIdentity() {
  val f=JSONObject().put("owner","rally").put("creator",JSONObject().put("name","Rally"))
  val p=JSONObject().put("id","rally").put("name","Rally Research").put("avatar","/assets/community-rally.png")
  assertEquals("Rally Research",discoveryCreator(f,listOf(p)).name)
 }
}
