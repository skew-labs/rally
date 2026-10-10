package com.rallydot.app
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.rememberScrollState
import androidx.compose.foundation.verticalScroll
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import org.junit.Test
import org.junit.Assert.*
import java.io.File
class PerpLayoutTest {
 @Test fun amountConversionAndActionRemainUsableWithKeyboardAndLargeText() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
  val dark=InstrumentationRegistry.getArguments().getString("theme")=="dark"
  ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->activity.setContent { RallyTheme(dark) { Surface { Column(Modifier.fillMaxSize().windowInsetsPadding(WindowInsets.safeDrawing).imePadding().padding(20.dp)) {
    var value by remember { mutableStateOf("0.3") };var mode by remember { mutableStateOf("quantity") }
    val estimate=perpEstimate(value,mode,"60000",5,5)
    Column(Modifier.weight(1f).verticalScroll(rememberScrollState())) { PerpPositionInput(value,mode,"BTC",estimate,Buy,true,{value=it},{next->if(estimate.valid)value=if(next=="usd")estimate.notional else estimate.quantity;mode=next},{}) }
    Button(onClick={throw AssertionError("No financial action")},enabled=estimate.valid,modifier=Modifier.fillMaxWidth().heightIn(min=54.dp)) { Text("Buy / Long") }
   } } } } }
   assertTrue(device.wait(Until.hasObject(By.text("≈ $18,000.00")),15000))
   device.findObject(By.text("USD")).click()
   assertTrue(device.wait(Until.hasObject(By.text("≈ 0.3 BTC")),5000))
   val input=device.findObject(By.desc("Position size"));assertNotNull(input);input.click();device.pressKeyCode(android.view.KeyEvent.KEYCODE_A,android.view.KeyEvent.META_CTRL_ON);device.executeShellCommand("input text 10")
   assertTrue(device.wait(Until.hasObject(By.text("≈ 0.00016 BTC · Rounded down")),5000))
   Thread.sleep(500)
   val buy=device.findObject(By.text("Buy / Long"));assertNotNull(buy);val b=buy.visibleBounds
   assertTrue("Buy clipped with keyboard: $b",b.width()>0 && b.height()>0 && b.left>=0 && b.top>=0 && b.right<=device.displayWidth && b.bottom<=device.displayHeight)
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"perp-layout.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"perp-layout.xml"))
  }
 }
}
