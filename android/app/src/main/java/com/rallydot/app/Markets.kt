package com.rallydot.app

import android.net.Uri
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.gestures.detectDragGestures
import androidx.compose.foundation.gestures.detectHorizontalDragGestures
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.pager.*
import androidx.compose.foundation.shape.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.draw.clipToBounds
import androidx.compose.ui.*
import androidx.compose.ui.draw.clip
import androidx.compose.ui.draw.drawWithCache
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.activity.compose.ReportDrawnWhen
import androidx.compose.ui.geometry.Offset
import androidx.compose.ui.graphics.*
import androidx.compose.ui.input.pointer.pointerInput
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.repeatOnLifecycle
import kotlinx.coroutines.*
import org.json.JSONObject
import kotlin.math.abs

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun MarketsScreen(vm: RallyViewModel,onAsset: (Asset)->Unit,launch: Boolean=false,create: ()->Unit={},initialCategory: String="Memes",overview: (@Composable ()->Unit)?=null) {
    val state by vm.state.collectAsStateWithLifecycle()
    var category by rememberSaveable(initialCategory) { mutableStateOf(initialCategory) }
    var query by rememberSaveable { mutableStateOf("") }
    var applied by rememberSaveable { mutableStateOf("") }
    val field=when { launch->"tokens";category=="Perps"->"markets";category=="Prediction"->"pools";else->"tokens" }
    val path=when { launch->"/api/launchpad/tokens?limit=24&query="+Uri.encode(applied);category=="Memes"->"/api/nadfun/tokens?sort=cap&limit=24&query="+Uri.encode(applied);category=="Spot"->"/api/market-catalog?limit=40&query="+Uri.encode(applied);category=="Perps"->"/api/perps";else->"/api/predictions" }
    val key="markets:$launch:$category:$applied"
    val page=state.pages[key] ?: Page(loading=true)
    val kind=when(category){"Perps"->"perps";"Prediction"->"prediction";else->"spot"}
    val assets=remember(page.items,query,kind) { page.items.map { Asset.parse(it,kind) }.filter { query.isBlank() || it.name.contains(query,true) || it.symbol.contains(query,true) || it.id.contains(query,true) } }
    LaunchedEffect(query) { delay(280);applied=query.trim() }
    LaunchedEffect(key) { vm.load(key,path,field) }
    LaunchedEffect(key,assets.firstOrNull()?.key) { assets.take(2).filter { it.kind=="spot" }.forEach(vm::warmChart) }
    val lifecycle=androidx.lifecycle.compose.LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(key,lifecycle) { lifecycle.repeatOnLifecycle(androidx.lifecycle.Lifecycle.State.STARTED) { while(true) { delay(30000);vm.load(key,path,field,true,retain=true) } } }
    val list=rememberLazyListState()
    ReportDrawnWhen { page.items.isNotEmpty() || page.error!=null || (!page.loading && state.pages.containsKey(key)) }
    LaunchedEffect(list,key,page.cursor) { snapshotFlow { list.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }.collect { index -> if(index>=list.layoutInfo.totalItemsCount-4 && assets.isNotEmpty() && page.cursor!=null && !page.loading && page.error==null)vm.load(key,path+if(category=="Spot" && !launch)"&offset="+page.cursor else "&cursor="+Uri.encode(page.cursor),field,append=true) } }
    Column(Modifier.fillMaxSize()) {
        PullToRefreshBox(isRefreshing=page.loading && page.items.isNotEmpty(),onRefresh={vm.load(key,path,field,true)},modifier=Modifier.weight(1f)) {
            LazyColumn(state=list,modifier=Modifier.highRefresh(),contentPadding=PaddingValues(bottom=24.dp)) {
                if(!launch && overview!=null)item(key="overview") { overview() }
                item(key="controls") {
        if(!launch)ScrollableTabRow(selectedTabIndex=listOf("Memes","Spot","Perps","Prediction").indexOf(category),edgePadding=16.dp,containerColor=MaterialTheme.colorScheme.background,divider={},indicator={}) { listOf("Memes","Spot","Perps","Prediction").forEach { label -> Tab(selected=category==label,onClick={category=label;query="";applied=""},text={Text(label,color=if(category==label)MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,fontWeight=if(category==label)FontWeight.SemiBold else FontWeight.Normal)}) } }
        Row(Modifier.padding(horizontal=16.dp,vertical=4.dp),verticalAlignment=Alignment.CenterVertically) {
            RallySearch(query,{query=it},if(launch)"Find a launch" else "Search tokens",Modifier.weight(1f))
            if(launch) { Spacer(Modifier.width(8.dp));FilledIconButton(onClick=create,modifier=Modifier.size(52.dp),colors=IconButtonDefaults.filledIconButtonColors(containerColor=MaterialTheme.colorScheme.onSurface,contentColor=MaterialTheme.colorScheme.surface)) { Icon(Icons.Outlined.Add,"Launch a token") } }
        }
                }
                if(page.items.isEmpty() && page.loading)item { LoadingRows() }
                if(page.error!=null)item { EmptyState("Connection interrupted",page.error,"Retry",{vm.load(key,path,field,true)}) }
                if(assets.isEmpty() && !page.loading && page.error==null)item { EmptyState("No markets found",if(query.isNotBlank())"Try a token name or address" else "Pull to refresh") }
                if(category=="Prediction") {
                    item { Text("Price predictions",Modifier.padding(20.dp),color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodyMedium) }
                    items(assets,key={it.key}) { a->PredictionRow(a,{onAsset(a)}) }
                } else {
                    item { Row(Modifier.padding(horizontal=16.dp,vertical=4.dp)) { Text(if(launch)"New launches" else "Asset",Modifier.weight(1f),style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(if(category=="Memes" || launch)"Market cap" else "Price",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant);Spacer(Modifier.width(64.dp)) } }
                    items(assets,key={it.key}) { a -> AssetRow(a,category=="Memes" || launch,{onAsset(a)},{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","buy")))}) }
                }
                if(page.cursor!=null)item { TextButton(onClick={vm.load(key,path+if(category=="Spot" && !launch)"&offset="+page.cursor else "&cursor="+Uri.encode(page.cursor),field,append=true)},modifier=Modifier.fillMaxWidth(),enabled=!page.loading) { Text(if(page.loading)"Loading…" else "Load more") } }
                else if(page.loading && page.items.isNotEmpty())item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
            }
        }
    }
}
@Composable fun AssetRow(asset: Asset,cap: Boolean,onClick: ()->Unit,onBuy: (()->Unit)?=null) {
    Row(Modifier.fillMaxWidth().rallyClickable(onClick).padding(horizontal=16.dp,vertical=6.dp).heightIn(min=52.dp),verticalAlignment=Alignment.CenterVertically) {
        TokenArtwork(asset,36.dp);Spacer(Modifier.width(10.dp))
        Column(Modifier.weight(1f).padding(end=8.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
            Text(asset.symbol,maxLines=1,overflow=TextOverflow.Ellipsis,fontWeight=FontWeight.Medium,fontSize=14.sp,lineHeight=18.sp)
            Text(if(asset.kind=="perps")asset.venue else asset.name,maxLines=1,overflow=TextOverflow.Ellipsis,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Column(Modifier.widthIn(max=if(onBuy==null)148.dp else 116.dp),horizontalAlignment=Alignment.End,verticalArrangement=Arrangement.spacedBy(4.dp)) {
            Text(if(cap && asset.cap!=null)"$"+compact(asset.cap) else money(asset.price),fontWeight=FontWeight.SemiBold,fontSize=14.sp,maxLines=1,overflow=TextOverflow.Ellipsis)
            Text(if(asset.freshness && asset.price!=null)"Last known" else if(cap)money(asset.price) else asset.change?.let { (if(it>=0)"+" else "")+String.format(java.util.Locale.US,"%.2f%%",it) } ?: "",maxLines=1,overflow=TextOverflow.Ellipsis,style=MaterialTheme.typography.bodySmall,color=if(asset.change!=null && !cap)if(asset.change>=0)MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if(onBuy!=null) {
            Spacer(Modifier.width(8.dp))
            TextButton(onClick=onBuy,enabled=asset.executable&&!asset.stale,modifier=Modifier.width(52.dp).heightIn(min=44.dp).semantics { contentDescription=if(asset.kind=="perps")"Buy / Long ${asset.symbol}" else "Buy ${asset.symbol}" },contentPadding=PaddingValues(4.dp),shape=RoundedCornerShape(10.dp),colors=ButtonDefaults.textButtonColors(containerColor=Color.Transparent,contentColor=if(MaterialTheme.colorScheme.surfaceContainer.luminance()<.5f)Color(0xFF8CB8FF) else Color(0xFF0055DD))) { Text(if(asset.kind=="perps")"Long" else "Buy",fontSize=12.sp,maxLines=1) }
        }
    }
    HorizontalDivider(Modifier.padding(horizontal=16.dp),color=MaterialTheme.colorScheme.outlineVariant.copy(alpha=.6f))
}
@Composable fun PredictionRow(asset: Asset,onClick: ()->Unit) {
    val raw=asset.raw;val status=raw.string("state").replace('_',' ')
    Surface(Modifier.padding(horizontal=20.dp,vertical=6.dp).fillMaxWidth().clickable(onClick=onClick),shape=RoundedCornerShape(22.dp),color=MaterialTheme.colorScheme.surface) {
        Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically) { TokenArtwork(asset,36.dp);Spacer(Modifier.width(10.dp));Column(Modifier.weight(1f)) { Text("${asset.symbol} / USD",fontWeight=FontWeight.Medium);Text("Pool #${asset.id}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) };Text(status,style=MaterialTheme.typography.labelSmall,color=if(raw.string("state")=="open")Gain else MaterialTheme.colorScheme.onSurfaceVariant) }
            Text("${raw.string("stake")} ${raw.string("stakeAsset")}",style=MaterialTheme.typography.headlineSmall)
            Row { Text("Entry stake",Modifier.weight(1f),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Text("${raw.optInt("predictions")} entries",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}
@Composable fun NadSwipeScreen(vm: RallyViewModel,onAsset: (Asset)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle();val key="swipe";val page=state.pages[key] ?: Page(loading=true)
    LaunchedEffect(Unit) { vm.load(key,"/api/nadfun/tokens?sort=cap&limit=24","tokens") }
    val assets=remember(page.items) { page.items.map { Asset.parse(it) } }
    val keys=remember(assets) { assets.map { it.key } }
    val lifecycle=androidx.lifecycle.compose.LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(lifecycle) { lifecycle.repeatOnLifecycle(androidx.lifecycle.Lifecycle.State.STARTED) { while(true) { delay(30000);vm.load(key,"/api/nadfun/tokens?sort=cap&limit=24","tokens",true,retain=true) } } }
    Column(Modifier.fillMaxSize()) {
        if(assets.isEmpty()) { if(page.loading)LoadingRows() else EmptyState("Swipe is unavailable",page.error,"Retry",{vm.load(key,"/api/nadfun/tokens?sort=cap&limit=24","tokens",true)}) }
        else {
            NativeSwipeDeck(keys,Modifier.weight(1f),onPage={index->
                assets.drop(index).take(2).forEach(vm::warmChart)
                if(index>=assets.size-4 && page.cursor!=null && !page.loading && page.error==null)
                    vm.load(key,"/api/nadfun/tokens?sort=cap&limit=24&cursor="+Uri.encode(page.cursor),"tokens",append=true)
            }) { index ->
                val a=assets[index]
                    BoxWithConstraints(Modifier.fillMaxSize()) {
                    val compactHeight=maxHeight<440.dp
                    val short=compactHeight || androidx.compose.ui.platform.LocalDensity.current.fontScale>1.3f
                    if(maxHeight<340.dp) {
                        Row(Modifier.fillMaxSize().padding(20.dp),horizontalArrangement=Arrangement.spacedBy(24.dp)) {
                            Column(Modifier.weight(1f).fillMaxHeight(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                                Row(verticalAlignment=Alignment.CenterVertically) { TokenArtwork(a,48.dp);Column(Modifier.padding(start=12.dp)) { Text(a.symbol,fontSize=22.sp,fontWeight=FontWeight.SemiBold,maxLines=1);Text(a.venue,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) } }
                                Spacer(Modifier.weight(1f));Text(money(a.price),fontSize=24.sp)
                            }
                            Column(Modifier.weight(1f).fillMaxHeight(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                                Text("$"+compact(a.cap),fontSize=30.sp);Text("Market cap",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Spacer(Modifier.weight(1f))
                                TradeButtons("Buy","Sell",{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","buy")))},{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","sell")))})
                            }
                        }
                    } else Column(Modifier.fillMaxSize().padding(if(short)16.dp else 24.dp),horizontalAlignment=Alignment.CenterHorizontally) {
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) { Text(a.venue,style=MaterialTheme.typography.labelLarge,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                        if(compactHeight)Spacer(Modifier.height(8.dp)) else Spacer(Modifier.weight(1f));TokenArtwork(a,if(short)44.dp else 112.dp)
                        Spacer(Modifier.height(if(short)6.dp else 20.dp));Text(a.symbol,fontSize=if(short)20.sp else 30.sp,fontWeight=FontWeight.SemiBold,maxLines=1);Text(a.name,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1)
                        Spacer(Modifier.height(if(short)6.dp else 28.dp));Text("$"+compact(a.cap),fontSize=if(short)24.sp else 36.sp,fontWeight=FontWeight.Medium);Text("Market cap",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall)
                        Spacer(Modifier.height(if(short)4.dp else 12.dp));Text(money(a.price),fontSize=if(short)14.sp else 18.sp)
                        if(compactHeight)Spacer(Modifier.height(8.dp)) else Spacer(Modifier.weight(1f));TradeButtons("Buy","Sell",{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","buy")))},{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","sell")))})
                        if(!short)Spacer(Modifier.height(12.dp));if(!short)Text("Swipe for the next token",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                    }
            }
        }
    }
}
@Composable fun TradeButtons(buyLabel: String,sellLabel: String,buy: ()->Unit,sell: ()->Unit,enabled: Boolean=true) {
    Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(12.dp)) {
        val buyInteraction=remember { androidx.compose.foundation.interaction.MutableInteractionSource() }
        val sellInteraction=remember { androidx.compose.foundation.interaction.MutableInteractionSource() }
        Button(onClick=buy,enabled=enabled,interactionSource=buyInteraction,modifier=Modifier.weight(1f).pressFeedback(buyInteraction).heightIn(min=52.dp),shape=RoundedCornerShape(12.dp),colors=ButtonDefaults.buttonColors(containerColor=Buy,contentColor=Color.White)) { Text(buyLabel) }
        Button(onClick=sell,enabled=enabled,interactionSource=sellInteraction,modifier=Modifier.weight(1f).pressFeedback(sellInteraction).heightIn(min=52.dp),shape=RoundedCornerShape(12.dp),colors=ButtonDefaults.buttonColors(containerColor=Sell,contentColor=Color.White)) { Text(sellLabel) }
    }
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun AssetSheet(asset: Asset,vm: RallyViewModel,close: ()->Unit,openBrowser: (String)->Unit,onCommunity: (String)->Unit={}) {
    val sheet=rememberModalBottomSheetState(skipPartiallyExpanded=true)
    val scope=rememberCoroutineScope()
    val focus=androidx.compose.ui.platform.LocalFocusManager.current
    val context=LocalContext.current
    val chartPrefs=remember { context.getSharedPreferences("rally_chart_v1",android.content.Context.MODE_PRIVATE) }
    var period by rememberSaveable(asset.key) { mutableStateOf(chartPrefs.getString("period","1D").takeIf { it in listOf("1D","7D","1M") } ?: "1D") }
    var chart by remember(asset.key) { mutableStateOf(vm.cachedChart(asset,period)?.takeIf { chartPoints(it).isNotEmpty() } ?: referenceChart(asset)) }
    var chartError by remember(asset.key) { mutableStateOf<String?>(null) }
    var chartRetry by remember(asset.key) { mutableIntStateOf(0) }
    var chartLoading by remember(asset.key) { mutableStateOf(true) }
    var chartPeriod by remember(asset.key) { mutableStateOf(period) }
    var trade by rememberSaveable(asset.key) { mutableStateOf(asset.raw.has("nativeSide")) }
    val provider=remember(asset.key) { providerTarget(asset) }
    var providerInterval by rememberSaveable(asset.key) { mutableStateOf("1m") }
    var providerDisabled by rememberSaveable(asset.key) { mutableStateOf(true) }
    val supportsCandles=asset.kind!="prediction" && !(asset.raw.optBoolean("nadfun")&&!asset.raw.optBoolean("graduated"))
    var chartMode by rememberSaveable(asset.key) { mutableStateOf(savedChartMode(chartPrefs.getString("mode",null),supportsCandles)) }
    var tickWindow by rememberSaveable { mutableIntStateOf(savedTickWindow(chartPrefs.getInt("window",60))) }
    fun rememberChart() { chartPrefs.edit().putString("mode",chartMode).putString("period",period).putInt("window",tickWindow).apply() }
    fun selectChart(mode:String) { chartMode=mode;providerDisabled=true;rememberChart() }
    var hourly by remember(asset.key) { mutableStateOf<JSONObject?>(null) }
    var selectedCandle by remember(asset.key) { mutableStateOf<HourCandle?>(null) }
    val candles=remember(hourly) { hourly?.let(::hourlyCandles).orEmpty() }
    var ticks by remember(asset.key) { mutableStateOf<List<PriceTick>>(emptyList()) }
    var tickEpoch by remember(asset.key) { mutableStateOf<String?>(null) }
    var tickCursor by remember(asset.key) { mutableLongStateOf(0) }
    var tickSource by remember(asset.key) { mutableStateOf("Price updates") }
    var ticksDelayed by remember(asset.key) { mutableStateOf(false) }
    var side by rememberSaveable(asset.key) { mutableStateOf(asset.raw.string("nativeSide","buy")) }
    val app by vm.state.collectAsStateWithLifecycle()
    var limit by rememberSaveable(asset.key,side) { mutableStateOf(defaultProtection(asset,side)) }
    var leverage by rememberSaveable(asset.key) { mutableIntStateOf(1) }
    var positionQty by rememberSaveable(asset.key) { mutableStateOf("") }
    var amount by rememberSaveable(asset.key) { mutableStateOf("") }
    var amountMode by rememberSaveable(asset.key) { mutableStateOf("quantity") }
    var options by rememberSaveable(asset.key) { mutableStateOf(false) }
    val quantityMarket=asset.kind=="perps" && asset.venue.lowercase() in setOf("perpl","drake")
    val estimate=remember(amount,amountMode,limit,leverage,asset.key) { perpEstimate(amount,amountMode,limit,asset.raw.optInt("lotDecimals",if(asset.venue=="Perpl")8 else 10),leverage) }
    var quote by remember { mutableStateOf<JSONObject?>(null) }
    var quoteError by remember { mutableStateOf<String?>(null) }
    var quoting by remember { mutableStateOf(false) }
    val scrubbing=remember { mutableStateOf<ChartPoint?>(null) }
    val points=remember(chart) { chart?.let(::chartPoints).orEmpty() }
    fun dismiss() { focus.clearFocus();scope.launch { sheet.hide();close() } }
    val lifecycle=androidx.lifecycle.compose.LocalLifecycleOwner.current.lifecycle
    LaunchedEffect(asset.key,chartMode,trade,lifecycle) {
        if(trade || chartMode !in listOf("Live","Ticks"))return@LaunchedEffect
        lifecycle.repeatOnLifecycle(androidx.lifecycle.Lifecycle.State.STARTED) {
            while(isActive){
                try {
                    val data=vm.priceTicks(asset,tickCursor)
                    ticks=mergePriceTicks(ticks,data,tickEpoch);tickEpoch=data.string("epoch");tickCursor=data.optLong("cursor")
                    tickSource=data.string("source","Price updates");ticksDelayed=data.optBoolean("stale")
                } catch(e:CancellationException){throw e} catch(_:Exception){ticksDelayed=true}
                delay(1000)
            }
        }
    }
    LaunchedEffect(asset.key,period,chartMode,trade,chartRetry,lifecycle) {
        if(trade || chartMode!="1h")return@LaunchedEffect
        if(hourly?.string("period")!=period)hourly=null
        selectedCandle=null
        lifecycle.repeatOnLifecycle(androidx.lifecycle.Lifecycle.State.STARTED) {
            while(isActive) {
                chartLoading=true;chartError=null
                try {
                    val data=vm.freshChart(asset,period,true)
                    if(hourlyCandles(data).isEmpty())throw ApiFailure(404,"No hourly candles yet")
                    hourly=data
                } catch(e:CancellationException){throw e} catch(e:Exception){chartError=if(e is ApiFailure)e.message else "Candles unavailable"}
                finally { chartLoading=false }
                delay(30000)
            }
        }
    }
    LaunchedEffect(asset.key,period,providerDisabled,trade,chartRetry,chartMode) {
        if(trade || chartMode!="History" || provider!=null&&!providerDisabled)return@LaunchedEffect
        chartError=null;chartLoading=true
        try {
            val history=if(!asset.raw.optBoolean("nadfun") || asset.raw.optBoolean("graduated"))vm.freshChart(asset,period) else vm.chart(asset,period)
            scrubbing.value=null
            chart=history.takeIf { chartPoints(it).isNotEmpty() } ?: referenceChart(asset) ?: history
            chartPeriod=period
            if(chartPoints(chart!!).isEmpty())chartError="No chart history yet"
        } catch(e:CancellationException) { throw e } catch(e:Exception) { chartError=if(e is ApiFailure)e.message else "Chart unavailable" } finally { chartLoading=false }
    }
    LaunchedEffect(asset.key,side,amount,trade) {
        quote=null;quoteError=null;quoting=false
        if(trade && asset.kind=="spot" && validAmount(amount)) {
            delay(240);quoting=true
            try { quote=vm.quote(asset,side,amount) } catch(e:CancellationException){throw e} catch(e:Exception){quoteError=e.message ?: "No quote for this amount"} finally { quoting=false }
        }
    }
    ModalBottomSheet(onDismissRequest=close,sheetState=sheet,containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing},dragHandle={
        val d=androidx.compose.ui.platform.LocalDensity.current
        if(WindowInsets.ime.getBottom(d)==0 && with(d) { LocalWindowInfo.current.containerSize.height.toDp() }>=600.dp)BottomSheetDefaults.DragHandle()
    }) {
        val density=androidx.compose.ui.platform.LocalDensity.current
        val keyboard=WindowInsets.ime.getBottom(density)>0
        // The sheet is a separate window. Bound its body using that window's IME insets.
        val windowHeight=with(density) { LocalWindowInfo.current.containerSize.height.toDp() }
        val obscured=with(density) { (WindowInsets.safeDrawing.getTop(density)+maxOf(WindowInsets.ime.getBottom(density),WindowInsets.navigationBars.getBottom(density))).toDp() }
        val windowLimit=(windowHeight-obscured-if(keyboard || windowHeight<600.dp)0.dp else 48.dp).coerceAtLeast(48.dp)
        BoxWithConstraints(Modifier.fillMaxWidth().heightIn(max=windowLimit)) {
            val available=maxHeight.coerceAtMost(780.dp)
            val compactTrade=trade && available<440.dp
            val tightKeyboard=keyboard && maxWidth>=600.dp && available<300.dp
            val compactHeader=trade && maxWidth>=600.dp && available<440.dp
            val graphHeight=animateDpAsState(if(keyboard)0.dp else if(trade)88.dp else if(chartMode=="History" && provider!=null&&!providerDisabled)if(provider.coin!=null)360.dp else 320.dp else if(chartMode=="1h")240.dp else 220.dp,tween(180),label="trade chart")
            @Composable fun direction(modifier: Modifier=Modifier) { Segmented(if(asset.kind=="perps")listOf("Buy / Long","Sell / Short") else listOf("Buy","Sell"),if(side=="buy")if(asset.kind=="perps")"Buy / Long" else "Buy" else if(asset.kind=="perps")"Sell / Short" else "Sell",{if(!app.order.blocksOrder)side=if(it.startsWith("Buy"))"buy" else "sell"},modifier,accent=if(side=="buy")Buy else Sell) }
            Column(Modifier.fillMaxWidth().heightIn(max=available)) {
                Row(Modifier.padding(horizontal=20.dp).padding(bottom=if(compactHeader)4.dp else 12.dp),verticalAlignment=Alignment.CenterVertically) {
                    TokenArtwork(asset,if(compactHeader)24.dp else 40.dp);Spacer(Modifier.width(12.dp))
                    Column(if(compactHeader)Modifier.widthIn(max=90.dp).padding(end=12.dp) else Modifier.weight(1f)) { Text(asset.symbol,style=if(compactHeader)MaterialTheme.typography.titleSmall else MaterialTheme.typography.titleLarge,maxLines=1,overflow=TextOverflow.Ellipsis);if(!compactHeader)Text(asset.venue+if(asset.kind=="perps")" · Perpetual" else " · Monad",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall,maxLines=1,overflow=TextOverflow.Ellipsis) }
                    if(compactHeader && trade && asset.kind!="prediction")direction(Modifier.weight(1f))
                    if(trade && asset.kind!="prediction" && !compactHeader)IconButton(onClick={focus.clearFocus();trade=false}) { Icon(Icons.Outlined.ShowChart,"Show chart") }
                    IconButton(onClick=::dismiss){Icon(Icons.Outlined.Close,"Close token")}
                }
                if(trade && asset.kind!="prediction" && !compactHeader)direction(Modifier.padding(horizontal=20.dp).padding(bottom=if(compactTrade)8.dp else 16.dp))
                Column(Modifier.weight(1f,fill=false).highRefresh().verticalScroll(rememberScrollState()).padding(horizontal=20.dp),verticalArrangement=Arrangement.spacedBy(if(compactTrade)8.dp else 16.dp)) {
                    if(!keyboard && !compactTrade) { if(trade)Fact("Reference price",money(asset.price)) else if(chartMode in listOf("Live","Ticks") && ticks.isNotEmpty())Text(money(scrubbing.value?.value?.toDouble() ?: ticks.last().value),style=MaterialTheme.typography.headlineMedium) else MarketPrice(asset,scrubbing) }
                    if(!trade) {
                        Segmented(if(supportsCandles)listOf("Line","Candles","Ticks") else listOf("Line","Ticks"),if(chartMode=="1h")"Candles" else if(chartMode=="Ticks")"Ticks" else "Line",{selectChart(when(it){"Candles"->"1h";"Ticks"->"Ticks";else->"History"});scrubbing.value=null;selectedCandle=null})
                        if(chartMode=="Ticks")Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                            Text("Updates",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant,modifier=Modifier.padding(end=12.dp))
                            Box(Modifier.weight(1f)) { Segmented(listOf("30","60","120"),tickWindow.toString(),{tickWindow=it.toInt();rememberChart()}) }
                        }
                        if(chartMode in listOf("History","Live") && providerDisabled)Segmented((if(asset.raw.optBoolean("nadfun")&&!asset.raw.optBoolean("graduated"))listOf("1D","7D") else listOf("1D","7D","1M"))+"Live",if(chartMode=="Live")"Live" else period,{if(it=="Live")selectChart("Live") else {period=it;selectChart("History")};scrubbing.value=null})
                    }
                    if(!trade && chartMode=="History" && provider!=null&&!providerDisabled)Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                        Text("CoinGecko · "+if(provider.token!=null)"Monad token" else "Spot reference",Modifier.weight(1f),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        TextButton(onClick={providerDisabled=true}) { Text("Price line") }
                    }
                    if(!compactTrade && !trade)Box(Modifier.fillMaxWidth().animatedHeight(graphHeight).clipToBounds()) {
                        if(chartMode=="1h") {
                            if(candles.isNotEmpty())HourlyCandleChart(candles) { selectedCandle=it }
                            else Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center) { Text(if(chartLoading)"Loading 1h candles…" else chartError ?: "No hourly candles yet",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                            if(chartLoading && candles.isNotEmpty())LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter))
                        }
                        else if(chartMode!="History") {
                            if(ticks.isNotEmpty())LivePriceChart(ticks,chartMode=="Ticks",{scrubbing.value=it},tickEpoch,tickWindow)
                            else Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center) { Text(if(ticksDelayed)"Price updates delayed" else "Waiting for price updates…",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                        }
                        else if(provider!=null&&!providerDisabled)ProviderPriceChart(provider,MaterialTheme.colorScheme.surface.luminance()<.5f,providerInterval,{providerDisabled=true})
                        else if(points.isNotEmpty()) {
                            PriceChart(points,{scrubbing.value=it})
                            if(chartLoading)LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter))
                        }
                        else Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center) { if(chartError!=null)Text(chartError!!,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) else CircularProgressIndicator(Modifier.size(24.dp),strokeWidth=2.dp) }
                    }
                    if(!trade && chartMode=="1h") {
                        Segmented(listOf("1D","7D","1M"),period,{period=it;rememberChart()})
                        selectedCandle?.let { b->
                            Text("O ${money(b.open)}  H ${money(b.high)}\nL ${money(b.low)}  C ${money(b.close)}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        }
                        Text((hourly?.string("reference") ?: "Hourly candles")+if(chartError!=null)" · Update delayed" else if(hourly?.optBoolean("stale")==true)" · Last known" else " · 1h",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        if(chartError!=null)TextButton(onClick={chartRetry++},enabled=!chartLoading) { Text("Retry chart") }
                    }
                    if(!trade && chartMode=="History" && provider?.token!=null&&!providerDisabled)Segmented(listOf("1m","15m","1h","4h"),providerInterval,{providerInterval=it})
                    if(!trade && chartMode=="History" && provider!=null&&providerDisabled)TextButton(onClick={providerDisabled=false;scrubbing.value=null}) { Text("Open CoinGecko chart") }
                    if(!keyboard && !trade) {
                        if(chartMode in listOf("Live","Ticks"))Text(tickSource+(if(ticksDelayed)" · Last known" else "")+(ticks.lastOrNull()?.let { " · "+java.text.SimpleDateFormat("HH:mm:ss",java.util.Locale.US).format(java.util.Date(it.time*1000)) } ?: ""),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        if(chartMode=="History" && (provider==null||providerDisabled))chart?.let { Text(it.string("reference")+if(it.optBoolean("quoteOnly"))if(chartLoading)" · Loading history" else " · No recent history" else " · $chartPeriod"+if(chartLoading)" · Updating…" else if(it.optBoolean("stale") || chartError!=null)" · Last known" else "",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                        if(chartMode=="History" && (provider==null||providerDisabled)&&chartError!=null)Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                            Text(chartError!!,Modifier.weight(1f),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            TextButton(onClick={chartRetry++},enabled=!chartLoading) { Text("Retry chart") }
                        }

                    }
                    if(!trade)TokenInformation(vm,asset) { id->scope.launch { sheet.hide();close();onCommunity(id) } }
                    if(asset.kind=="prediction") { Fact("Entry stake",asset.raw.string("stake")+" "+asset.raw.string("stakeAsset"));Fact("Status",asset.raw.string("state").replace('_',' ')) }
                    if(trade) {
                        val quantity=asset.kind=="perps" && asset.venue in listOf("Perpl","Drake")
                        val denom=if(side=="sell" && asset.kind=="spot")asset.symbol else if(asset.kind=="spot")asset.raw.string("quoteSymbol","MON") else if(quantity)asset.symbol else if(asset.venue=="Pingu")"MON" else "USDC"
                        if(quantityMarket)PerpPositionInput(amount,amountMode,asset.symbol,estimate,if(side=="buy")Buy else Sell,!app.order.blocksOrder,{amount=it},{next->if(!app.order.blocksOrder && amountMode!=next) { if(estimate.valid)amount=if(next=="usd")estimate.notional else estimate.quantity;amountMode=next }},{focus.clearFocus()},margin=asset.venue=="Perpl",showEquivalent=false)
                        else TradeAmount(amount,{amount=it},if(asset.kind=="prediction")"Predicted USD price" else if(quantity)"Quantity" else if(asset.kind=="perps")"Collateral" else if(side=="buy")"You pay" else "You sell",if(asset.kind=="prediction")"USD" else denom,if(side=="buy")Buy else Sell,{focus.clearFocus()},enabled=!app.order.blocksOrder)
                        if(asset.kind=="perps") {
                            if(asset.venue.lowercase()=="leverup")OutlinedTextField(positionQty,{positionQty=it},Modifier.fillMaxWidth(),singleLine=true,enabled=!app.order.blocksOrder,label={Text("Position quantity · ${asset.symbol}")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Decimal),shape=RoundedCornerShape(16.dp))
                            if(asset.venue.lowercase() in listOf("perpl","pingu")) {
                                val max=if(asset.venue.lowercase()=="perpl")5 else minOf(10,asset.raw.optInt("maxLeverage",1))
                                val choices=(listOf(1,2,3,5,10).filter { it<=max }+max).distinct().sorted()
                                Segmented(choices.map { "${it}×" },"${leverage}×",{if(!app.order.blocksOrder)leverage=it.removeSuffix("×").toInt()})
                            }
                            if(asset.venue.lowercase() in listOf("perpl","drake","pingu")) {
                                Row(Modifier.fillMaxWidth().heightIn(min=48.dp).clickable { options=!options }.semantics { contentDescription="Price & options" },verticalAlignment=Alignment.CenterVertically) {
                                    Text("Price & options",Modifier.weight(1f),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                                    Text(if(validAmount(limit))perpDollars(limit) else "Enter price",style=MaterialTheme.typography.bodySmall)
                                    Icon(if(options)Icons.Outlined.Remove else Icons.Outlined.Add,null,Modifier.padding(start=8.dp).size(18.dp))
                                }
                                AnimatedVisibility(options,enter=expandVertically(tween(160))+fadeIn(tween(120)),exit=shrinkVertically(tween(140))+fadeOut(tween(80))) {
                                    OutlinedTextField(limit,{limit=it},Modifier.fillMaxWidth(),singleLine=true,enabled=!app.order.blocksOrder,label={Text("Protection price · USD")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Decimal),shape=RoundedCornerShape(16.dp))
                                }
                            }
                        }
                        if(asset.kind=="spot")Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) { listOf("0.1","1","5","10").forEach { preset->TextButton(onClick={amount=preset;focus.clearFocus()},enabled=!app.order.blocksOrder,modifier=Modifier.weight(1f).heightIn(min=44.dp),contentPadding=PaddingValues(0.dp),shape=RoundedCornerShape(10.dp),colors=ButtonDefaults.textButtonColors(containerColor=MaterialTheme.colorScheme.surfaceContainer,contentColor=if(amount==preset)MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface)) { Text(preset) } } }
                        Box(Modifier.fillMaxWidth().heightIn(min=28.dp)) {
                            if(quoting)LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.Center))
                            quote?.let { q->val best=q.objects("routes").firstOrNull { it.string("state")=="quoted" };Fact(best?.string("provider") ?: q.string("venue","nad.fun"),best?.string("output")?.let { "≈ ${displayAmount(it)} ${if(side=="buy")asset.symbol else "MON"}" } ?: q.string("receive").takeIf { it.isNotBlank() }?.let { "≈ ${displayAmount(it)} ${q.string("outputAsset")}" } ?: "No route for this amount") }
                            quoteError?.let { Text(it,color=Sell,style=MaterialTheme.typography.bodySmall) }
                        }
                    }
                    Spacer(Modifier.height(4.dp))
                }
                Column(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=if(compactTrade)8.dp else 16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    if(trade) {
                        OrderStatus(vm,compact=true)
                        val interaction=remember { androidx.compose.foundation.interaction.MutableInteractionSource() }
                        val action: @Composable (Modifier)->Unit = { modifier -> Button(onClick={focus.clearFocus();vm.trade(NativeTrade(asset,side,amount,limit,leverage,positionQty,amountMode))},interactionSource=interaction,enabled=validAmount(amount) && (!quantityMarket || estimate.valid) && asset.executable && !app.order.blocksOrder && (asset.kind!="perps" || (if(asset.venue.lowercase()=="leverup")validAmount(positionQty) else validAmount(limit))),modifier=modifier.pressFeedback(interaction).heightIn(min=if(tightKeyboard)48.dp else 54.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=if(side=="buy")Buy else Sell,contentColor=Color.White)) {
                            Text(if(asset.kind=="prediction")"Predict price" else if(side=="buy")if(asset.kind=="perps")"Buy / Long" else "Buy" else if(asset.kind=="perps")"Sell / Short" else "Sell",fontWeight=FontWeight.SemiBold)
                            Spacer(Modifier.width(8.dp));Icon(Icons.Outlined.ArrowForward,null,Modifier.size(18.dp))
                        } }
                        if(tightKeyboard)Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(16.dp)) {
                            if(quantityMarket)Text(perpEquivalent(amount,amountMode,asset.symbol,estimate),Modifier.weight(1f),style=MaterialTheme.typography.bodySmall,maxLines=2,overflow=TextOverflow.Ellipsis)
                            action(if(quantityMarket)Modifier.width(220.dp) else Modifier.fillMaxWidth())
                        } else {
                            if(quantityMarket)Text(perpEquivalent(amount,amountMode,asset.symbol,estimate),style=MaterialTheme.typography.bodySmall)
                            action(Modifier.fillMaxWidth())
                        }
                        if(!keyboard)Text("Monad mainnet",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    } else if(asset.kind=="prediction")Button(onClick={trade=true},enabled=asset.executable,modifier=Modifier.fillMaxWidth().heightIn(min=54.dp),shape=RoundedCornerShape(16.dp)) { Text(if(asset.executable)"Predict price" else asset.raw.string("state").replace('_',' ')) }
                    else TradeButtons(if(asset.kind=="perps")"Buy / Long" else "Buy",if(asset.kind=="perps")"Sell / Short" else "Sell",{side="buy";trade=true},{side="sell";trade=true},asset.executable)
                }
            }
        }
    }
}
@Composable private fun MarketPrice(asset: Asset,scrubbing: State<ChartPoint?>) {
    val point=scrubbing.value
    val time=remember(point?.time) { point?.let { java.text.SimpleDateFormat("MMM d · HH:mm",java.util.Locale.US).format(java.util.Date(it.time*1000)) } }
    Column {
        Text(money(point?.value?.toDouble() ?: asset.price),fontSize=32.sp,fontWeight=FontWeight.Medium,maxLines=1,overflow=TextOverflow.Ellipsis)
        Text(time ?: if(asset.freshness)"Last known price" else asset.raw.string("priceSource","Reference price"),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
@Composable fun Fact(label: String,value: String) { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) { Text(label,Modifier.weight(1f),maxLines=2,overflow=TextOverflow.Ellipsis,color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodyMedium);Text(value,style=MaterialTheme.typography.bodyMedium,maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.padding(start=12.dp).weight(1f),textAlign=androidx.compose.ui.text.style.TextAlign.End) } }
@Composable fun PriceChart(points: List<ChartPoint>,onScrub: (ChartPoint?)->Unit) {
    val color=Color(0xFF9178FF)
    val pointer=remember(points) { mutableStateOf<Offset?>(null) }
    val scrub by rememberUpdatedState(onScrub)
    Box(Modifier.fillMaxSize().semantics { contentDescription="Price line chart, ${points.size} observations" }.pointerInput(points) {
        detectDragGestures(onDragEnd={pointer.value=null;scrub(null)},onDragCancel={pointer.value=null;scrub(null)}) { change,_ ->
            change.consume();pointer.value=change.position
            scrub(nearestChartPoint(points,change.position.x/size.width))
        }
    }.drawWithCache {
        val low=points.minOf { it.value };val high=points.maxOf { it.value }
        val range=(high-low).takeIf { it>0 } ?: (abs(high)*.01f).coerceAtLeast(.0000001f)
        val start=points.first().time;val duration=(points.last().time-start).coerceAtLeast(1)
        val offsets=points.map { Offset(if(points.size==1)size.width/2 else (it.time-start).toFloat()/duration*size.width,if(high==low)size.height/2 else size.height-12-(it.value-low)/range*(size.height-24).coerceAtLeast(1f)) }
        val line=Path().apply { offsets.forEachIndexed { i,p->if(i==0)moveTo(p.x,p.y) else lineTo(p.x,p.y) } }
        onDrawBehind {
            drawPath(line,color,style=androidx.compose.ui.graphics.drawscope.Stroke(width=2.dp.toPx(),cap=StrokeCap.Round,join=StrokeJoin.Round))
            drawCircle(color,2.5.dp.toPx(),offsets.last())
            pointer.value?.let { p->drawLine(color.copy(alpha=.3f),Offset(p.x,0f),Offset(p.x,size.height),1.dp.toPx()) }
        }
    })
}
