package com.rallydot.app
import android.app.Application
import androidx.activity.compose.setContent
import androidx.lifecycle.ViewModelStore
import androidx.compose.material3.*
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.json.JSONObject
import org.junit.Test
import org.junit.Assert.*
import java.io.File
class PerpSheetLayoutTest {
 @Test fun fullOrderSheetKeepsBuyVisibleWhenKeyboardOpens() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst);val app=inst.targetContext.applicationContext as Application
  val dark=InstrumentationRegistry.getArguments().getString("theme")=="dark"
  val credentials=CredentialStore(app,"qa-perp-sheet-session",true);credentials.clear()
  val client=OkHttpClient.Builder().addInterceptor { chain->
   val r=chain.request();val body=when(r.url.encodedPath) {
    "/api/bootstrap"->"{\"me\":null,\"wallet\":\"\"}"
    "/api/auth/config"->"{\"privy\":{\"enabled\":false}}"
    "/api/market-chart"->"{\"points\":[],\"reference\":\"QA fixture\"}"
    else->throw AssertionError("Unexpected request ${r.url.encodedPath}")
   }
   Response.Builder().request(r).protocol(Protocol.HTTP_1_1).code(200).message("QA").body(body.toResponseBody("application/json".toMediaType())).build()
  }.build()
  val asset=Asset.parse(JSONObject().put("id",1).put("symbol","BTC").put("venue","Perpl").put("mark",60000).put("lotDecimals",5).put("priceDecimals",2).put("open",true).put("execution","wallet_transactions").put("nativeSide","buy"),"perps")
  val store=ViewModelStore()
  try { ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->val vm=RallyViewModel(app,RallyApi(app,client,credentials),DurablePairing(app,"qa-perp-sheet-pairing"));store.put("qa-sheet",vm);activity.setContent { RallyTheme(dark) { Surface { AssetSheet(asset,vm,{},{throw AssertionError("No browser or wallet")}) } } } }
   assertTrue(device.wait(Until.hasObject(By.desc("Position size")),15000))
   device.findObject(By.text("USD")).click();val input=device.findObject(By.desc("Position size"));input.click();device.executeShellCommand("input text 10")
   val converted=device.wait(Until.hasObject(By.text("≈ 0.00016 BTC · Rounded down")),5000)
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"perp-sheet.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"perp-sheet.xml"))
   assertTrue("Conversion not visible in full sheet",converted)
   Thread.sleep(500);val buy=device.findObjects(By.text("Buy / Long")).last();val b=buy.visibleBounds
   assertTrue("Full sheet Buy clipped: $b",b.width()>0 && b.height()>0 && b.left>=0 && b.top>=0 && b.right<=device.displayWidth && b.bottom<=device.displayHeight)
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"perp-sheet.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"perp-sheet.xml"))
  } } finally { inst.runOnMainSync { store.clear() };credentials.clear();client.dispatcher.executorService.shutdown() }
 }
}
