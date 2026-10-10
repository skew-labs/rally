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
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class TouchFlowTest {
 @Test fun marketBuyOpensOrderInOneTapAndShortcutsPreserveDirection() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst);val app=inst.targetContext.applicationContext as Application
  val dark=InstrumentationRegistry.getArguments().getString("theme")=="dark"
  fun find(selector: BySelector,direction: Direction=Direction.DOWN,button: Boolean=false): UiObject2 {
   fun candidate(): UiObject2? { return try {
    var node=device.findObject(selector) ?: return null
    if(button) {
     repeat(4) { if(!node.isClickable)node=node.parent ?: return null }
     if(!node.isClickable || node.visibleBounds.height()<44*inst.targetContext.resources.displayMetrics.density)return null
     val visible=android.graphics.Rect(node.visibleBounds)
     var ancestor=node.parent
     while(ancestor!=null) {
      if(ancestor.isScrollable && !visible.intersect(ancestor.visibleBounds))return null
      ancestor=ancestor.parent
     }
     if(visible.height()<44*inst.targetContext.resources.displayMetrics.density)return null
    }
    node
   } catch(_: StaleObjectException) { null } }
   device.wait(Until.hasObject(selector),500);repeat(4) { candidate()?.let { return it };Thread.sleep(100) }
   repeat(5) {
    device.wait(Until.hasObject(By.scrollable(true)),2000)
    val scroller=device.findObjects(By.scrollable(true)).lastOrNull { it.visibleBounds.width()>0 }
    val bounds=scroller?.visibleBounds ?: throw AssertionError("No order scroller")
    val x=bounds.left+12;val top=bounds.top+12;val bottom=bounds.bottom-12
    device.swipe(x,if(direction==Direction.DOWN)bottom else top,x,(top+bottom)/2,60)
    device.waitForIdle(2000)
    Thread.sleep(600)
    device.wait(Until.hasObject(selector),500);repeat(4) { candidate()?.let { return it };Thread.sleep(100) }
   }
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"touch-scroll.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"touch-scroll.xml"))
   throw AssertionError("Control unavailable in scrollable order sheet: $selector")
  }
  val appearance=app.getSharedPreferences("appearance",android.content.Context.MODE_PRIVATE);val hadTheme=appearance.contains("dark");val previousTheme=appearance.getBoolean("dark",false);appearance.edit().putBoolean("dark",dark).commit()
  val credentials=CredentialStore(app,"qa-touch-session",true);credentials.clear();val store=ViewModelStore()
  val market=JSONObject().put("id",7).put("symbol","BTC").put("venue","Perpl").put("mark",60000).put("lotDecimals",5).put("priceDecimals",2).put("open",true).put("stale",false).put("execution","wallet_transactions")
  val client=OkHttpClient.Builder().addInterceptor { chain->
   val r=chain.request();assertEquals("Read-only UI test", "GET",r.method)
   val body=when(r.url.encodedPath) {
    "/api/bootstrap"->"{\"me\":null,\"wallet\":\"\"}"
    "/api/auth/config"->"{\"privy\":{\"enabled\":false}}"
    "/api/perps"->JSONObject().put("markets",org.json.JSONArray().put(market)).toString()
    "/api/nadfun/tokens"->"{\"tokens\":[],\"total\":0}"
    "/api/market-chart"->"{\"points\":[],\"reference\":\"QA fixture\"}"
    else->throw AssertionError("Unexpected request ${r.url.encodedPath}")
   }
   Response.Builder().request(r).protocol(Protocol.HTTP_1_1).code(200).message("QA").body(body.toResponseBody("application/json".toMediaType())).build()
  }.build()
  try { ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->val vm=RallyViewModel(app,RallyApi(app,client,credentials),DurablePairing(app,"qa-touch-pairing"));store.put("qa",vm);activity.setContent { RallyApp(vm,{throw AssertionError("No browser or wallet")},null) } }
   assertTrue(device.wait(Until.hasObject(By.text("Perps")),15000));device.findObject(By.text("Perps")).click()
   assertTrue(device.wait(Until.hasObject(By.desc("Buy / Long BTC")),10000));val quick=device.findObject(By.desc("Buy / Long BTC"));assertTrue(quick.isEnabled)
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"touch-market.png"));quick.click()
   assertTrue(device.wait(Until.hasObject(By.desc("Position size")),5000))
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"touch-order-start.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"touch-order-start.xml"))
   find(By.text("$25"),button=true)
   device.waitForIdle();Thread.sleep(600)
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"touch-preset-before.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"touch-preset-before.xml"))
   find(By.text("$25"),button=true).click()
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"touch-preset-after.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"touch-preset-after.xml"))
   assertTrue("Preset did not set USD position",device.wait(Until.hasObject(By.text("≈ 0.00041 BTC · Rounded down")),3000))
   find(By.desc("Sell / Short"),Direction.UP).click();find(By.text("≈ 0.00041 BTC · Rounded down"))
   assertFalse("Advanced price is expanded by default",device.hasObject(By.text("Protection price · USD")))
   val action=device.findObjects(By.text("Sell / Short")).last();assertTrue(action.visibleBounds.width()>0 && action.visibleBounds.bottom<=device.displayHeight)
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"touch-flow.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"touch-flow.xml"))
  } } catch(e: Throwable) {
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"touch-flow-failure.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"touch-flow-failure.xml"));throw e
  } finally { inst.runOnMainSync { store.clear() };credentials.clear();client.dispatcher.executorService.shutdown();if(hadTheme)appearance.edit().putBoolean("dark",previousTheme).commit() else appearance.edit().remove("dark").commit() }
 }
}
