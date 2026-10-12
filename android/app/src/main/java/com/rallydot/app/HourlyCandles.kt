package com.rallydot.app

import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.gestures.detectTapGestures
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.geometry.Rect
import androidx.compose.ui.graphics.*
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.compose.ui.text.TextStyle
import androidx.compose.ui.text.drawText
import androidx.compose.ui.text.rememberTextMeasurer
import androidx.compose.ui.platform.LocalDensity
import org.json.JSONObject
import kotlin.math.*

data class HourCandle(val time: Long,val open: Double,val high: Double,val low: Double,val close: Double)
fun hourlyCandles(data: JSONObject): List<HourCandle> {
    if(data.string("interval")!="1h")return emptyList()
    val end=System.currentTimeMillis()/1000
    return data.objects("candles").mapNotNull {
        val t=it.optLong("time");val o=it.number("open");val h=it.number("high");val l=it.number("low");val c=it.number("close")
        if(t<=0 || t>end || t%3600L!=0L || listOf(o,h,l,c).any { v->v==null||!v.isFinite()||v<=0 })null
        else if(l!!>min(o!!,c!!) || h!!<max(o,c) || l>h)null else HourCandle(t,o,h,l,c)
    }.associateBy { it.time }.toSortedMap().values.toList().takeLast(721)
}

/** Only geometry is cached. Bars remain provider OHLC, including gaps. */
@Composable fun HourlyCandleChart(bars: List<HourCandle>,onSelect: (HourCandle?)->Unit) {
    if(bars.isEmpty())return
    val textMeasurer=rememberTextMeasurer()
    val axisWidth=with(LocalDensity.current){68.dp.toPx()}
    var back by remember { mutableFloatStateOf(0f) }
    val select by rememberUpdatedState(onSelect)
    val visible=remember(bars,back) {
        val end=(bars.size-back.toInt()).coerceIn(min(1,bars.size),bars.size)
        bars.subList((end-48).coerceAtLeast(0),end)
    }
    val accent=MaterialTheme.colorScheme.onSurfaceVariant
    val start=visible.first().time;val span=(visible.last().time-start+3600).coerceAtLeast(3600)
    fun stamp(time: Long)=java.text.SimpleDateFormat("MMM d HH:mm",java.util.Locale.US).format(java.util.Date(time*1000))
    Column(Modifier.fillMaxSize()) {
        Box(Modifier.fillMaxWidth().weight(1f).highRefresh()
            .semantics { contentDescription="1 hour candlestick chart, ${visible.size} candles. Swipe for earlier hours; tap for OHLC." }
            .pointerInput(bars.size) {
                detectHorizontalDragGestures { change,amount->change.consume();back=(back+amount/size.width*48).coerceIn(0f,(bars.size-1).coerceAtLeast(0).toFloat());select(null) }
            }.pointerInput(visible) {
                detectTapGestures { p->val t=start+(p.x/(size.width-axisWidth).coerceAtLeast(1f)*span).toLong();select(visible.minByOrNull { abs(it.time+1800-t) }) }
            }.drawWithCache {
                val low=visible.minOf { it.low };val high=visible.maxOf { it.high };val range=max(high-low,abs(high)*.0001)
                val plotWidth=(size.width-axisWidth).coerceAtLeast(1f)
                val pad=10.dp.toPx();val width=(plotWidth*3600/span*.65f).coerceIn(1f,14.dp.toPx())
                fun y(v: Double)=(size.height-pad-((v-low)/range)*(size.height-pad*2)).toFloat()
                val upWick=Path();val downWick=Path();val upBody=Path();val downBody=Path()
                for(b in visible){
                    val x=((b.time-start+1800).toDouble()/span*plotWidth).toFloat()
                    val wick=if(b.close>=b.open)upWick else downWick;val body=if(b.close>=b.open)upBody else downBody
                    wick.moveTo(x,y(b.high));wick.lineTo(x,y(b.low))
                    val top=min(y(b.open),y(b.close));val bottom=max(y(b.open),y(b.close))
                    body.addRect(Rect(x-width/2,top,x+width/2,max(bottom,top+1.dp.toPx())))
                }
                val ticks=listOf(high,(high+low)/2,low).map { value->
                    val label=money(value).removePrefix("$")
                    Triple(y(value),textMeasurer.measure(label,TextStyle(color=accent,fontSize=10.sp)),value)
                }
                val lastY=y(visible.last().close)
                onDrawBehind {
                    ticks.forEach { (level,label,_)->
                        drawLine(accent.copy(alpha=.1f),Offset(0f,level),Offset(plotWidth,level),1.dp.toPx())
                        drawText(label,topLeft=Offset(plotWidth+8.dp.toPx(),(level-label.size.height/2).coerceIn(0f,(size.height-label.size.height).coerceAtLeast(0f))))
                    }
                    drawLine(accent.copy(alpha=.3f),Offset(0f,lastY),Offset(plotWidth,lastY),1.dp.toPx(),pathEffect=PathEffect.dashPathEffect(floatArrayOf(4.dp.toPx(),4.dp.toPx())))
                    drawPath(upWick,Buy,style=Stroke(1.dp.toPx()));drawPath(downWick,Sell,style=Stroke(1.dp.toPx()))
                    drawPath(upBody,Buy);drawPath(downBody,Sell)
                }
            })
        Row(Modifier.fillMaxWidth().padding(top=6.dp),horizontalArrangement=Arrangement.SpaceBetween) {
            Text(stamp(visible.first().time),style=MaterialTheme.typography.labelSmall,color=accent)
            Text(stamp(visible.last().time),style=MaterialTheme.typography.labelSmall,color=accent)
        }
    }
}
