package com.rallydot.app
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.ui.Modifier
import androidx.compose.material3.Surface
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.unit.Density
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
class TokenRecencyUiTest {
 @Test fun compactRowsFitLargeTextAndKeepBuyDistinct() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
  val intent=mutableStateOf("None")
  val asset=Asset.parse(JSONObject().put("id","qa-recency").put("symbol","LONGTOKENNAME").put("name","QA token")
   .put("price",.00992).put("marketCap",9920000).put("volume",179400).put("change",1735.07).put("graduatedAt",System.currentTimeMillis()/1000-1200))
  for(dark in listOf(false,true))ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->activity.setContent { RallyTheme(dark) {
    CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density,1.3f)) {
     Surface(Modifier.fillMaxSize()) { Column(Modifier.windowInsetsPadding(WindowInsets.systemBars)) {Text("Recently graduated");TokenMarketRow(asset,"Graduated",{intent.value="Detail"},{intent.value="Buy intent"});Text(intent.value)} }
    }
   } } }
   assertTrue(device.wait(Until.hasObject(By.text("$9.92M MC")),5000))
   val cap=device.findObject(By.text("$9.92M MC"));val buy=device.findObject(By.desc("Buy LONGTOKENNAME"))
   assertTrue(cap.visibleBounds.left>=0);assertTrue(cap.visibleBounds.right<=buy.visibleBounds.left)
   assertTrue(buy.visibleBounds.right<=device.displayWidth)
   assertTrue(device.hasObject(By.text("$179.4K Vol")))
   buy.click();assertTrue(device.wait(Until.hasObject(By.text("Buy intent")),2000))
   cap.click();assertTrue(device.wait(Until.hasObject(By.text("Detail")),2000))
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"token-recency-${if(dark)"dark" else "light"}.png"))
  }
 }
}
