package com.rallydot.app

import android.app.Application
import androidx.activity.compose.setContent
import androidx.lifecycle.ViewModelStore
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.json.*
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.concurrent.atomic.AtomicInteger

class SocialSubscriptionJourneyTest {
 @Test fun communityAuthorAndLeaderboardReachTheSamePricedSubscription() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst);val app=inst.targetContext.applicationContext as Application
  val credentials=CredentialStore(app,"qa-social-subscriptions",true).apply{clear()};val store=ViewModelStore();val writes=AtomicInteger()
  val token=JSONObject().put("id","0x"+"a".repeat(40)).put("address","0x"+"a".repeat(40)).put("symbol","QA").put("name","QA token").put("price",1).put("change",12).put("stale",false).put("fetchedAt",System.currentTimeMillis()/1000)
  val linked=JSONObject(token.toString()).put("vault","0x"+"f".repeat(40)).put("buybackBps",2000)
  val person=JSONObject().put("id","qa-creator").put("name","QA creator").put("handle","qa_creator").put("kind","person").put("communityToken",linked)
  val feed=JSONObject().put("id","qa-feed").put("owner","qa-creator").put("name","Early discovery").put("creator",person).put("price","2.5").put("priceRaw","2500000").put("periodDays",30).put("access",false).put("communityToken",linked)
  val post=JSONObject().put("id","qa-post").put("author",person).put("text","QA community observation").put("created",System.currentTimeMillis()/1000)
  val entry=JSONObject().put("id","qa-feed").put("author",person).put("algorithms",JSONArray().put(feed)).put("rank",1).put("performance",JSONObject().put("roi",12).put("closedTrades",2))
  val client=OkHttpClient.Builder().addInterceptor { chain->val r=chain.request();if(r.method!="GET"){writes.incrementAndGet();throw AssertionError("Writes forbidden")}
   val response=when(r.url.encodedPath){
    "/api/bootstrap"->JSONObject().put("me",JSONObject.NULL).put("wallet","").put("activeFeed","latest").put("feeds",JSONArray().put(feed)).put("people",JSONArray().put(person)).put("communities",JSONArray())
    "/api/auth/config"->JSONObject("""{"privy":{"enabled":false}}""")
    "/api/posts"->JSONObject().put("posts",JSONArray().put(post))
    "/api/profile"->person
    "/api/market-catalog"->JSONObject().put("tokens",JSONArray().put(token))
    "/api/performance/leaderboard"->JSONObject().put("entries",JSONArray().put(entry)).put("unranked",JSONArray()).put("basis","QA fixture")
    "/api/discover/preview"->JSONObject().put("feed",feed).put("creator",person).put("posts",JSONArray().put(post))
    else->JSONObject()
   };Response.Builder().request(r).protocol(Protocol.HTTP_1_1).code(200).message("QA").body(response.toString().toResponseBody("application/json".toMediaType())).build()
  }.build()
  fun tap(selector:BySelector){repeat(5){assertTrue("Missing $selector",device.wait(Until.hasObject(selector),15000));try{device.findObject(selector).click();return}catch(_:StaleObjectException){Thread.sleep(100)}};error("Unstable target $selector")}
  try { ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->val vm=RallyViewModel(app,RallyApi(app,client,credentials),DurablePairing(app,"qa-social-subscriptions-pairing"));store.put("vm",vm);activity.setContent{RallyApp(vm,{throw AssertionError("No external browser")},null)} }
   tap(By.desc("Community"));assertTrue(device.wait(Until.hasObject(By.text("Subscriptions")),5000));val feedLabel=device.findObject(By.text("Subscriptions")).visibleBounds;assertTrue("Feed name clipped",feedLabel.width()>feedLabel.height()*2.5);assertTrue(device.wait(Until.hasObject(By.text("QA community observation")),15000))
   tap(By.text("QA creator"));assertTrue(device.wait(Until.hasObject(By.text("Subscribe")),15000));tap(By.text("Early discovery"))
   assertTrue(device.wait(Until.hasObject(By.text("Subscribe · 2.5 USDC")),15000));assertTrue(device.wait(Until.hasObject(By.text("Buyback allocation")),10000));assertTrue(device.hasObject(By.text("20%")))
   val button=device.findObject(By.text("Subscribe · 2.5 USDC"));assertTrue(button.visibleBounds.right<=device.displayWidth);assertTrue(button.visibleBounds.left>=0)
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"social-subscription.png"));device.pressBack()
   tap(By.desc("Search"));assertTrue(device.wait(Until.hasObject(By.text("Token name or address")),10000));assertTrue(device.wait(Until.hasObject(By.text("QA token")),10000));assertTrue(device.hasObject(By.text("24h gainers")))
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"social-search.png"))
   tap(By.desc("Leaderboard"));assertTrue(device.wait(Until.hasObject(By.text("+12.0%")),15000));tap(By.text("Subscribe"));assertTrue(device.wait(Until.hasObject(By.text("Subscribe · 2.5 USDC")),10000))
   assertEquals(0,writes.get())
  } } finally {inst.runOnMainSync{store.clear()};credentials.clear();client.dispatcher.executorService.shutdown()}
 }
}
