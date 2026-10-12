package com.rallydot.app

// Absent or invalid preferences always open a historical line.
fun savedChartMode(value: String?,candles: Boolean=true): String = when(value) {
    "Live","Ticks","History" -> value
    "1h" -> if(candles)"1h" else "History"
    else -> "History"
}
fun savedTickWindow(value: Int): Int = if(value in listOf(30,60,120))value else 60
