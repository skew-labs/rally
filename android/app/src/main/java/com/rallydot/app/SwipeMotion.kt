package com.rallydot.app

import androidx.compose.animation.core.*
import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.pager.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.input.pointer.util.VelocityTracker
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.*
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.*
import kotlin.math.abs

/** A swipe changes the viewed card only; it never submits an order. */
fun swipeTargetPage(current: Int,count: Int,distance: Float,width: Float,velocity: Float): Int {
    if(count<=0 || width<=0f || !distance.isFinite() || !velocity.isFinite())return current
    val travelled=abs(distance)/width
    val fling=travelled>=.06f && abs(velocity)>=1000f && distance*velocity>0f
    if(travelled<.22f && !fling)return current
    return (current+if(distance<0f)1 else -1).coerceIn(0,count-1)
}

@Composable fun NativeSwipeDeck(keys: List<String>,modifier: Modifier=Modifier,onPage: (Int)->Unit={},content: @Composable (Int)->Unit) {
    val pager=rememberPagerState(pageCount={keys.size})
    val scope=rememberCoroutineScope()
    val haptic=LocalHapticFeedback.current
    val horizontal=remember { Animatable(0f) }
    val drag=remember { mutableFloatStateOf(0f) }
    val dragging=remember { mutableStateOf(false) }
    var settling by remember { mutableStateOf(false) }
    var job by remember { mutableStateOf<Job?>(null) }
    val count by rememberUpdatedState(keys.size)
    val pageCallback by rememberUpdatedState(onPage)
    DisposableEffect(Unit) { onDispose { job?.cancel() } }
    LaunchedEffect(pager) {
        var previous=pager.settledPage
        snapshotFlow { pager.settledPage }.collect { index->
            if(previous!=index)haptic.performHapticFeedback(HapticFeedbackType.SegmentTick)
            previous=index;pageCallback(index)
        }
    }
    Column(modifier.fillMaxWidth()) {
    VerticalPager(pager,Modifier.weight(1f).fillMaxWidth().highRefresh(),beyondViewportPageCount=1,
        contentPadding=PaddingValues(horizontal=12.dp,vertical=8.dp),pageSpacing=12.dp,key={keys[it]}) { index->
        Surface(Modifier.fillMaxSize().highRefresh().semantics { if(index!=pager.currentPage)hideFromAccessibility() }.graphicsLayer {
            // Drag and spring values are read in the render phase, not in card composition.
            translationX=if(dragging.value)drag.floatValue else horizontal.value
            val distance=abs(pager.currentPage-index+pager.currentPageOffsetFraction).coerceIn(0f,1f)
            scaleX=1f-distance*.015f;scaleY=scaleX;alpha=1f-distance*.08f
        }.pointerInput(pager) {
            val tracker=VelocityTracker()
            var captured=false
            fun settle(cancel: Boolean) {
                if(!captured)return
                captured=false
                val distance=drag.floatValue
                val width=size.width.toFloat()
                val velocity=tracker.calculateVelocity().x
                val next=if(cancel)pager.currentPage else swipeTargetPage(pager.currentPage,count,distance,width,velocity)
                dragging.value=false;settling=true
                job=scope.launch {
                    try {
                        horizontal.snapTo(distance)
                        if(next!=pager.currentPage) {
                            val direction=if(next>pager.currentPage)-1f else 1f
                            horizontal.animateTo(direction*width,tween(120,easing=FastOutLinearInEasing))
                            pager.scrollToPage(next)
                            horizontal.snapTo(-direction*width)
                            horizontal.animateTo(0f,tween(180,easing=FastOutSlowInEasing))
                        } else horizontal.animateTo(0f,spring(dampingRatio=1f,stiffness=800f))
                    } finally { horizontal.snapTo(0f);drag.floatValue=0f;settling=false }
                }
            }
            detectHorizontalDragGestures(onDragStart={
                captured=!settling && !pager.isScrollInProgress
                if(captured) { tracker.resetTracking();drag.floatValue=0f;dragging.value=true }
            },onDragCancel={settle(true)},onDragEnd={settle(false)}) { change,delta->
                if(captured) {
                    tracker.addPosition(change.uptimeMillis,change.position)
                    change.consume()
                    val candidate=drag.floatValue+delta
                    val edge=(pager.currentPage==0 && candidate>0) || (pager.currentPage==count-1 && candidate<0)
                    drag.floatValue=(drag.floatValue+delta*if(edge).25f else 1f).coerceIn(-size.width.toFloat(),size.width.toFloat())
                }
            }
        },shape=RoundedCornerShape(24.dp),border=BorderStroke(1.dp,MaterialTheme.colorScheme.outlineVariant),color=MaterialTheme.colorScheme.surface) {
            content(index)
        }
    }
    Row(Modifier.fillMaxWidth().heightIn(min=48.dp).padding(horizontal=20.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.SpaceBetween) {
        IconButton(onClick={scope.launch { pager.animateScrollToPage((pager.currentPage-1).coerceAtLeast(0)) }},enabled=pager.currentPage>0 && !settling && !pager.isScrollInProgress){Icon(Icons.Outlined.ArrowBack,"Previous card")}
        Text("${pager.currentPage+1} / ${keys.size}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        IconButton(onClick={scope.launch { pager.animateScrollToPage((pager.currentPage+1).coerceAtMost(keys.lastIndex)) }},enabled=pager.currentPage<keys.lastIndex && !settling && !pager.isScrollInProgress){Icon(Icons.Outlined.ArrowForward,"Next card")}
    }
    }
}
