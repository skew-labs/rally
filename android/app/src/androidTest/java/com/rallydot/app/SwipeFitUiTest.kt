package com.rallydot.app

import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Surface
import androidx.compose.runtime.CompositionLocalProvider
import androidx.compose.ui.Modifier
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import okhttp3.OkHttpClient
import okhttp3.Response
import okhttp3.Protocol
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class SwipeFitUiTest {
 @Test fun chartSwipesAdvanceAndActionsFitAtLargeText() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
  val now=System.currentTimeMillis()/1000
  val client=OkHttpClient.Builder().addInterceptor { chain->
   val request=chain.request();assertEquals("GET",request.method)
   val id=request.url.queryParameter("asset") ?: "1"
   val body=if(request.url.encodedPath.contains("market-chart"))"""{"asset":"$id","points":[{"time":${now-60},"value":100},{"time":$now,"value":110}]}""" else """{"me":null,"feeds":[],"people":[],"communities":[],"watches":[],"posts":[]}"""
   Response.Builder().request(request).protocol(Protocol.HTTP_1_1).code(200).message("OK").body(body.toResponseBody("application/json".toMediaType())).build()
  }.build()
  for(dark in listOf(false,true))ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->
    val vm=RallyViewModel(activity.application,RallyApi(activity,client,CredentialStore(activity,"swipe-fit-qa")))
    val items=listOf("BTC","ETH").mapIndexed { i,symbol->JSONObject().put("id",i+1).put("symbol",symbol).put("name",symbol).put("venue","Perpl").put("mark",100).put("open",true).put("execution","wallet_transactions").put("fetchedAt",now).put("price",100).put("tradeSupported",true) }
    activity.setContent { RallyTheme(dark) { CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density,1.3f)) {
     Surface(Modifier.fillMaxSize()) { Column(Modifier.windowInsetsPadding(WindowInsets.systemBars)) {
      NativeSwipeDeck(listOf("btc","eth"),Modifier.weight(1f)) { i->SocialSwipeCard(items[i],"Perps",i,2,vm,{},{}) }
     } }
    } } }
   }
   val chart=By.desc("Price line chart, 2 observations")
   assertTrue(device.wait(Until.hasObject(chart),8000))
   for(label in listOf("Long","Short")) {
    val bounds=device.findObject(By.text(label)).visibleBounds
    assertTrue(bounds.left>=0 && bounds.right<=device.displayWidth)
    assertTrue(bounds.height()>0 && bounds.bottom<device.displayHeight)
   }
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"swipe-fit-${if(dark)"dark" else "light"}.png"))
   val bounds=device.findObject(chart).visibleBounds
   val startY=bounds.bottom-24;val endY=(bounds.top-200).coerceAtLeast(100)
   android.util.Log.i("SwipeFit","bounds=$bounds display=${device.displayHeight} from=$startY to=$endY")
   device.swipe(bounds.centerX(),startY,bounds.centerX(),endY,20)
   device.waitForIdle()
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"swipe-fit-after.png"))
   device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"swipe-fit-after.xml"))
   assertTrue("Vertical swipe starting on chart should advance",device.wait(Until.hasObject(By.text("2 / 2")),5000))
   assertTrue(device.wait(Until.hasObject(By.desc("Previous card").enabled(true)),5000))
   device.findObject(By.desc("Previous card").enabled(true)).click()
   assertTrue(device.wait(Until.hasObject(By.text("1 / 2")),5000))
  }
 }
}
