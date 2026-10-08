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
@Composable fun MarketsScreen(vm: RallyViewModel,onAsset: (Asset)->Unit,launch: Boolean=false,create: ()->Unit={}) {
    val state by vm.state.collectAsStateWithLifecycle()
    var category by rememberSaveable { mutableStateOf("Memes") }
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
    LaunchedEffect(list,key,page.cursor) { snapshotFlow { list.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }.collect { index -> if(index>=assets.size-4 && page.cursor!=null && !page.loading && page.error==null)vm.load(key,path+if(category=="Spot" && !launch)"&offset="+page.cursor else "&cursor="+Uri.encode(page.cursor),field,append=true) } }
    Column(Modifier.fillMaxSize()) {
        if(!launch)ScrollableTabRow(selectedTabIndex=listOf("Memes","Spot","Perps","Prediction").indexOf(category),edgePadding=20.dp,containerColor=MaterialTheme.colorScheme.background,divider={},indicator={}) { listOf("Memes","Spot","Perps","Prediction").forEach { label -> Tab(selected=category==label,onClick={category=label;query="";applied=""},text={Text(label,color=if(category==label)MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,fontWeight=if(category==label)FontWeight.SemiBold else FontWeight.Normal)}) } }
        Row(Modifier.padding(horizontal=20.dp,vertical=12.dp),verticalAlignment=Alignment.CenterVertically) {
            OutlinedTextField(query,{query=it},Modifier.weight(1f),singleLine=true,placeholder={Text(if(launch)"Find a launch" else "Search tokens",style=MaterialTheme.typography.bodyMedium)},leadingIcon={Icon(Icons.Outlined.Search,null)},trailingIcon={if(query.isNotEmpty())IconButton(onClick={query=""}){Icon(Icons.Outlined.Close,"Clear search")}},shape=RoundedCornerShape(100.dp),colors=OutlinedTextFieldDefaults.colors(unfocusedBorderColor=Color.Transparent,focusedBorderColor=Violet,unfocusedContainerColor=MaterialTheme.colorScheme.surfaceContainer,focusedContainerColor=MaterialTheme.colorScheme.surfaceContainer))
            if(launch) { Spacer(Modifier.width(8.dp));FilledIconButton(onClick=create,modifier=Modifier.size(52.dp),colors=IconButtonDefaults.filledIconButtonColors(containerColor=MaterialTheme.colorScheme.onSurface,contentColor=MaterialTheme.colorScheme.surface)) { Icon(Icons.Outlined.Add,"Launch a token") } }
        }
        PullToRefreshBox(isRefreshing=page.loading && page.items.isNotEmpty(),onRefresh={vm.load(key,path,field,true)},modifier=Modifier.weight(1f)) {
            if(page.items.isEmpty() && page.loading)LoadingRows()
            else LazyColumn(state=list,modifier=Modifier.highRefresh(),contentPadding=PaddingValues(bottom=24.dp)) {
                if(page.error!=null)item { EmptyState("Connection interrupted",page.error,"Retry",{vm.load(key,path,field,true)}) }
                if(assets.isEmpty() && !page.loading && page.error==null)item { EmptyState("No markets found",if(query.isNotBlank())"Try a token name or address" else "Pull to refresh") }
                if(category=="Prediction") {
                    item { Text("Price predictions",Modifier.padding(20.dp),color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodyMedium) }
                    items(assets,key={it.key}) { a->PredictionRow(a,{onAsset(a)}) }
                } else {
                    item { Row(Modifier.padding(horizontal=20.dp,vertical=8.dp)) { Text(if(launch)"New launches" else "Asset",Modifier.weight(1f),style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(if(category=="Memes" || launch)"Market cap" else "Price",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant) } }
                    items(assets,key={it.key}) { a -> AssetRow(a,category=="Memes" || launch,{onAsset(a)}) }
                }
                if(page.cursor!=null)item { TextButton(onClick={vm.load(key,path+if(category=="Spot" && !launch)"&offset="+page.cursor else "&cursor="+Uri.encode(page.cursor),field,append=true)},modifier=Modifier.fillMaxWidth(),enabled=!page.loading) { Text(if(page.loading)"Loading…" else "Load more") } }
                else if(page.loading && page.items.isNotEmpty())item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
            }
        }
    }
}
@Composable fun AssetRow(asset: Asset,cap: Boolean,onClick: ()->Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick=onClick).padding(horizontal=20.dp,vertical=14.dp).heightIn(min=58.dp),verticalAlignment=Alignment.CenterVertically) {
        Artwork(asset.image,asset.symbol,34.dp);Spacer(Modifier.width(12.dp))
        Column(Modifier.weight(1f).padding(end=8.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
            Text(asset.symbol,maxLines=1,overflow=TextOverflow.Ellipsis,fontWeight=FontWeight.SemiBold,fontSize=14.sp)
            Text(if(asset.kind=="perps")asset.venue else asset.name,maxLines=1,overflow=TextOverflow.Ellipsis,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
        Column(Modifier.widthIn(max=148.dp),horizontalAlignment=Alignment.End,verticalArrangement=Arrangement.spacedBy(4.dp)) {
            Text(if(cap && asset.cap!=null)"$"+compact(asset.cap) else money(asset.price),fontWeight=FontWeight.SemiBold,fontSize=14.sp,maxLines=1,overflow=TextOverflow.Ellipsis)
            Text(if(asset.freshness && asset.price!=null)"Last known" else if(cap)money(asset.price) else asset.change?.let { (if(it>=0)"+" else "")+String.format(java.util.Locale.US,"%.2f%%",it) } ?: asset.venue,maxLines=1,overflow=TextOverflow.Ellipsis,style=MaterialTheme.typography.bodySmall,color=if(asset.change!=null && !cap)if(asset.change>=0)MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.error else MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    HorizontalDivider(Modifier.padding(horizontal=20.dp),color=MaterialTheme.colorScheme.outlineVariant)
}
@Composable fun PredictionRow(asset: Asset,onClick: ()->Unit) {
    val raw=asset.raw;val status=raw.string("state").replace('_',' ')
    Surface(Modifier.padding(horizontal=20.dp,vertical=6.dp).fillMaxWidth().clickable(onClick=onClick),shape=RoundedCornerShape(22.dp),color=MaterialTheme.colorScheme.surface) {
        Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically) { Artwork(asset.image,asset.symbol,40.dp);Spacer(Modifier.width(12.dp));Column(Modifier.weight(1f)) { Text("${asset.symbol} / USD",fontWeight=FontWeight.Medium);Text("Pool #${asset.id}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) };Text(status,style=MaterialTheme.typography.labelSmall,color=if(raw.string("state")=="open")Gain else MaterialTheme.colorScheme.onSurfaceVariant) }
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
                                Row(verticalAlignment=Alignment.CenterVertically) { Artwork(a.image,a.symbol,48.dp);Column(Modifier.padding(start=12.dp)) { Text(a.symbol,fontSize=22.sp,fontWeight=FontWeight.SemiBold,maxLines=1);Text(a.venue,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) } }
                                Spacer(Modifier.weight(1f));Text(money(a.price),fontSize=24.sp);Text("${index+1} / ${assets.size}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            }
                            Column(Modifier.weight(1f).fillMaxHeight(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                                Text("$"+compact(a.cap),fontSize=30.sp);Text("Market cap",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Spacer(Modifier.weight(1f))
                                TradeButtons("Buy","Sell",{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","buy")))},{onAsset(a.copy(raw=JSONObject(a.raw.toString()).put("nativeSide","sell")))})
                            }
                        }
                    } else Column(Modifier.fillMaxSize().padding(if(short)16.dp else 24.dp),horizontalAlignment=Alignment.CenterHorizontally) {
                        Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) { Text(a.venue,style=MaterialTheme.typography.labelLarge,color=MaterialTheme.colorScheme.onSurfaceVariant);Text("${index+1} / ${assets.size}",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                        if(compactHeight)Spacer(Modifier.height(8.dp)) else Spacer(Modifier.weight(1f));Artwork(if(short)a.image else a.heroImage,a.symbol,if(short)44.dp else 112.dp)
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
        Button(onClick=buy,enabled=enabled,interactionSource=buyInteraction,modifier=Modifier.weight(1f).pressFeedback(buyInteraction).heightIn(min=52.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=Buy,contentColor=Color.White)) { Text(buyLabel) }
        Button(onClick=sell,enabled=enabled,interactionSource=sellInteraction,modifier=Modifier.weight(1f).pressFeedback(sellInteraction).heightIn(min=52.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=Sell,contentColor=Color.White)) { Text(sellLabel) }
    }
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun AssetSheet(asset: Asset,vm: RallyViewModel,close: ()->Unit,openBrowser: (String)->Unit) {
    val sheet=rememberModalBottomSheetState(skipPartiallyExpanded=true)
    val scope=rememberCoroutineScope()
    val focus=androidx.compose.ui.platform.LocalFocusManager.current
    val density=androidx.compose.ui.platform.LocalDensity.current
    val keyboard=WindowInsets.ime.getBottom(density)>0
    var period by rememberSaveable(asset.key) { mutableStateOf("1D") }
    var chart by remember(asset.key) { mutableStateOf<JSONObject?>(null) }
    var chartError by remember(asset.key) { mutableStateOf<String?>(null) }
    var chartLoading by remember(asset.key) { mutableStateOf(true) }
    var chartPeriod by remember(asset.key) { mutableStateOf(period) }
    var trade by rememberSaveable(asset.key) { mutableStateOf(asset.raw.has("nativeSide")) }
    var side by rememberSaveable(asset.key) { mutableStateOf(asset.raw.string("nativeSide","buy")) }
    var amount by rememberSaveable(asset.key) { mutableStateOf("") }
    var quote by remember { mutableStateOf<JSONObject?>(null) }
    var quoteError by remember { mutableStateOf<String?>(null) }
    var quoting by remember { mutableStateOf(false) }
    val scrubbing=remember { mutableStateOf<ChartPoint?>(null) }
    val points=remember(chart) { chart?.let(::chartPoints).orEmpty() }
    val graphHeight=animateDpAsState(if(keyboard)0.dp else if(trade)88.dp else 160.dp,tween(180),label="trade chart")
    fun dismiss() { focus.clearFocus();scope.launch { sheet.hide();close() } }
    LaunchedEffect(asset.key,period) {
        chartError=null;chartLoading=true
        try {
            chart=vm.chart(asset,period)
            chartPeriod=period
            if(chartPoints(chart!!).size<2)chartError="No chart history yet"
        } catch(e:CancellationException) { throw e } catch(e:Exception) { chartError=if(e is ApiFailure)e.message else "Chart unavailable" } finally { chartLoading=false }
    }
    LaunchedEffect(asset.key,side,amount,trade) {
        quote=null;quoteError=null;quoting=false
        if(trade && asset.kind=="spot" && validAmount(amount)) {
            delay(240);quoting=true
            try { quote=vm.quote(asset,side,amount) } catch(e:CancellationException){throw e} catch(e:Exception){quoteError=e.message ?: "No quote for this amount"} finally { quoting=false }
        }
    }
    ModalBottomSheet(onDismissRequest=close,sheetState=sheet,containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing},dragHandle={BottomSheetDefaults.DragHandle()}) {
        BoxWithConstraints(Modifier.fillMaxWidth().imePadding()) {
            val available=maxHeight.coerceAtMost(780.dp)
            Column(Modifier.fillMaxWidth().heightIn(max=available)) {
                Row(Modifier.padding(horizontal=20.dp).padding(bottom=12.dp),verticalAlignment=Alignment.CenterVertically) {
                    Artwork(asset.image,asset.symbol,40.dp);Spacer(Modifier.width(12.dp))
                    Column(Modifier.weight(1f)) { Text(asset.symbol,style=MaterialTheme.typography.titleLarge,maxLines=1,overflow=TextOverflow.Ellipsis);Text(asset.venue+if(asset.kind=="perps")" · Perpetual" else " · Monad",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall,maxLines=1,overflow=TextOverflow.Ellipsis) }
                    IconButton(onClick=::dismiss){Icon(Icons.Outlined.Close,"Close token")}
                }
                Column(Modifier.weight(1f,fill=false).highRefresh().verticalScroll(rememberScrollState()).padding(horizontal=20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                    if(!keyboard)MarketPrice(asset,scrubbing)
                    Box(Modifier.fillMaxWidth().animatedHeight(graphHeight).clipToBounds()) {
                        if(points.size>1) {
                            PriceChart(points,{scrubbing.value=it})
                            if(chartLoading)LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.TopCenter))
                        }
                        else Box(Modifier.fillMaxSize(),contentAlignment=Alignment.Center) { if(chartError!=null)Text(chartError!!,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) else CircularProgressIndicator(Modifier.size(24.dp),strokeWidth=2.dp) }
                    }
                    if(!trade)Segmented(if(asset.raw.optBoolean("nadfun"))listOf("1D","7D") else listOf("1D","7D","1M"),period,{period=it})
                    if(!keyboard) {
                        chart?.let { Text(it.string("reference")+" · $chartPeriod"+if(chartLoading)" · Updating…" else if(it.optBoolean("stale") || chartError!=null)" · Last known" else "",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                        if(chartError!=null && points.size>1)Text(chartError!!,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        if(asset.cap!=null)Fact("Market cap", "$"+compact(asset.cap))
                        if(asset.raw.number("liquidity")!=null)Fact("Liquidity",money(asset.raw.number("liquidity")))
                    }
                    if(asset.kind=="prediction") { Fact("Entry stake",asset.raw.string("stake")+" "+asset.raw.string("stakeAsset"));Fact("Status",asset.raw.string("state").replace('_',' ')) }
                    if(trade) {
                        if(asset.kind!="prediction")Segmented(if(asset.kind=="perps")listOf("Buy / Long","Sell / Short") else listOf("Buy","Sell"),if(side=="buy")if(asset.kind=="perps")"Buy / Long" else "Buy" else if(asset.kind=="perps")"Sell / Short" else "Sell",{side=if(it.startsWith("Buy"))"buy" else "sell"},accent=if(side=="buy")Buy else Sell)
                        val quantity=asset.kind=="perps" && asset.venue in listOf("Perpl","Drake")
                        val denom=if(side=="sell" && asset.kind=="spot")asset.symbol else if(asset.kind=="spot")asset.raw.string("quoteSymbol","MON") else if(quantity)asset.symbol else if(asset.venue=="Pingu")"MON" else "USDC"
                        TradeAmount(amount,{amount=it},if(asset.kind=="prediction")"Predicted USD price" else if(quantity)"Quantity" else if(asset.kind=="perps")"Collateral" else if(side=="buy")"You pay" else "You sell",if(asset.kind=="prediction")"USD" else denom,if(side=="buy")Buy else Sell,{focus.clearFocus()})
                        if(asset.kind=="spot")Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(8.dp)) { listOf("0.1","1","5","10").forEach { preset->TextButton(onClick={amount=preset;focus.clearFocus()},Modifier.weight(1f).heightIn(min=44.dp),contentPadding=PaddingValues(0.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.textButtonColors(containerColor=MaterialTheme.colorScheme.surfaceContainer,contentColor=if(amount==preset)MaterialTheme.colorScheme.primary else MaterialTheme.colorScheme.onSurface)) { Text(preset) } } }
                        Box(Modifier.fillMaxWidth().heightIn(min=28.dp)) {
                            if(quoting)LinearProgressIndicator(Modifier.fillMaxWidth().align(Alignment.Center))
                            quote?.let { q->val best=q.objects("routes").firstOrNull { it.string("state")=="quoted" };Fact(best?.string("provider") ?: q.string("venue","nad.fun"),best?.string("output")?.let { "≈ ${displayAmount(it)} ${if(side=="buy")asset.symbol else "MON"}" } ?: q.string("receive").takeIf { it.isNotBlank() }?.let { "≈ ${displayAmount(it)} ${q.string("outputAsset")}" } ?: "No route for this amount") }
                            quoteError?.let { Text(it,color=Sell,style=MaterialTheme.typography.bodySmall) }
                        }
                    }
                    Spacer(Modifier.height(4.dp))
                }
                Column(Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
                    if(trade) {
                        Button(onClick={focus.clearFocus();openBrowser(vm.walletURL(asset,side,amount))},enabled=validAmount(amount) && asset.executable,modifier=Modifier.fillMaxWidth().heightIn(min=54.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=if(side=="buy")Buy else Sell,contentColor=Color.White)) {
                            Text(if(asset.kind=="prediction")"Predict price" else if(side=="buy")if(asset.kind=="perps")"Buy / Long" else "Buy" else if(asset.kind=="perps")"Sell / Short" else "Sell",fontWeight=FontWeight.SemiBold)
                            Spacer(Modifier.width(8.dp));Icon(Icons.Outlined.ArrowForward,null,Modifier.size(18.dp))
                        }
                        if(!keyboard)Text("Wallet approval opens secure checkout.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
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
@Composable fun Fact(label: String,value: String) { Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) { Text(label,color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodyMedium);Text(value,style=MaterialTheme.typography.bodyMedium,maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.padding(start=12.dp).weight(1f),textAlign=androidx.compose.ui.text.style.TextAlign.End) } }
@Composable fun PriceChart(points: List<ChartPoint>,onScrub: (ChartPoint?)->Unit) {
    val color=if(points.last().value>=points.first().value)Buy else Sell
    val pointer=remember(points) { mutableStateOf<Offset?>(null) }
    val scrub by rememberUpdatedState(onScrub)
    Box(Modifier.fillMaxSize().semantics { contentDescription="Price chart, ${points.size} observations" }.pointerInput(points) {
        detectDragGestures(onDragEnd={pointer.value=null;scrub(null)},onDragCancel={pointer.value=null;scrub(null)}) { change,_ ->
            change.consume();pointer.value=change.position
            scrub(nearestChartPoint(points,change.position.x/size.width))
        }
    }.drawWithCache {
        val low=points.minOf { it.value };val high=points.maxOf { it.value }
        val range=(high-low).takeIf { it>0 } ?: (abs(high)*.01f).coerceAtLeast(.0000001f)
        val start=points.first().time;val duration=(points.last().time-start).coerceAtLeast(1)
        val offsets=points.map { Offset((it.time-start).toFloat()/duration*size.width,size.height-12-(it.value-low)/range*(size.height-24).coerceAtLeast(1f)) }
        val line=Path().apply { offsets.forEachIndexed { i,p->if(i==0)moveTo(p.x,p.y) else lineTo(p.x,p.y) } }
        val fill=Path().apply { addPath(line);lineTo(size.width,size.height);lineTo(0f,size.height);close() }
        val gradient=Brush.verticalGradient(listOf(color.copy(alpha=.14f),color.copy(alpha=0f)))
        onDrawBehind {
            drawPath(fill,gradient)
            drawPath(line,color,style=androidx.compose.ui.graphics.drawscope.Stroke(width=2.dp.toPx(),cap=StrokeCap.Round,join=StrokeJoin.Round))
            pointer.value?.let { p->drawLine(color.copy(alpha=.3f),Offset(p.x,0f),Offset(p.x,size.height),1.dp.toPx()) }
        }
    })
}
