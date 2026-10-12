package com.rallydot.app
import android.app.Application
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
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

/** Same composables and callbacks as production, with read-only fixture transport. */
class DiscoveryLayoutTest {
 @Test fun listsAndSwipeOpenTheSameAlgorithmPreviewWithoutSubmitting() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst);val app=inst.targetContext.applicationContext as Application
  val args=InstrumentationRegistry.getArguments();val dark=args.getString("theme")=="dark";val mode=args.getString("mode") ?: "algorithms"
  val writes=AtomicInteger();val credentials=CredentialStore(app,"qa-discovery",true).apply { clear() };val store=ViewModelStore()
  val feed=JSONObject("""{"id":"qa-wallet","owner":"rally","name":"QA trader","price":0,"access":true,"creator":{"name":"Rally","handle":"rally"},"research":{"wallet":"0x1111111111111111111111111111111111111111","returnPct":25,"pnlMON":120,"tokens":[{"symbol":"TEST"}],"trades":[{"symbol":"TEST","returnPct":25}]}}""")
  val token=JSONObject().put("owner","rally").put("symbol","TEST").put("verifiedAt",System.currentTimeMillis()/1000).put("stats",JSONObject().put("referenceMarketCapUSDC",1200)).put("asset",JSONObject().put("id","0x"+"a".repeat(40)).put("symbol","TEST").put("communityToken",true))
  val communities=JSONArray().put(JSONObject().put("id","qa").put("name","QA community").put("members",12).put("posts24h",3).put("token",token))
  val feeds=JSONArray().put(feed).put(JSONObject("""{"id":"paid","owner":"rally","name":"Paid feed","price":2,"access":false}"""))
  val client=OkHttpClient.Builder().addInterceptor { chain->val r=chain.request();if(r.method!="GET"){writes.incrementAndGet();throw AssertionError("No state or financial writes allowed")};val body=when(r.url.encodedPath) {
   "/api/bootstrap"->JSONObject().put("me",JSONObject.NULL).put("wallet","").put("activeFeed","latest").put("feeds",feeds).put("communities",communities).toString()
   "/api/auth/config"->"{\"privy\":{\"enabled\":false}}"
   "/api/posts"->"{\"posts\":[]}"
   "/api/discover/preview"->JSONObject().put("feed",feed).put("posts",JSONArray()).toString()
   else->throw AssertionError("Unexpected read "+r.url.encodedPath)
  };Response.Builder().request(r).protocol(Protocol.HTTP_1_1).code(200).message("QA").body(body.toResponseBody("application/json".toMediaType())).build() }.build()
  try { ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->val vm=RallyViewModel(app,RallyApi(app,client,credentials),DurablePairing(app,"qa-discovery-pairing"));store.put("vm",vm)
    activity.setContent { RallyTheme(dark) { Surface { var selected by remember { mutableStateOf<JSONObject?>(null) };var room by remember { mutableStateOf(false) }
     Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing)) {
      when(mode){
       "communities"->if(room)CommunityRoom(vm,"qa",{throw AssertionError("No asset action")},{selected=it},{}) { Text("Community feed") } else CommunityList(vm,{room=true},{throw AssertionError("No asset action")})
       "swipe"->SwipeScreen(vm,{throw AssertionError("No asset action")},{},{selected=it})
       else->AlgorithmList(vm,{selected=it})
      }
     };selected?.let { AlgorithmSheet(it,vm,{selected=null},{throw AssertionError("No browser")}) }
    } } }
   }
   if(mode=="communities") {
    assertTrue(device.wait(Until.hasObject(By.text("QA community")),15000));device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"discovery-list.png"));device.findObject(By.text("QA community")).click()
    assertTrue(device.wait(Until.hasObject(By.desc("Algorithms")),5000));device.findObject(By.desc("Algorithms")).click()
   } else if(mode=="swipe") {
    assertTrue(device.wait(Until.hasObject(By.desc("Algorithms")),15000));device.findObject(By.desc("Algorithms")).click()
    assertTrue(device.wait(Until.hasObject(By.text("Preview algorithm")),10000));device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"discovery-list.png"))
   } else { assertTrue(device.wait(Until.hasObject(By.text("+25.0%")),15000));device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"discovery-list.png")) }
   val action=if(mode=="swipe")By.text("Preview algorithm") else By.desc("Preview TEST trader")
   assertTrue(device.wait(Until.hasObject(action),10000));device.findObject(action).click()
   assertTrue(device.wait(Until.hasObject(By.text("Open feed")),10000));assertTrue(device.wait(Until.hasObject(By.text("Sampled wallet ROI")),10000))
   val button=device.findObject(By.text("Open feed"));if(!button.isEnabled)Thread.sleep(400)
   assertTrue(button.visibleBounds.width()>0);assertTrue(button.visibleBounds.right<=device.displayWidth)
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"discovery-preview.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"discovery-preview.xml"))
   assertEquals(0,writes.get())
  } } finally { inst.runOnMainSync { store.clear() };credentials.clear();client.dispatcher.executorService.shutdown() }
 }
}
