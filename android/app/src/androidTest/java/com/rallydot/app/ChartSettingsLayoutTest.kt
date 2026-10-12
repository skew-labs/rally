package com.rallydot.app

import android.app.Application
import androidx.activity.compose.setContent
import androidx.lifecycle.ViewModelStore
import androidx.compose.material3.Surface
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.json.JSONObject
import org.json.JSONArray
import org.junit.Test
import org.junit.Assert.*
import java.io.File

class ChartSettingsLayoutTest {
 @Test fun lineIsDefaultAndTickWindowSurvivesReopening() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
  val app=inst.targetContext.applicationContext as Application
  val prefs=app.getSharedPreferences("rally_chart_v1",0);prefs.edit().clear().commit()
  val credentials=CredentialStore(app,"qa-chart-settings",true);credentials.clear()
  val now=System.currentTimeMillis()/1000;val hour=now/3600*3600
  val client=OkHttpClient.Builder().addInterceptor { chain->
   val r=chain.request();assertEquals("Read-only chart test","GET",r.method)
   val body=when(r.url.encodedPath) {
    "/api/bootstrap"->JSONObject().put("me",JSONObject.NULL)
    "/api/auth/config"->JSONObject().put("privy",JSONObject().put("enabled",false))
    "/api/market-chart"->JSONObject().put("asset","1").put("kind","perps").put("freshRead",true).put("cached",false).put("period",r.url.queryParameter("period")).put("interval","1h").put("reference","QA OHLC")
      .put("points",JSONArray().put(JSONObject().put("time",hour-3600).put("value",60000)).put(JSONObject().put("time",hour).put("value",60100)))
      .put("candles",JSONArray().put(JSONObject().put("time",hour).put("open",60000).put("high",60200).put("low",59900).put("close",60100)))
    "/api/market-ticks"->JSONObject().put("asset","1").put("kind","perps").put("epoch","qa").put("cursor",150).put("observationType","price_update").put("source","QA prices")
      .put("points",JSONArray().apply { repeat(150){i->put(JSONObject().put("id",i+1).put("time",now-150+i).put("value",60000+i))} })
    else->throw AssertionError("Unexpected request ${r.url.encodedPath}")
   }
   Response.Builder().request(r).protocol(Protocol.HTTP_1_1).code(200).message("QA").body(body.toString().toResponseBody("application/json".toMediaType())).build()
  }.build()
  val asset=Asset.parse(JSONObject().put("id",1).put("symbol","BTC").put("venue","Perpl").put("mark",60000).put("open",true).put("execution","wallet_transactions"),"perps")
  val store=ViewModelStore()
  try {
   val vm=RallyViewModel(app,RallyApi(app,client,credentials),DurablePairing(app,"qa-chart-pairing"));store.put("chart",vm)
   fun open(check:()->Unit) { ActivityScenario.launch(RallyActivity::class.java).use { scenario->
    scenario.onActivity { activity->activity.setContent { RallyTheme(false) { Surface { AssetSheet(asset,vm,{},{throw AssertionError("No browser or wallet")}) } } } }
    check()
   } }
   open {
    assertTrue(device.wait(Until.hasObject(By.descStartsWith("Price line chart")),15000))
    device.findObject(By.text("Candles")).click()
    assertTrue(device.wait(Until.hasObject(By.descStartsWith("1 hour candlestick")),8000))
    device.findObject(By.text("Ticks")).click()
    assertTrue(device.wait(Until.hasObject(By.descStartsWith("Price ticks")),8000))
    device.findObject(By.text("120")).click()
    assertTrue(device.wait(Until.hasObject(By.descContains("last 120 updates")),5000))
    device.takeScreenshot(File(app.getExternalFilesDir(null),"chart-ticks-120.png"))
    device.findObject(By.text("30")).click()
    assertTrue(device.wait(Until.hasObject(By.descContains("last 30 updates")),5000))
   }
   open {
    assertTrue(device.wait(Until.hasObject(By.descContains("last 30 updates")),15000))
    device.findObject(By.text("Line")).click()
    assertTrue(device.wait(Until.hasObject(By.descStartsWith("Price line chart")),8000))
    device.findObject(By.text("Live")).click()
    assertTrue(device.wait(Until.hasObject(By.descStartsWith("Live price line")),8000))
    device.findObject(By.text("7D")).click()
    assertTrue(device.wait(Until.hasObject(By.descStartsWith("Price line chart")),8000))
    device.takeScreenshot(File(app.getExternalFilesDir(null),"chart-line-default.png"))
   }
  } finally { inst.runOnMainSync { store.clear() };prefs.edit().clear().commit();credentials.clear();client.dispatcher.executorService.shutdown() }
 }
}
