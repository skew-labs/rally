package com.rallydot.app

import androidx.compose.material3.Surface
import androidx.activity.compose.setContent
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import org.junit.Assert.*
import org.junit.Test
import java.io.File

class LoginLayoutTest {
    @Test fun loginControlsFitAndEmailExpandsWithoutBrowserHandoff() {
        val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
        val dark=InstrumentationRegistry.getArguments().getString("theme")=="dark"
        ActivityScenario.launch(RallyActivity::class.java).use { scenario->
            scenario.onActivity { activity->
                val vm=RallyViewModel(activity.application)
                activity.setContent { RallyTheme(dark) { Surface { WalletLoginSheet(vm,{}, {throw AssertionError("No browser handoff in layout test")}) } } }
            }
            assertTrue(device.wait(Until.hasObject(By.text("Continue with Google")),15000))
            for(label in listOf("Continue with Google","Connect wallet","Continue with email")) {
                var node=device.findObject(By.text(label))
                if(node==null) { device.findObject(By.scrollable(true))?.scroll(Direction.DOWN,1f);node=device.findObject(By.text(label)) }
                assertNotNull("Missing $label",node)
                val b=node!!.visibleBounds
                assertTrue("Clipped $label: $b",b.width()>0 && b.height()>0 && b.left>=0 && b.top>=0 && b.right<=device.displayWidth && b.bottom<=device.displayHeight)
            }
            device.findObject(By.text("Continue with email")).click()
            assertTrue(device.wait(Until.hasObject(By.clazz("android.widget.EditText")),5000))
            val folder=inst.targetContext.getExternalFilesDir(null)
            device.takeScreenshot(File(folder,"login-layout.png"));device.dumpWindowHierarchy(File(folder,"login-layout.xml"))
        }
    }
}
