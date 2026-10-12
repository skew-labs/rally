package com.rallydot.app

import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.MotionDurationScale
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.Path
import androidx.compose.ui.graphics.StrokeCap
import androidx.compose.ui.graphics.StrokeJoin
import androidx.compose.ui.graphics.drawscope.Stroke
import androidx.compose.ui.graphics.drawscope.withTransform
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.semantics.contentDescription
import androidx.compose.ui.semantics.semantics
import androidx.compose.ui.unit.dp
import org.json.JSONObject
import kotlin.math.abs
import kotlin.math.max

data class PriceTick(val id: Long,val time: Long,val value: Double)
fun mergePriceTicks(previous: List<PriceTick>,data: JSONObject,epoch: String?): List<PriceTick> {
    val reset=data.optBoolean("reset") || epoch!=data.string("epoch")
    val next=if(reset)linkedMapOf<Long,PriceTick>() else previous.associateByTo(linkedMapOf()) { it.id }
    data.objects("points").forEach { row->
        val id=row.optLong("id");val time=row.optLong("time");val value=row.number("value")
        if(id>0 && time>0 && time<=System.currentTimeMillis()/1000+5 && value!=null && value>0 && value.isFinite())next[id]=PriceTick(id,time,value)
    }
    return next.values.sortedBy { it.id }.takeLast(240)
}
fun tickEase(progress: Float): Float { val t=1-progress.coerceIn(0f,1f);return 1-t*t*t }
private class TickBounds { var low=0.0;var range=0.0 }

// Frame-clock progress is read only by the draw phase, not by the order sheet.
// The observed price list remains unchanged while the live edge moves.
@Composable fun LivePriceChart(points: List<PriceTick>,ticks: Boolean,onScrub: (ChartPoint?)->Unit,epoch: String?=null,windowSize: Int=60) {
    val color=Color(0xFF9178FF)
    val progress=remember(epoch) { mutableFloatStateOf(1f) }
    var previous by remember(epoch) { mutableLongStateOf(0) }
    val pointer=remember(epoch) { mutableStateOf<Offset?>(null) }
    val bounds=remember(epoch) { TickBounds() }
    val scrub by rememberUpdatedState(onScrub)
    LaunchedEffect(points.lastOrNull()?.id,ticks,epoch,windowSize) {
        val latest=points.lastOrNull()?.id ?: return@LaunchedEffect
        val animate=previous!=0L && previous!=latest && (coroutineContext[MotionDurationScale]?.scaleFactor ?: 1f)>0
        previous=latest
        if(!animate){progress.floatValue=1f;return@LaunchedEffect}
        progress.floatValue=0f
        val start=withFrameNanos { it }
        while(progress.floatValue<1f)withFrameNanos { frame->progress.floatValue=((frame-start)/220_000_000.0).toFloat().coerceAtMost(1f) }
    }
    Box(Modifier.fillMaxSize().highRefresh().semantics { contentDescription="${if(ticks)"Price ticks" else "Live price line"}, ${minOf(points.size,savedTickWindow(windowSize))} actual observations, last ${savedTickWindow(windowSize)} updates" }.pointerInput(points,ticks,windowSize) {
        detectDragGestures(onDragEnd={pointer.value=null;scrub(null)},onDragCancel={pointer.value=null;scrub(null)}) { change,_->
            change.consume();pointer.value=change.position;progress.floatValue=1f
            if(points.isNotEmpty()){
                val visible=points.takeLast(savedTickWindow(windowSize));val last=visible.last();val duration=max(30L,last.time-visible.first().time);val count=max(12,visible.size-1)
                val fraction=change.position.x/size.width
                val point=visible.minBy { p->val x=if(ticks)1-(visible.lastIndex-visible.indexOf(p)).toDouble()/count else 1-(last.time-p.time).toDouble()/duration;abs(x-fraction) }
                scrub(ChartPoint(point.time,point.value.toFloat()))
            }
        }
    }.drawWithCache {
        val visible=points.takeLast(savedTickWindow(windowSize))
        if(visible.isEmpty())return@drawWithCache onDrawBehind { }
        val minimum=visible.minOf { it.value };val high=visible.maxOf { it.value };val range=max(high-minimum,max(high*.0005,1e-9));val low=(minimum+high-range)/2
        val duration=max(30L,visible.last().time-visible.first().time);val count=max(12,visible.size-1)
        val pad=18.dp.toPx();val width=(size.width-18.dp.toPx()).coerceAtLeast(1f)
        val oldRange=bounds.range;val sy=if(oldRange>0)(range/oldRange).toFloat() else 1f
        val ty=if(oldRange>0)(size.height-pad)*(1-sy)-((low-bounds.low)/oldRange).toFloat()*(size.height-pad*2) else 0f
        bounds.low=low;bounds.range=range
        val offsets=visible.mapIndexed { i,p->Offset((if(ticks)1-(visible.lastIndex-i).toDouble()/count else 1-(visible.last().time-p.time).toDouble()/duration).toFloat()*width,size.height-pad-((p.value-low)/range).toFloat()*(size.height-pad*2).coerceAtLeast(1f)) }
        val path=Path().apply { offsets.dropLast(1).forEachIndexed { i,p->if(i==0)moveTo(p.x,p.y) else lineTo(p.x,p.y) } }
        val tip=offsets.last();val from=offsets.getOrElse(offsets.lastIndex-1) { tip };val shift=(tip.x-from.x).coerceAtLeast(0f)
        val stroke=Stroke(width=2.dp.toPx(),cap=StrokeCap.Round,join=StrokeJoin.Round)
        onDrawBehind {
            val p=tickEase(progress.floatValue);val dx=(1-p)*shift
            val end=Offset(from.x+(tip.x-from.x)*p,from.y+(tip.y-from.y)*p)
            withTransform({translate(dx,(1-p)*ty);scale(1f,sy+(1-sy)*p,pivot=Offset.Zero)}) {
                drawPath(path,color,style=stroke)
                drawLine(color,from,end,2.dp.toPx(),cap=StrokeCap.Round)
                drawCircle(color.copy(alpha=.12f),7.dp.toPx(),end);drawCircle(color,3.dp.toPx(),end)
            }
            pointer.value?.let { point->drawLine(color.copy(alpha=.3f),Offset(point.x,0f),Offset(point.x,size.height),1.dp.toPx()) }
        }
    })
}
