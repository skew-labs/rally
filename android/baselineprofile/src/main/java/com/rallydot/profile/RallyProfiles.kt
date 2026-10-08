package com.rallydot.profile

import androidx.benchmark.macro.junit4.BaselineProfileRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.uiautomator.By
import androidx.test.uiautomator.Until
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class RallyProfiles {
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
        device.findObject(By.text("MOE")).click()
        check(device.wait(Until.hasObject(By.desc("Close token")),10000))
        device.findObject(By.text("Buy")).click()
        check(device.wait(Until.hasObject(By.text("Amount")),10000))
        device.findObject(By.desc("Close token")).click()
        device.waitForIdle()
        val width=device.displayWidth;val height=device.displayHeight
        device.swipe(width/2,height*3/4,width/2,height/3,40)
        device.findObject(By.text("Swipe")).click()
        check(device.wait(Until.hasObject(By.text("Buy")),10000))
        device.waitForIdle()
        device.swipe(width/2,height*3/4,width/2,height/3,40)
        device.waitForIdle()
        device.findObject(By.text("Discover")).click()
        check(device.wait(Until.hasObject(By.text("Search people, tokens, algorithms")),10000))
        device.findObject(By.text("Profile")).click()
        device.waitForIdle()
        // Only public reads and sheet presentation; never submit a wallet request.
    }
}
