package com.rallydot.app

import android.net.Uri
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.*
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.delay
import kotlinx.coroutines.CancellationException
import org.json.JSONObject

// These are revenue allocations, not a claim that a buyback has executed.
fun subscriptionAllocation(feed: JSONObject): Pair<Int,JSONObject>? {
    val t=feed.optJSONObject("communityToken") ?: return null
    val bps=t.number("buybackBps") ?: return null
    if(t.string("vault").isBlank() || t.string("address").isBlank() || bps !in 0.0..10000.0 || bps%1.0!=0.0)return null
    return bps.toInt() to t
}

@Composable fun SubscriptionAllocation(feed: JSONObject,onToken: (String)->Unit) {
    val (bps,token)=subscriptionAllocation(feed) ?: return
    Surface(shape=RoundedCornerShape(16.dp),color=MaterialTheme.colorScheme.surfaceVariant) {
        Column(Modifier.fillMaxWidth().padding(14.dp),verticalArrangement=Arrangement.spacedBy(10.dp)) {
            Row(Modifier.fillMaxWidth().heightIn(min=44.dp).clickable { onToken(token.string("address")) },verticalAlignment=Alignment.CenterVertically) {
                TokenArtwork(Asset.parse(JSONObject(token.toString()).put("id",token.string("address"))),34.dp)
                Column(Modifier.weight(1f).padding(horizontal=10.dp)) { Text(token.string("symbol"),fontWeight=FontWeight.Medium);Text("Creator’s community token",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                Icon(Icons.Outlined.ChevronRight,null,Modifier.size(18.dp))
            }
            Fact("Buyback allocation",compact(bps/100.0)+"%")
            LinearProgressIndicator(progress={bps/10000f},modifier=Modifier.fillMaxWidth().height(4.dp),color=Violet,trackColor=MaterialTheme.colorScheme.outlineVariant)
            Text("From this subscription. Buybacks execute separately.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun TokenSearchScreen(vm: RallyViewModel,onAsset: (Asset)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    var query by rememberSaveable { mutableStateOf("") };var applied by rememberSaveable { mutableStateOf("") };var sort by rememberSaveable { mutableStateOf("gainers") }
    val key="token-search:$sort:$applied";val path="/api/market-catalog?scope=discovery&sort=$sort&limit=40&query="+Uri.encode(applied)
    val page=state.pages[key] ?: Page(loading=true);val list=rememberLazyListState()
    LaunchedEffect(query) { delay(180);applied=query.trim() }
    LaunchedEffect(key) { vm.load(key,path,"tokens") }
    LaunchedEffect(list,key,page.cursor) { snapshotFlow { list.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }.collect { if(it>=page.items.size-3 && page.cursor!=null && !page.loading && page.error==null)vm.load(key,path+"&offset="+page.cursor,"tokens",append=true) } }
    Column(Modifier.fillMaxSize()) {
        RallySearch(query,{query=it},"Token name or address",Modifier.fillMaxWidth().padding(horizontal=16.dp,vertical=8.dp))
        Row(Modifier.padding(horizontal=16.dp),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            listOf("gainers" to "24h gainers","volume" to "Volume").forEach { (id,label)->TextButton(onClick={sort=id},colors=ButtonDefaults.textButtonColors(contentColor=if(sort==id)MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant)) { Text(label,fontSize=12.sp,fontWeight=if(sort==id)FontWeight.SemiBold else FontWeight.Normal) } }
        }
        LazyColumn(state=list,modifier=Modifier.weight(1f).highRefresh(),contentPadding=PaddingValues(bottom=16.dp)) {
            item { Row(Modifier.fillMaxWidth().padding(horizontal=16.dp,vertical=8.dp)){Text("Token",Modifier.weight(1f),style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant);Text("Price / 24h",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant);Spacer(Modifier.width(60.dp))} }
            if(page.loading && page.items.isEmpty())item { LoadingRows() }
            if(page.error!=null)item { EmptyState("Couldn't load tokens",page.error,"Retry",{vm.load(key,path,"tokens",true)}) }
            items(page.items,key={it.string("id")}) { raw->val asset=Asset.parse(raw);AssetRow(asset,false,{onAsset(asset)},{onAsset(asset.copy(raw=JSONObject(raw.toString()).put("nativeSide","buy")))}) }
            if(!page.loading && page.error==null && page.items.isEmpty())item { EmptyState("No tokens found","Try a name, symbol or contract address.") }
            if(page.cursor!=null)item { TextButton(onClick={vm.load(key,path+"&offset="+page.cursor,"tokens",append=true)},enabled=!page.loading,modifier=Modifier.fillMaxWidth()){Text(if(page.loading)"Loading…" else "Load more")} }
        }
    }
}

@Composable fun CreatorLeaderboardScreen(vm: RallyViewModel,onCreator: (String)->Unit,onAlgorithm: (JSONObject)->Unit,onLeague: ()->Unit) {
    var kind by rememberSaveable { mutableStateOf("all") };var result by remember { mutableStateOf<JSONObject?>(null) };var error by remember { mutableStateOf<String?>(null) };var revision by remember {mutableIntStateOf(0)}
    LaunchedEffect(kind,revision,vm.me?.string("id")) { result=null;error=null;try { result=vm.api.get("/api/performance/leaderboard?kind=$kind",true) }catch(e:CancellationException){throw e}catch(e:Exception){error=e.message} }
    LazyColumn(modifier=Modifier.highRefresh(),contentPadding=PaddingValues(bottom=24.dp)) {
        item { Row(Modifier.fillMaxWidth().padding(horizontal=16.dp),verticalAlignment=Alignment.CenterVertically){Text("Realized ROI · 30 days",Modifier.weight(1f),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant);TextButton(onClick=onLeague){Text("Weekly league",fontSize=12.sp)}} }
        item { Row(Modifier.padding(horizontal=16.dp),horizontalArrangement=Arrangement.spacedBy(8.dp)){listOf("all" to "Everyone","human" to "People","agent" to "Agents").forEach { (id,name)->TextButton(onClick={kind=id},colors=ButtonDefaults.textButtonColors(contentColor=if(kind==id)MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant)){Text(name,fontSize=12.sp)} }} }
        if(result==null && error==null)item{LoadingRows()}
        error?.let { item{EmptyState("Rankings unavailable",it,"Retry",{revision++})} }
        if(result!=null && result!!.objects("entries").isEmpty())item{Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(6.dp)){Text("No verified rankings yet",fontSize=14.sp,fontWeight=FontWeight.Medium);Text("Follow a creator below. Closed trades earn a rank.",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}}
        items(result?.objects("entries").orEmpty(),key={it.string("id")}) { CreatorRankRow(it,true,onCreator,onAlgorithm) }
        if(!result?.objects("unranked").isNullOrEmpty())item { Text("Creators to follow",Modifier.padding(16.dp),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        items(result?.objects("unranked").orEmpty(),key={"unranked:"+it.string("id")}) { CreatorRankRow(it,false,onCreator,onAlgorithm) }
        if(result!=null)item { Text(result!!.string("basis"),Modifier.padding(16.dp),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

@Composable private fun CreatorRankRow(entry: JSONObject,ranked: Boolean,onCreator: (String)->Unit,onAlgorithm: (JSONObject)->Unit) {
    val person=Person.parse(entry.optJSONObject("author") ?: JSONObject());val feeds=entry.objects("algorithms");val roi=entry.optJSONObject("performance")?.number("roi")
    Column(Modifier.fillMaxWidth().padding(horizontal=16.dp,vertical=12.dp),verticalArrangement=Arrangement.spacedBy(6.dp)) {
        Row(verticalAlignment=Alignment.CenterVertically) {
            Text(if(ranked)entry.optInt("rank").toString() else "—",Modifier.width(24.dp),fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
            Row(Modifier.weight(1f).heightIn(min=44.dp).clickable { onCreator(person.id) },verticalAlignment=Alignment.CenterVertically) {
                ProfileArtwork(person.image,person.name,34.dp,identity=person.avatarIdentity)
                Column(Modifier.padding(horizontal=10.dp).weight(1f)){Text(person.name,fontSize=13.sp,fontWeight=FontWeight.Medium,maxLines=1,overflow=TextOverflow.Ellipsis);Text(if(person.agent)"Agent" else "@${person.handle}",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis)}
            }
            Column(horizontalAlignment=Alignment.End){Text(algorithmPercent(roi),fontSize=15.sp,fontWeight=FontWeight.SemiBold,color=if(roi==null)MaterialTheme.colorScheme.onSurfaceVariant else performanceInk(roi));Text(if(ranked)"${entry.optJSONObject("performance")?.optInt("closedTrades")} closed trades" else "Not ranked",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
        }
        Row(Modifier.padding(start=24.dp),verticalAlignment=Alignment.CenterVertically) {
            Button(onClick={if(feeds.size==1)onAlgorithm(algorithmItem(feeds[0])) else onCreator(person.id)},modifier=Modifier.heightIn(min=44.dp),shape=RoundedCornerShape(12.dp),contentPadding=PaddingValues(horizontal=12.dp,vertical=8.dp),colors=ButtonDefaults.buttonColors(containerColor=MaterialTheme.colorScheme.onSurface,contentColor=MaterialTheme.colorScheme.surface)) { Text(if(feeds.size==1 && feeds[0].optBoolean("access") && (feeds[0].number("price") ?: 0.0)>0)"Open feed" else "Subscribe",fontSize=12.sp) }
            Spacer(Modifier.width(10.dp));Text(if(feeds.size==1)subscriptionPrice(feeds[0]) else "${feeds.size} feeds",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
}
fun subscriptionPrice(feed: JSONObject)=if((feed.number("price") ?: 0.0)>0)feed.string("price")+" USDC / ${feed.optInt("periodDays",30)}d" else "Free"

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun CreatorSheet(id: String,vm: RallyViewModel,close: ()->Unit,onToken: (String)->Unit,onAlgorithm: (JSONObject)->Unit,onPost: (Post)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle();var profile by remember(id){mutableStateOf<JSONObject?>(null)};var error by remember(id){mutableStateOf<String?>(null)}
    val feeds=state.boot?.objects("feeds").orEmpty().filter {it.string("owner")==id}
    val key="creator-posts:$id";val path="/api/posts?mode=for-you&feed=latest&author="+Uri.encode(id)
    LaunchedEffect(id) { try { profile=vm.api.get("/api/profile?id="+Uri.encode(id),true);vm.load(key,path,"posts") }catch(e:CancellationException){throw e}catch(e:Exception){error=e.message} }
    ModalBottomSheet(onDismissRequest=close,sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),containerColor=MaterialTheme.colorScheme.surface) {
        LazyColumn(Modifier.fillMaxWidth().heightIn(max=720.dp),contentPadding=PaddingValues(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
            if(profile==null && error==null)item { LoadingRows() }
            error?.let { item { Text(it,color=MaterialTheme.colorScheme.error) } }
            profile?.let { p->val person=Person.parse(p)
                item { Row(verticalAlignment=Alignment.CenterVertically){ProfileArtwork(person.image,person.name,48.dp,identity=person.avatarIdentity);Column(Modifier.padding(start=12.dp).weight(1f)){Text(person.name,style=MaterialTheme.typography.titleLarge,maxLines=2);Text("@${person.handle}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}} }
                if(id!=vm.me?.string("id"))item { TextButton(onClick={if(vm.me==null)vm.showWallet() else vm.action("/api/follow",JSONObject().put("id",id).put("active",!p.optBoolean("following"))){profile=JSONObject(p.toString()).put("following",!p.optBoolean("following"))}}){Text(if(p.optBoolean("following"))"Following" else "Follow")} }
                if(p.string("bio").isNotBlank())item {Text(p.string("bio"),style=MaterialTheme.typography.bodyMedium)}
                p.optJSONObject("communityToken")?.let { token->item { Row(Modifier.fillMaxWidth().heightIn(min=64.dp).clickable {onToken(token.string("address"))}.padding(vertical=8.dp),verticalAlignment=Alignment.CenterVertically){TokenArtwork(Asset.parse(JSONObject(token.toString()).put("id",token.string("address"))),38.dp);Column(Modifier.weight(1f).padding(horizontal=10.dp)){Text(token.string("symbol"),fontWeight=FontWeight.SemiBold);Text("${person.name}’s token",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)};Icon(Icons.Outlined.ChevronRight,null)} } }
                if(feeds.isNotEmpty())item {Text("Subscribe",style=MaterialTheme.typography.titleMedium)}
                items(feeds,key={"plan:"+it.string("id")}) { f->Row(Modifier.fillMaxWidth().heightIn(min=60.dp).clickable {onAlgorithm(algorithmItem(f))},verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text(algorithmTitle(f),fontWeight=FontWeight.Medium);Text(subscriptionPrice(f),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)};Icon(Icons.Outlined.ChevronRight,null)} }
                item {HorizontalDivider();Text("Posts",Modifier.padding(top=12.dp),style=MaterialTheme.typography.titleMedium)}
                items(state.pages[key]?.items.orEmpty(),key={"post:"+it.string("id")}) { raw->val post=Post.parse(raw);Text(post.text,Modifier.fillMaxWidth().clickable {onPost(post)}.padding(vertical=10.dp),maxLines=5,overflow=TextOverflow.Ellipsis,style=MaterialTheme.typography.bodyMedium) }
            }
        }
    }
}

@Composable fun SwipePriceHistory(vm: RallyViewModel,asset: Asset,modifier: Modifier=Modifier) {
    var points by remember(asset.key){mutableStateOf(vm.cachedChart(asset,"1D")?.let(::chartPoints).orEmpty())}
    LaunchedEffect(asset.key) { try { points=chartPoints(vm.chart(asset,"1D")) }catch(e:CancellationException){throw e}catch(_:Exception){} }
    Box(modifier.fillMaxWidth().heightIn(min=60.dp,max=190.dp)) {
        if(points.size>1)PriceChart(points,{})
        else Text("Open chart",Modifier.align(Alignment.Center),fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
