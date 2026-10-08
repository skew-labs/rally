package com.rallydot.app

import android.net.Uri
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.pager.*
import androidx.compose.foundation.shape.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.*
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.*
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import coil.compose.AsyncImage
import kotlinx.coroutines.*
import org.json.JSONObject
import kotlin.math.abs

@Composable fun SwipeScreen(vm: RallyViewModel,onAsset: (Asset)->Unit,onPost: (Post)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    var mode by rememberSaveable { mutableStateOf("Spot") }
    val feed=state.boot?.string("activeFeed","latest") ?: "latest"
    val pageKey="social-swipe:$mode:$feed"
    val path=when(mode) { "Perps"->"/api/perps";"Prediction"->"/api/predictions";else->"/api/posts?mode=for-you&feed="+Uri.encode(feed) }
    val field=when(mode) { "Perps"->"markets";"Prediction"->"pools";else->"posts" }
    val page=state.pages[pageKey] ?: Page(loading=true)
    LaunchedEffect(pageKey) { if(mode!="Memes")vm.load(pageKey,path,field) }
    val lifecycle=androidx.lifecycle.compose.LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(pageKey,lifecycle) { lifecycle.repeatOnLifecycle(androidx.lifecycle.Lifecycle.State.STARTED) { while(mode!="Memes") { delay(30000);vm.load(pageKey,path,field,true,retain=true) } } }
    Column(Modifier.fillMaxSize()) {
        Segmented(listOf("Spot","Perps","Prediction","Memes"),mode,{mode=it},Modifier.padding(horizontal=12.dp,vertical=4.dp))
        if(mode=="Memes")NadSwipeScreen(vm,onAsset)
        else if(page.items.isEmpty()) { if(page.loading)LoadingRows() else EmptyState("No ${if(mode=="Spot")"posts" else "markets"} yet",page.error,"Retry",{vm.load(pageKey,path,field,true)}) }
        else key(pageKey) {
            val keys=remember(page.items) { page.items.map { if(mode=="Spot")it.string("id") else Asset.parse(it,if(mode=="Perps")"perps" else "prediction").key } }
            NativeSwipeDeck(keys,Modifier.weight(1f),onPage={i->if(i>=page.items.size-3 && page.cursor!=null && !page.loading)vm.load(pageKey,path+"&cursor="+Uri.encode(page.cursor),field,append=true)}) { index->
                SocialSwipeCard(page.items[index],mode,index,page.items.size,vm,onAsset,onPost)
            }
        }
    }
}

@Composable private fun NativeSwipeDeck(keys: List<String>,modifier: Modifier,onPage: (Int)->Unit,content: @Composable (Int)->Unit) {
    val pager=rememberPagerState(pageCount={keys.size});val scope=rememberCoroutineScope();val haptic=LocalHapticFeedback.current
    val horizontal=remember { Animatable(0f) };var drag by remember { mutableFloatStateOf(0f) };var dragging by remember { mutableStateOf(false) };var settling by remember { mutableStateOf(false) };var job by remember { mutableStateOf<Job?>(null) }
    val count by rememberUpdatedState(keys.size);val pageCallback by rememberUpdatedState(onPage)
    DisposableEffect(Unit) { onDispose { job?.cancel() } }
    LaunchedEffect(pager) { var previous=pager.settledPage;snapshotFlow { pager.settledPage }.collect { i->if(previous!=i)haptic.performHapticFeedback(HapticFeedbackType.SegmentTick);previous=i;pageCallback(i) } }
    VerticalPager(pager,modifier.fillMaxWidth().highRefresh(),beyondViewportPageCount=1,contentPadding=PaddingValues(horizontal=12.dp,vertical=8.dp),pageSpacing=12.dp,key={keys[it]}) { index->
        Surface(Modifier.fillMaxSize().highRefresh().semantics { if(index!=pager.currentPage)hideFromAccessibility() }.graphicsLayer {
            translationX=if(dragging)drag else horizontal.value
            val distance=abs(pager.currentPage-index+pager.currentPageOffsetFraction).coerceIn(0f,1f)
            scaleX=1f-distance*.02f;scaleY=scaleX;alpha=1f-distance*.10f
        }.pointerInput(pager) {
            var captured=false
            fun settle(cancel: Boolean) {
                if(!captured)return;captured=false;val distance=drag;val width=size.width.toFloat();dragging=false;settling=true
                job=scope.launch {
                    try {
                        horizontal.snapTo(distance);val next=(pager.currentPage+if(distance<0)1 else -1).coerceIn(0,count-1)
                        if(!cancel && abs(distance)>72.dp.toPx() && next!=pager.currentPage) {
                            val direction=if(distance<0)-1f else 1f;horizontal.animateTo(direction*width,tween(120,easing=FastOutLinearInEasing));pager.scrollToPage(next);horizontal.snapTo(-direction*width);horizontal.animateTo(0f,tween(160,easing=LinearOutSlowInEasing))
                        } else horizontal.animateTo(0f,spring(dampingRatio=1f,stiffness=700f))
                    } finally { horizontal.snapTo(0f);drag=0f;settling=false }
                }
            }
            detectHorizontalDragGestures(onDragStart={captured=!settling && !pager.isScrollInProgress;if(captured){drag=0f;dragging=true}},onDragCancel={settle(true)},onDragEnd={settle(false)}) { change,delta->if(captured){change.consume();drag=(drag+delta).coerceIn(-size.width.toFloat(),size.width.toFloat())} }
        },shape=RoundedCornerShape(24.dp),border=BorderStroke(1.dp,MaterialTheme.colorScheme.outlineVariant),color=MaterialTheme.colorScheme.surface) { content(index) }
    }
}

@Composable private fun SocialSwipeCard(item: JSONObject,mode: String,index: Int,total: Int,vm: RallyViewModel,onAsset: (Asset)->Unit,onPost: (Post)->Unit) {
    val post=remember(item,mode) { if(mode=="Spot")Post.parse(item) else null }
    val fixed=remember(item,mode) { if(post==null)Asset.parse(item,if(mode=="Perps")"perps" else "prediction") else null }
    val asset by produceState<Asset?>(fixed,item,mode) { value=fixed;if(post!=null && post.asset.isNotBlank())try { value=vm.resolveAsset(post.asset) } catch(e:CancellationException){throw e} catch(_:Exception){value=null} }
    LaunchedEffect(asset?.key) { asset?.let(vm::warmChart) }
    BoxWithConstraints(Modifier.fillMaxSize()) {
        if(maxHeight<320.dp) {
            Row(Modifier.fillMaxSize().padding(14.dp),horizontalArrangement=Arrangement.spacedBy(16.dp)) {
                Column(Modifier.weight(1f).fillMaxHeight(),verticalArrangement=Arrangement.spacedBy(6.dp)) {
                    Text(post?.author?.name ?: fixed?.symbol.orEmpty(),fontWeight=FontWeight.Medium,maxLines=1)
                    Text(post?.text ?: if(mode=="Prediction")"Price prediction · Pool #${item.string("id")}" else "${fixed?.venue} · Perpetual",Modifier.weight(1f).then(if(post!=null)Modifier.clickable { onPost(post) } else Modifier),maxLines=3,overflow=TextOverflow.Ellipsis,style=MaterialTheme.typography.bodyMedium)
                    Text("${index+1} / $total",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
                Column(Modifier.weight(1f).fillMaxHeight(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    asset?.let { a->
                        Row(verticalAlignment=Alignment.CenterVertically) { Artwork(a.image,a.symbol,28.dp);Column(Modifier.padding(start=8.dp)) { Text(a.symbol,maxLines=1,fontWeight=FontWeight.SemiBold);Text(money(a.price),style=MaterialTheme.typography.bodySmall) } }
                        Spacer(Modifier.weight(1f))
                        if(mode=="Prediction")Button(onClick={onAsset(a)},enabled=a.executable,modifier=Modifier.fillMaxWidth(),shape=RoundedCornerShape(100.dp)) { Text("Predict price",maxLines=1) }
                        else TradeButtons(if(mode=="Perps")"Long" else "Buy",if(mode=="Perps")"Short" else "Sell",{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","buy")))},{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","sell")))},a.executable)
                    } ?: post?.let { Spacer(Modifier.weight(1f));Button(onClick={onPost(it)},shape=RoundedCornerShape(100.dp)) { Text("Discuss") } }
                }
            }
        } else {
        val short=maxHeight<420.dp || androidx.compose.ui.platform.LocalDensity.current.fontScale>1.3f
        Column(Modifier.fillMaxSize().padding(if(short)14.dp else 18.dp),verticalArrangement=Arrangement.spacedBy(if(short)8.dp else 14.dp)) {
            if(post!=null) {
                Row(verticalAlignment=Alignment.CenterVertically) { Artwork(post.author.image,post.author.name,36.dp);Column(Modifier.weight(1f).padding(start=10.dp)) { Text(post.author.name,style=MaterialTheme.typography.titleSmall,maxLines=1,overflow=TextOverflow.Ellipsis);Text("@${post.author.handle} · ${age(post.created)}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis) };if(post.author.agent)Text("Agent",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                Text(post.text,Modifier.clickable { onPost(post) },maxLines=if(short)3 else if(post.media!=null)4 else 7,overflow=TextOverflow.Ellipsis,style=MaterialTheme.typography.bodyLarge)
                if(!short && post.media!=null) { val media=post.media;val poster=safeImage(media.string("poster",media.string("url")));if(poster!=null)AsyncImage(poster,"Post media",Modifier.fillMaxWidth().weight(1f).clip(RoundedCornerShape(16.dp)).clickable { onPost(post) },contentScale=androidx.compose.ui.layout.ContentScale.Fit) else Spacer(Modifier.weight(1f)) }
                else Spacer(Modifier.weight(1f))
                if(!short)TextButton(onClick={onPost(post)},contentPadding=PaddingValues(0.dp)) { Text("Read more",color=MaterialTheme.colorScheme.onSurfaceVariant,fontSize=12.sp) }
            } else {
                Text(if(mode=="Prediction")"Price prediction" else "Perpetual",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                fixed?.let { a->Row(verticalAlignment=Alignment.CenterVertically) { Artwork(a.heroImage,a.symbol,if(short)44.dp else 64.dp);Text(a.symbol,Modifier.padding(start=14.dp),fontSize=if(short)22.sp else 30.sp,fontWeight=FontWeight.SemiBold) };Text(money(a.price),fontSize=if(short)26.sp else 38.sp,fontWeight=FontWeight.Medium) }
                Spacer(Modifier.weight(1f))
                if(mode=="Prediction") { Fact("Pool", "#"+item.string("id"));Fact("Entry stake",item.string("stake")+" "+item.string("stakeAsset"));Fact("Status",item.string("state").replace('_',' ')) }
            }
            val a=asset
            if(a!=null) {
                HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
                Row(verticalAlignment=Alignment.CenterVertically) { Artwork(a.image,a.symbol,32.dp);Column(Modifier.weight(1f).padding(start=10.dp)) { Text(a.symbol,fontWeight=FontWeight.SemiBold,fontSize=14.sp);Text(a.venue,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) };Column(horizontalAlignment=Alignment.End) { Text(if(a.raw.optBoolean("nadfun") && a.cap!=null)"$"+compact(a.cap) else money(a.price),fontWeight=FontWeight.Medium,fontSize=15.sp);Text(if(a.freshness)"Last known" else if(a.raw.optBoolean("nadfun"))"Market cap" else "Reference price",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) } }
                if(mode=="Prediction")Button(onClick={onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","buy")))},enabled=a.executable,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=Buy,contentColor=Color.White)) { Text(if(a.executable)"Predict price" else item.string("state").replace('_',' ')) }
                else TradeButtons(if(mode=="Perps")"Buy / Long" else "Buy",if(mode=="Perps")"Sell / Short" else "Sell",{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","buy")))},{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","sell")))},a.executable)
            } else if(post!=null)Button(onClick={onPost(post)},Modifier.fillMaxWidth().heightIn(min=52.dp),shape=RoundedCornerShape(100.dp)) { Text("Discuss") }
            Text("${index+1} / $total",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
        }
    }
}
