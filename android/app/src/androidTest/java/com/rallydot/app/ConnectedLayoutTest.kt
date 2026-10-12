package com.rallydot.app
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.Text
import androidx.compose.runtime.*
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.Density
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import org.json.JSONObject
import org.junit.Assert.*
import org.junit.Test

class ConnectedLayoutTest {
 @Test fun algorithmIdentityPriceAndVerifiedBasisRemainReachableAtLargeText() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst);val opened=mutableStateOf(false)
  val feed=JSONObject().put("id","qa").put("name","A long strategy name for a narrow display").put("price","2.50").put("periodDays",30)
  ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->activity.setContent { RallyTheme(false) { CompositionLocalProvider(LocalDensity provides Density(LocalDensity.current.density,1.3f)) { Column { AlgorithmListRow(feed,Person("qa","Creator name","creator",null,false)){opened.value=true};if(opened.value)Text("Preview opened") } } } } }
   assertTrue(device.wait(Until.hasObject(By.text("No verified return")),5000))
   val price=device.findObject(By.text("2.50 USDC / 30d"));assertNotNull(price);assertTrue(price.visibleBounds.right<=device.displayWidth)
   device.findObject(By.text("Creator name")).click();assertTrue(device.wait(Until.hasObject(By.text("Preview opened")),2000))
   device.takeScreenshot(java.io.File(inst.targetContext.getExternalFilesDir(null),"connected-algorithm-large-text.png"))
  }
 }
 @Test fun detailInformationChangesWithoutRecreatingChartState() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst);val selected=mutableStateOf("Holders");var chartMounts=0
  ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->activity.setContent { RallyTheme(true) { Column(Modifier.windowInsetsPadding(WindowInsets.safeDrawing)) { val chart=remember { ++chartMounts };Text("Chart instance $chart");DetailInformationTabs(listOf("Holders","Community","Details"),selected.value,{selected.value=it});Text("Pane: "+selected.value) } } } }
   for(tab in listOf("Community","Details","Holders")){assertTrue(device.wait(Until.hasObject(By.text(tab)),5000));device.findObject(By.text(tab)).click();assertTrue(device.wait(Until.hasObject(By.text("Pane: $tab")),2000));assertNotNull(device.findObject(By.text("Chart instance 1")))}
   assertEquals(1,chartMounts)
  }
 }
}
