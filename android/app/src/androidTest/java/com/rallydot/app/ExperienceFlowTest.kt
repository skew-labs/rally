package com.rallydot.app

import android.app.Application
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Surface
import androidx.compose.ui.Modifier
import androidx.lifecycle.ViewModelStore
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import org.json.JSONArray
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
import java.util.concurrent.atomic.AtomicReference

/** Exercises production view models/composables with a provider-blocked QA transport. */
class ExperienceFlowTest {
 private val inst=InstrumentationRegistry.getInstrumentation()
 private val device=UiDevice.getInstance(inst)
 private fun waitUntil(message: String,condition: ()->Boolean) {
  repeat(150){if(condition())return;Thread.sleep(40)};assertTrue(message,condition())
 }
 private fun button(description:String):UiObject2 {
  var node=device.findObject(By.desc(description)) ?: throw AssertionError("Missing $description")
  while(!node.isClickable)node=node.parent ?: throw AssertionError("No target for $description")
  return node
 }
 private inner class Fixture:AutoCloseable {
  val app=inst.targetContext.applicationContext as Application
  val credentials=CredentialStore(app,"qa-experience-session",true).apply{clear()}
  val store=ViewModelStore()
  val reactions=AtomicInteger();val feedUses=AtomicInteger();val posts=AtomicInteger()
  val gate=AtomicReference<CountDownLatch?>(null)
  @Volatile var fail=false
  @Volatile var active="latest"
  val token="0x"+"a".repeat(40)
  val post=JSONObject("""{"id":"qa-post","text":"QA reading position stays in place.","author":{"id":"qa-author","name":"Codex","handle":"qa_author","kind":"agent"},"likes":2,"liked":false,"replies":0}""")
  val feeds=JSONArray("""[{"id":"latest","name":"Latest","price":0},{"id":"momentum","name":"Momentum","price":0},{"id":"paid","name":"Paid research","price":2,"access":false}]""")
  val client=OkHttpClient.Builder().addInterceptor { chain->
   val request=chain.request();val path=request.url.encodedPath
   var status=200
   val body=if(request.method=="GET")when(path) {
    "/api/bootstrap"->JSONObject().put("me",JSONObject().put("id","qa-owner").put("name","QA reader").put("handle","qa_reader").put("communityToken",JSONObject().put("address",token).put("name","A very long community token name that should fit the profile row").put("symbol","TEST").put("buybackBps",2000))).put("wallet","").put("activeFeed",active).put("feeds",feeds).put("communities",JSONArray()).toString()
    "/api/auth/config"->"{\"privy\":{\"enabled\":false}}"
    "/api/posts"->{posts.incrementAndGet();JSONObject().put("posts",JSONArray().put(post)).toString()}
    "/api/perps"->JSONObject().put("markets",JSONArray().put(market(7,"BTC",60000)).put(market(8,"ETH",3000))).toString()
    "/api/market-chart"->"{\"points\":[],\"reference\":\"QA\"}"
    else->throw AssertionError("Unexpected QA read $path")
   } else {
    val buffer=Buffer();request.body!!.writeTo(buffer);val args=JSONObject(buffer.readUtf8())
    when(path) {
     "/api/reaction"->{assertEquals("like",args.string("kind"));reactions.incrementAndGet();gate.get()?.let{assertTrue("QA reaction release timed out",it.await(15,TimeUnit.SECONDS))};if(fail){status=503;"{\"error\":\"QA temporary outage\"}"}else JSONObject().put("liked",args.optBoolean("active")).put("likes",if(args.optBoolean("active"))3 else 2).toString()}
     "/api/feeds/use"->{feedUses.incrementAndGet();active=args.string("id");"{}"}
     else->throw AssertionError("No wallet or financial submission allowed: $path")
    }
   }
   Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(status).message("QA").body(body.toResponseBody("application/json".toMediaType())).build()
  }.build()
  lateinit var vm:RallyViewModel
  init{inst.runOnMainSync{vm=RallyViewModel(app,RallyApi(app,client,credentials),DurablePairing(app,"qa-experience-pairing"));store.put("qa",vm)};waitUntil("QA bootstrap"){vm.me!=null}}
  fun market(id:Int,symbol:String,price:Int)=JSONObject().put("id",id).put("symbol",symbol).put("venue","Perpl").put("mark",price).put("open",true).put("stale",false).put("execution","wallet_transactions").put("fetchedAt",System.currentTimeMillis()/1000)
  override fun close(){gate.get()?.countDown();inst.runOnMainSync{store.clear()};credentials.clear();client.dispatcher.executorService.shutdown()}
 }
 @Test fun reactionsKeepThePageAndRollbackWithoutDuplicateRequests() {
  Fixture().use { f->
   inst.runOnMainSync{f.vm.load("qa-feed","/api/posts","posts")};waitUntil("QA page"){f.vm.state.value.pages["qa-feed"]?.loading==false}
   val page=f.vm.state.value.pages["qa-feed"]!!;val beforeReads=f.posts.get();val p=Post.parse(f.post)
   val release=CountDownLatch(1);f.gate.set(release)
   inst.runOnMainSync{f.vm.react(p);f.vm.react(p)}
   val immediate=f.vm.state.value.reactions[p.id]!!
   assertTrue(immediate.liked);assertTrue(immediate.pending);assertEquals(3,immediate.likes);assertFalse(f.vm.state.value.busy)
   assertSame(page,f.vm.state.value.pages["qa-feed"]);waitUntil("Only one reaction request"){f.reactions.get()==1};release.countDown()
   waitUntil("Confirmed reaction"){f.vm.state.value.reactions[p.id]?.pending==false};assertEquals(3,f.vm.state.value.reactions[p.id]?.likes)
   f.gate.set(null);f.fail=true;inst.runOnMainSync{f.vm.react(p)}
   waitUntil("Failed reaction restored"){f.reactions.get()==2 && f.vm.state.value.reactions[p.id]?.pending==false}
   assertTrue(f.vm.state.value.reactions[p.id]!!.liked);assertEquals(3,f.vm.state.value.reactions[p.id]?.likes);assertNotNull(f.vm.state.value.message)
   f.fail=false;inst.runOnMainSync{f.vm.react(p)};waitUntil("Retry confirmed"){f.reactions.get()==3 && f.vm.state.value.reactions[p.id]?.pending==false}
   assertFalse(f.vm.state.value.reactions[p.id]!!.liked);assertEquals(2,f.vm.state.value.reactions[p.id]?.likes)
   assertEquals(beforeReads,f.posts.get());assertSame(page,f.vm.state.value.pages["qa-feed"])
   // A response from the old session must not update a later session.
   val old=CountDownLatch(1);f.gate.set(old);inst.runOnMainSync{f.vm.react(p)};waitUntil("Old request started"){f.reactions.get()==4}
   inst.runOnMainSync{f.vm.api.signIn("q".repeat(48))};old.countDown()
   waitUntil("Old request unlocked"){f.vm.state.value.reactions[p.id]?.pending==false}
   assertFalse(f.vm.state.value.reactions[p.id]!!.liked)
  }
 }
 @Test fun pickerSwipeAndProfileUseTheirExistingInPlaceActions() {
  val dark=InstrumentationRegistry.getArguments().getString("theme")=="dark"
  Fixture().use { f->ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   val preview=AtomicReference<String?>(null);val opened=AtomicReference<String?>(null)
   try {
    scenario.onActivity{a->a.setContent{RallyTheme(dark){Surface(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)){FeedScreen(f.vm,onPost={},onAsset={},compose={},onFeedPreview={preview.set(it.string("id"))})}}}}
    assertTrue(device.wait(Until.hasObject(By.text("Latest")),10000));device.findObject(By.text("Latest")).click()
    assertTrue(device.wait(Until.hasObject(By.text("Your algorithm")),5000));device.findObject(By.text("Momentum")).click()
    waitUntil("Algorithm selected"){f.feedUses.get()==1&&f.active=="momentum"};assertTrue(device.wait(Until.hasObject(By.text("Momentum")),5000));assertTrue(device.wait(Until.gone(By.text("Your algorithm")),5000))
    device.findObject(By.text("Momentum")).click();assertTrue(device.wait(Until.hasObject(By.text("Paid research")),5000));device.findObject(By.text("Paid research")).click();waitUntil("Paid preview"){preview.get()=="paid"};assertEquals(1,f.feedUses.get())
    scenario.onActivity{a->a.setContent{RallyTheme(dark){Surface(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)){SwipeScreen(f.vm,{opened.set(it.id)},{})}}}}
    assertTrue(device.wait(Until.hasObject(By.text("Perps")),10000));device.findObject(By.text("Perps")).click()
    assertTrue(device.wait(Until.hasObject(By.desc("Next card")),10000));fun next()=button("Next card")
    assertTrue(next().isEnabled);next().click();assertTrue(device.wait(Until.hasObject(By.text("2 / 2")),5000));assertFalse(next().isEnabled)
    val bounds=next().visibleBounds;assertTrue(bounds.left>=0&&bounds.right<=device.displayWidth&&bounds.bottom<=device.displayHeight);assertTrue(bounds.height()>=44*f.app.resources.displayMetrics.density)
    device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"experience-swipe.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"experience-swipe.xml"))
    waitUntil("Paging settled"){button("Previous card").isEnabled};button("Previous card").click();assertTrue(device.wait(Until.hasObject(By.text("1 / 2")),5000));assertNull("Paging must not trade",opened.get())
    scenario.onActivity{a->a.setContent{RallyTheme(dark){Surface(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)){ProfileScreen(f.vm,{}, {},{opened.set(it)})}}}}
    assertTrue(device.wait(Until.hasObject(By.textStartsWith("A very long community token")),10000));device.findObject(By.textStartsWith("A very long community token")).click();assertEquals(f.token,opened.get())
    device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"experience-profile.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"experience-profile.xml"))
   }catch(e:Throwable){device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"experience-failure.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"experience-failure.xml"));throw e}
  } }
 }
 @Test fun horizontalGestureMovesOneCardAndNeverOpensAnOrder() {
  val dark=InstrumentationRegistry.getArguments().getString("theme")=="dark"
  Fixture().use{f->ActivityScenario.launch(RallyActivity::class.java).use{scenario->
   val opened=AtomicInteger()
   scenario.onActivity{a->a.setContent{RallyTheme(dark){Surface(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)){SwipeScreen(f.vm,{opened.incrementAndGet()},{opened.incrementAndGet()})}}}}
   assertTrue(device.wait(Until.hasObject(By.text("Perps")),10000));device.findObject(By.text("Perps")).click()
   assertTrue(device.wait(Until.hasObject(By.text("1 / 2")),10000));waitUntil("Deck ready"){button("Next card").isEnabled}
   val w=device.displayWidth;val y=device.displayHeight/2
   device.swipe(w*8/10,y,w*75/100,y,25);Thread.sleep(500);assertTrue(device.hasObject(By.text("1 / 2")))
   device.swipe(w*8/10,y,w/10,y,35);assertTrue(device.wait(Until.hasObject(By.text("2 / 2")),5000));waitUntil("Horizontal transition settled"){button("Previous card").isEnabled}
   assertFalse(button("Next card").isEnabled);assertEquals(0,opened.get())
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"experience-horizontal.png"))
  }}
 }
}
