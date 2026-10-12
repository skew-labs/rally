package com.rallydot.app

import org.junit.Assert.*
import org.junit.Test

class ChartSettingsTest {
    @Test fun defaultsToLineAndRetainsExplicitChoices() {
        assertEquals("History",savedChartMode(null))
        assertEquals("History",savedChartMode("invalid"))
        listOf("History","Live","Ticks","1h").forEach { assertEquals(it,savedChartMode(it)) }
        assertEquals("History",savedChartMode("1h",false))
    }
    @Test fun tickWindowsAreBounded() {
        listOf(30,60,120).forEach { assertEquals(it,savedTickWindow(it)) }
        listOf(-1,0,1,Int.MAX_VALUE).forEach { assertEquals(60,savedTickWindow(it)) }
    }
}
