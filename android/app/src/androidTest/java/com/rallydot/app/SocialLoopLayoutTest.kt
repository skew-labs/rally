package com.rallydot.app

import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.concurrent.atomic.AtomicInteger

class SocialLoopLayoutTest {
 @Test fun signalAndFillFitAndOpenOnlyTheirToken() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
  val dark=InstrumentationRegistry.getArguments().getString("theme")=="dark"
  val signal=JSONObject("""{"entry":{"price":"0.00001479","source":"QA observed reference","observedAt":1791594000},"latest":{"price":"0.0000172"},"terms":{"direction":"up","target":"0.000021","invalidation":"0.000010"},"state":"active","priceChangePercent":16.29,"stale":false}""")
  val fill=JSONObject("""{"side":"buy","quantity":"67400.12345","symbol":"TEST","venue":"nad.fun","created":1791594000}""")
  val opened=AtomicInteger()
  ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->activity.setContent {RallyTheme(dark){Surface{Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)){SignalCard(signal,{opened.incrementAndGet()});VerifiedTradeCard(fill,{opened.incrementAndGet()})}}}} }
   assertTrue(device.wait(Until.hasObject(By.text("Open token")),15000))
   device.findObject(By.text("Open token")).click();inst.waitForIdleSync();assertEquals(1,opened.get())
   var buy=device.findObject(By.text("Buy"));if(buy==null){device.findObject(By.scrollable(true))?.scroll(Direction.DOWN,1f);buy=device.findObject(By.text("Buy"))}
   assertNotNull(buy);val bounds=buy!!.visibleBounds;assertTrue(bounds.left>=0&&bounds.right<=device.displayWidth&&bounds.bottom<=device.displayHeight&&bounds.height()>0)
   buy.click();inst.waitForIdleSync();assertEquals(2,opened.get())
   assertNotNull(RallyPush.route("/?view=post&post=qa-post"));assertNull(RallyPush.route("https://evil.test/?view=post"));assertNull(RallyPush.route("https://rallydot.com@evil.test/?view=post"));assertNull(RallyPush.route("javascript:alert(1)"))
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"social-loop-layout.png"))
   device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"social-loop-layout.xml"))
  }
 }
}
