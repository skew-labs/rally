package com.rallydot.app

import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.Column
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

class FocusedNavigationTest {
 @Test fun homeSectionsRemainReachableWithLargeText() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
  val selected=mutableStateOf("Markets")
  ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->activity.setContent {RallyTheme(false) {
    CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density,1.3f)) {
     Column {HomeSections(selected.value,{selected.value=it});Text("Selected: "+selected.value)}
    }
   }}}
   for(label in listOf("Launch","Swipe","Feed","Markets")) {
    assertTrue(device.wait(Until.hasObject(By.text(label)),5000))
    val tab=device.findObject(By.text(label));assertTrue(tab.visibleBounds.right<=device.displayWidth)
    tab.click();assertTrue(device.wait(Until.hasObject(By.text("Selected: $label")),2000))
   }
  }
 }
 @Test fun marketRowSeparatesDetailFromBuy() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
  val intent=mutableStateOf("None")
  val asset=Asset.parse(JSONObject().put("id","qa-focus").put("symbol","QA").put("name","QA market row").put("price",1.25).put("marketCap",10000).put("executable",true))
  ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->activity.setContent {RallyTheme(false) {Column {
    AssetRow(asset.copy(stale=false),false,{intent.value="Detail"},{intent.value="Buy intent"});Text(intent.value)
   }}}}
   assertTrue(device.wait(Until.hasObject(By.text("QA")),5000));device.findObject(By.text("QA")).click()
   assertTrue(device.wait(Until.hasObject(By.text("Detail")),2000))
   device.findObject(By.desc("Buy QA")).click()
   assertTrue(device.wait(Until.hasObject(By.text("Buy intent")),2000))
  }
 }
}
