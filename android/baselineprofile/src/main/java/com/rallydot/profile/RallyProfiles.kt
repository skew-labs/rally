package com.rallydot.profile

import androidx.benchmark.macro.junit4.BaselineProfileRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.BySelector
import androidx.test.uiautomator.StaleObjectException
import androidx.test.uiautomator.UiDevice
import androidx.test.uiautomator.Until
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RallyProfiles {
    private fun UiDevice.tapCurrent(selector: BySelector) {
        repeat(3) {
            val node=wait(Until.findObject(selector),10000) ?: error("Control not visible: $selector")
            try {
                val bounds=node.visibleBounds
                check(click(bounds.centerX(),bounds.centerY()))
                waitForIdle()
                return
            } catch(_: StaleObjectException) {
                // Navigation and public data updates can replace an accessibility node.
            }
        }
        error("Control kept changing: $selector")
    }
    @get:Rule val profile=BaselineProfileRule()
    @Test fun startup()=profile.collect(packageName="com.rallydot.app",includeInStartupProfile=true,maxIterations=5,stableIterations=2) {
        pressHome();startActivityAndWait()
        check(device.wait(Until.hasObject(By.text("Asset")),20000)) { "Market content did not load" }
        device.waitForIdle()
    }
    @Test fun browseAndTradeSheet()=profile.collect(packageName="com.rallydot.app",maxIterations=5,stableIterations=2) {
        pressHome();startActivityAndWait()
        check(device.wait(Until.hasObject(By.text("Asset")),20000))
        check(device.wait(Until.hasObject(By.text("MOE")),20000))
        device.tapCurrent(By.text("MOE"))
        check(device.wait(Until.hasObject(By.desc("Close token")),10000))
        device.tapCurrent(By.text("Buy"))
        check(device.wait(Until.hasObject(By.text("You pay")),10000))
        device.tapCurrent(By.desc("Close token"))
        device.waitForIdle()
        val width=device.displayWidth;val height=device.displayHeight
        device.swipe(width/2,height*3/4,width/2,height/3,40)
        device.tapCurrent(By.text("Swipe"))
        check(device.wait(Until.hasObject(By.text("Spot")),10000))
        device.waitForIdle()
        device.swipe(width/2,height*3/4,width/2,height/3,40)
        device.waitForIdle()
        device.tapCurrent(By.text("Memes"))
        check(device.wait(Until.hasObject(By.text("Buy")),10000))
        device.waitForIdle()
        device.swipe(width/2,height*3/4,width/2,height/3,40)
        device.waitForIdle()
        device.tapCurrent(By.desc("Discover"))
        check(device.wait(Until.hasObject(By.text("Search people, posts, algorithms")),10000))
        device.tapCurrent(By.desc("Profile"))
        device.waitForIdle()
        // Only public reads and sheet presentation; never submit a wallet request.
    }
}
