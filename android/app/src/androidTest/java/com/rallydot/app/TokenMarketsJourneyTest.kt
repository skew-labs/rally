package com.rallydot.app

import android.app.Application
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
import androidx.compose.material3.Text
import androidx.compose.runtime.*
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
import java.util.concurrent.CopyOnWriteArrayList

class TokenMarketsJourneyTest {
 @Test fun categoriesUseOneMarketAndPreserveBuyIntent() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
  val app=inst.targetContext.applicationContext as Application;val store=ViewModelStore()
  val credentials=CredentialStore(app,"qa-token-markets",true).apply{clear()}
  val requests=CopyOnWriteArrayList<String>();val selected=mutableStateOf("None")
  val client=OkHttpClient.Builder().addInterceptor { chain->val r=chain.request();assertEquals("GET",r.method)
   val response=when(r.url.encodedPath){
    "/api/bootstrap"->JSONObject().put("feeds",JSONArray()).put("people",JSONArray()).put("communities",JSONArray())
    "/api/auth/config"->JSONObject("""{"privy":{"enabled":false}}""")
    "/api/token-markets"->{val category=r.url.queryParameter("category")!!;requests.add(category)
     val token=JSONObject().put("id","0x"+"a".repeat(40)).put("symbol","QA").put("name","QA $category")
      .put("price",1.2).put("change",2).put("fetchedAt",System.currentTimeMillis()/1000).put("chainId",143).put("tradeSupported",true)
     JSONObject().put("tokens",JSONArray().put(token)).put("total",1)
    }
    else->JSONObject()
   };Response.Builder().request(r).protocol(Protocol.HTTP_1_1).code(200).message("QA").body(response.toString().toResponseBody("application/json".toMediaType())).build()
  }.build()
  try {ActivityScenario.launch(RallyActivity::class.java).use {scenario->
   scenario.onActivity {activity->val vm=RallyViewModel(app,RallyApi(app,client,credentials),DurablePairing(app,"qa-token-markets"));store.put("vm",vm)
    activity.setContent {RallyTheme(false){Column {Text("Intent: "+selected.value);MarketsScreen(vm,{selected.value=if(it.raw.string("nativeSide")=="buy")"Buy" else "Detail"})}}}
   }
   assertTrue(device.wait(Until.hasObject(By.text("QA crypto")),10000))
   assertFalse(device.hasObject(By.text("Memes")));assertFalse(device.hasObject(By.text("Spot")))
   for(label in listOf("Trending","Graduated","New","Crypto")) {
    assertTrue(device.wait(Until.hasObject(By.text(label)),5000));val filter=device.findObject(By.text(label))
    assertTrue(filter.visibleBounds.left>=0);assertTrue(filter.visibleBounds.right<=device.displayWidth)
    filter.click();assertTrue(device.wait(Until.hasObject(By.text("QA "+label.lowercase())),10000))
   }
   assertTrue(requests.containsAll(listOf("crypto","trending","graduated","new")))
   device.findObject(By.text("QA")).click();assertTrue(device.wait(Until.hasObject(By.text("Intent: Detail")),2000))
   device.findObject(By.desc("Buy QA")).click();assertTrue(device.wait(Until.hasObject(By.text("Intent: Buy")),2000))
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"token-markets.png"))
  }} finally {inst.runOnMainSync{store.clear()};credentials.clear();client.dispatcher.executorService.shutdown()}
 }
}
