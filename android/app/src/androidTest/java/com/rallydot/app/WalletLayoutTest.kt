package com.rallydot.app
import androidx.activity.compose.setContent
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import org.json.JSONObject
import org.junit.Test
import org.junit.Assert.*
import java.io.File
class WalletLayoutTest {
 @Test fun walletControlsFitVisibleWindow() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
  val mode=InstrumentationRegistry.getArguments().getString("mode") ?: "profile"
  val dark=InstrumentationRegistry.getArguments().getString("theme")=="dark"
  val token=JSONObject().put("id","MON").put("symbol","MON").put("name","Monad").put("decimals",18).put("logoURI","/assets/MON.png")
  val h=JSONObject().put("asset","MON").put("amount","12.34").put("token",token).put("valueUSD","24.68")
  val p=JSONObject().put("holdings",org.json.JSONArray().put(h)).put("refreshing",false).put("valuation",JSONObject().put("valueUSD","24.68").put("change24hPercent","2"))
  val state=AppState(boot=JSONObject().put("wallet","0x"+"1".repeat(40)),portfolio=p)
  ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->activity.setContent { RallyTheme(dark) { Surface { if(mode=="profile")Column(Modifier.fillMaxSize().padding(24.dp)) { WalletBalanceHero(state,{},{}) } else WalletAssetsSheet(state,if(mode=="keyboard")"send" else mode,{},{_,_,_->throw AssertionError("No financial action")},{}) } } } }
   val label=if(mode=="deposit")"Copy address" else "Send"
   val ready=device.wait(Until.hasObject(By.text(label)),15000)
   if(!ready) { device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"wallet-layout-failure.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"wallet-layout-failure.xml")) }
   assertTrue("Missing $label in $mode",ready)
   if(mode=="keyboard") {
    val inputs=device.findObjects(By.clazz("android.widget.EditText"));assertTrue(inputs.isNotEmpty());inputs.last().click();inputs.last().text="0.01";Thread.sleep(900)
   } else Thread.sleep(800)
   val node=device.findObjects(By.text(label)).last();val b=node.visibleBounds
   assertTrue("Footer clipped: $b",b.width()>0 && b.height()>0 && b.left>=0 && b.top>=0 && b.right<=device.displayWidth && b.bottom<=device.displayHeight)
   if(mode=="profile")assertNotNull(device.findObject(By.text("$24.68")))
   val file=File(inst.targetContext.getExternalFilesDir(null),"wallet-layout.png")
   device.takeScreenshot(file)
   device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"wallet-layout.xml"))
  }
 }
}
