package com.rallydot.app

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.lazy.grid.*
import androidx.compose.foundation.shape.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.material3.pulltorefresh.PullToRefreshBox
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.*
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.*
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.compose.ui.viewinterop.AndroidView
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView
import coil.compose.AsyncImage
import kotlinx.coroutines.*
import org.json.JSONObject

fun Post.tradeTarget(): String = raw.optJSONObject("verifiedTrade")?.let { fill ->
    if(fill.string("kind")=="perps") "perpl:"+fill.string("marketId") else asset
} ?: asset

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun FeedScreen(vm: RallyViewModel,community: String?=null,onPost: (Post)->Unit,onAsset: (String)->Unit,compose: ()->Unit,onAlgorithm: ()->Unit={}) {
    val state by vm.state.collectAsStateWithLifecycle()
    var mode by rememberSaveable(community){mutableStateOf("For you")}
    val feed=state.boot?.string("activeFeed","latest") ?: "latest"
    val key="feed:${community.orEmpty()}:$feed:$mode";val path="/api/posts?mode="+when(mode){"Following"->"following";"Trades"->"trades";else->"for-you"}+"&feed="+Uri.encode(feed)+(community?.let { "&community="+Uri.encode(it) } ?: "")
    val page=state.pages[key] ?: Page(loading=true)
    LaunchedEffect(key,state.pages.containsKey(key)) { if(!state.pages.containsKey(key))vm.load(key,path,"posts") }
    val list=rememberLazyListState()
    LaunchedEffect(list,key,page.cursor) { snapshotFlow { list.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }.collect { if(it>=page.items.size-3 && page.cursor!=null && !page.loading && page.error==null)vm.load(key,path+"&cursor="+Uri.encode(page.cursor),"posts",append=true) } }
    PullToRefreshBox(isRefreshing=page.loading && page.items.isNotEmpty(),onRefresh={vm.load(key,path,"posts",true)}) {
        if(page.loading && page.items.isEmpty())LoadingRows() else LazyColumn(state=list,modifier=Modifier.highRefresh(),contentPadding=PaddingValues(bottom=24.dp)) {
            item {
                Row(Modifier.padding(20.dp).fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                    OutlinedButton(onClick=onAlgorithm,shape=RoundedCornerShape(14.dp)) { Icon(Icons.Outlined.Layers,null,Modifier.size(18.dp));Spacer(Modifier.width(8.dp));Text(state.boot?.objects("feeds")?.firstOrNull { it.string("id")==feed }?.string("name") ?: "Latest",maxLines=1) }
                    Spacer(Modifier.weight(1f));FilledIconButton(onClick=compose,colors=IconButtonDefaults.filledIconButtonColors(containerColor=MaterialTheme.colorScheme.onSurface,contentColor=MaterialTheme.colorScheme.surface)) { Icon(Icons.Outlined.Edit,"Create post") }
                }
            }
            if(community==null)item { Segmented(listOf("For you","Following","Trades"),mode,{mode=it},Modifier.padding(horizontal=20.dp,vertical=8.dp)) }
            if(page.error!=null)item { EmptyState("Couldn't refresh",page.error,"Retry",{vm.load(key,path,"posts",true)}) }
            items(page.items,key={it.string("id")},contentType={"post"}) { j->val p=remember(j) { Post.parse(j) };PostCard(p,{onPost(p)},{onAsset(p.tradeTarget())},{vm.action("/api/reaction",JSONObject().put("post",p.id).put("kind","like").put("active",!p.liked)) { vm.load(key,path,"posts",true) }},onRecord={onAsset("signals:"+p.author.id)}) }
            if(page.items.isEmpty() && !page.loading && page.error==null)item { EmptyState("No posts yet",action="Create a post",onAction=compose) }
            if(page.cursor!=null)item { TextButton(onClick={vm.load(key,path+"&cursor="+Uri.encode(page.cursor),"posts",append=true)},modifier=Modifier.fillMaxWidth(),enabled=!page.loading) { Text(if(page.loading)"Loading…" else "Load more") } }
        }
    }
}
@Composable fun PostCard(post: Post,onClick: ()->Unit,onAsset: ()->Unit,onLike: ()->Unit,expanded: Boolean=false,onRecord: (()->Unit)?=null) {
    Column(Modifier.fillMaxWidth().clickable(onClick=onClick).padding(horizontal=20.dp,vertical=16.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
        Row(verticalAlignment=Alignment.CenterVertically) { Artwork(post.author.image,post.author.name,40.dp);Spacer(Modifier.width(10.dp));Column(Modifier.weight(1f)) { Row(verticalAlignment=Alignment.CenterVertically) { Text(post.author.name,fontWeight=FontWeight.Medium,maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.weight(1f,false));if(post.author.agent)Text("Agent",Modifier.padding(start=6.dp),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant) };Text("@${post.author.handle} · ${age(post.created)}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1) };Icon(Icons.Outlined.MoreHoriz,null,tint=MaterialTheme.colorScheme.onSurfaceVariant) }
        post.raw.optJSONObject("author")?.objects("badges")?.take(2)?.forEach {badge->Text(badge.string("label"),style=MaterialTheme.typography.labelSmall,color=Violet)}
        Text(post.text,style=MaterialTheme.typography.bodyLarge,maxLines=if(expanded)Int.MAX_VALUE else 8,overflow=TextOverflow.Ellipsis)
        post.media?.let { media -> val poster=safeImage(media.string("poster",media.string("url")));Box(Modifier.fillMaxWidth().aspectRatio((media.optDouble("width",16.0)/media.optDouble("height",9.0)).toFloat().coerceIn(.6f,1.78f)).clip(RoundedCornerShape(16.dp)).background(MaterialTheme.colorScheme.surfaceContainer)) { AsyncImage(poster,"Post media",Modifier.fillMaxSize(),contentScale=ContentScale.Crop);if(media.string("mime").startsWith("video"))Icon(Icons.Outlined.PlayCircle,"Play video",Modifier.size(52.dp).align(Alignment.Center),tint=Color.White) } }
        post.raw.optJSONObject("signal")?.let { SignalCard(it,onAsset,onRecord) }
        post.raw.optJSONObject("verifiedTrade")?.let { VerifiedTradeCard(it,onAsset) }
        if(post.asset.isNotEmpty()) { val info=post.raw.optJSONObject("assetInfo");AssistChip(onClick=onAsset,label={Text(info?.string("symbol") ?: if(post.asset.startsWith("0x"))post.asset.take(6)+"…"+post.asset.takeLast(4) else post.asset)},leadingIcon={Icon(Icons.Outlined.ShowChart,null,Modifier.size(16.dp))}) }
        Row(horizontalArrangement=Arrangement.spacedBy(20.dp),verticalAlignment=Alignment.CenterVertically) {
            TextButton(onClick=onLike,contentPadding=PaddingValues(0.dp)) { Icon(if(post.liked)Icons.Outlined.Favorite else Icons.Outlined.FavoriteBorder,"Like",Modifier.size(21.dp),tint=if(post.liked)Sell else MaterialTheme.colorScheme.onSurfaceVariant);if(post.likes>0)Text(" ${post.likes}",color=MaterialTheme.colorScheme.onSurfaceVariant) }
            TextButton(onClick=onClick,contentPadding=PaddingValues(0.dp)) { Icon(Icons.Outlined.ChatBubbleOutline,"Replies",Modifier.size(20.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant);if(post.replies>0)Text(" ${post.replies}",color=MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
    HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
}
@Composable fun CommunitiesScreen(vm: RallyViewModel,onCommunity: (String)->Unit,onBenefits: (String)->Unit={}) {
    val state by vm.state.collectAsStateWithLifecycle();val communities=state.boot?.objects("communities").orEmpty()
    LazyColumn(modifier=Modifier.highRefresh(),contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        if(state.boot==null && state.bootError==null)item { LoadingRows() }
        items(communities,key={it.string("id")}) { c->val image=when { c.string("id")=="monad"->"/assets/MON.png";c.string("name")=="Rally"->"/assets/community-rally.png";else->c.string("logoURI") }
            Surface(Modifier.fillMaxWidth().clickable { onCommunity(c.string("id")) },shape=RoundedCornerShape(22.dp),color=MaterialTheme.colorScheme.surface) {
                Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
                    Row(verticalAlignment=Alignment.CenterVertically) { Artwork(safeImage(image),c.string("name"),48.dp);Spacer(Modifier.width(12.dp));Column(Modifier.weight(1f)) { Text(c.string("name"),style=MaterialTheme.typography.titleMedium);Text("${c.optInt("members")} members",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall) };Icon(Icons.Outlined.ChevronRight,null,tint=MaterialTheme.colorScheme.onSurfaceVariant) }
                    if(c.string("tokenOwner").isNotEmpty())TextButton(onClick={onBenefits(c.string("tokenOwner"))}){Text("Token benefits")}
                    Text(c.string("description"),color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodyMedium)
                    OutlinedButton(onClick={vm.action("/api/join",JSONObject().put("id",c.string("id")).put("active",!c.optBoolean("joined")))},shape=RoundedCornerShape(14.dp),enabled=!state.busy) { Text(if(c.optBoolean("joined"))"Joined" else "Join") }
                }
            }
        }
    }
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun DiscoverScreen(vm: RallyViewModel,onPost: (Post)->Unit,onAlgorithm: (JSONObject)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle();var query by rememberSaveable { mutableStateOf("") };var applied by rememberSaveable { mutableStateOf("") };var filter by rememberSaveable { mutableStateOf("all") }
    val key="discover:$filter:$applied";val path="/api/discover?q="+Uri.encode(applied)+"&scope="+filter;val page=state.pages[key] ?: Page(loading=true);val scope=rememberCoroutineScope();val list=rememberLazyGridState()
    LaunchedEffect(query) { delay(280);applied=query.trim() };LaunchedEffect(key) { vm.load(key,path,"items") }
    LaunchedEffect(list,key,page.cursor) { snapshotFlow { list.layoutInfo.visibleItemsInfo.lastOrNull()?.index ?: 0 }.collect { if(it>=page.items.size-4 && page.cursor!=null && !page.loading && page.error==null)vm.load(key,path+"&cursor="+Uri.encode(page.cursor),"items",append=true) } }
    Column(Modifier.fillMaxSize()) {
        OutlinedTextField(query,{query=it},Modifier.fillMaxWidth().padding(horizontal=20.dp,vertical=12.dp),singleLine=true,placeholder={Text("Search people, posts, algorithms",fontSize=14.sp)},leadingIcon={Icon(Icons.Outlined.Search,null)},shape=RoundedCornerShape(100.dp),colors=OutlinedTextFieldDefaults.colors(unfocusedBorderColor=Color.Transparent,unfocusedContainerColor=MaterialTheme.colorScheme.surfaceContainer))
        Row(Modifier.fillMaxWidth().horizontalScroll(rememberScrollState()).padding(horizontal=20.dp),horizontalArrangement=Arrangement.spacedBy(4.dp)) {
            listOf("all" to "For you","algorithms" to "Algorithms","photos" to "Photos","videos" to "Videos").forEach { (id,label)->TextButton(onClick={filter=id},shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.textButtonColors(contentColor=if(filter==id)MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant,containerColor=if(filter==id)MaterialTheme.colorScheme.surfaceContainer else Color.Transparent)) { Text(label,fontSize=11.sp) } }
        }
        PullToRefreshBox(isRefreshing=page.loading && page.items.isNotEmpty(),onRefresh={vm.load(key,path,"items",true)},modifier=Modifier.weight(1f)) {
            if(page.items.isEmpty() && page.loading)LoadingRows() else LazyVerticalGrid(GridCells.Adaptive(110.dp),state=list,modifier=Modifier.highRefresh(),contentPadding=PaddingValues(horizontal=4.dp,vertical=8.dp),horizontalArrangement=Arrangement.spacedBy(4.dp),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                if(page.error!=null)item(span={GridItemSpan(maxLineSpan)}) { EmptyState("Couldn't load discovery",page.error,"Retry",{vm.load(key,path,"items",true)}) }
                items(page.items,key={it.string("id")},contentType={it.string("kind")}) { item -> val cover=safeImage(item.string("cover"));val algorithm=item.string("kind")=="algorithm";Box(Modifier.aspectRatio(1f).clip(RoundedCornerShape(14.dp)).background(MaterialTheme.colorScheme.surfaceContainer).clickable {
                    if(item.string("kind")=="algorithm")onAlgorithm(item) else scope.launch { try { onPost(Post.parse(vm.api.get("/api/post?id="+Uri.encode(item.string("id").removePrefix("post:"))))) } catch(e:Exception){vm.message(e.message)} }
                }) {
                    if(cover!=null)AsyncImage(cover,item.string("title"),Modifier.fillMaxSize().padding(if(item.string("coverType")=="token")20.dp else 0.dp),contentScale=if(item.string("coverType")=="token")ContentScale.Fit else ContentScale.Crop)
                    else if(algorithm)Icon(Icons.Outlined.Layers,null,Modifier.align(Alignment.Center).size(32.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant.copy(alpha=.45f))
                    else Column(Modifier.padding(12.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) { Artwork(Person.parse(item.optJSONObject("author") ?: JSONObject()).image,item.string("title"),32.dp);Text(item.string("title"),fontSize=12.sp,maxLines=3,overflow=TextOverflow.Ellipsis) }
                    if(algorithm) {
                        Box(Modifier.fillMaxSize().background(Brush.verticalGradient(listOf(Color.Transparent,Color.Black.copy(alpha=.75f)),startY=70f)))
                        Icon(Icons.Outlined.Layers,"Algorithm",Modifier.align(Alignment.TopEnd).padding(8.dp).size(16.dp),tint=if(cover==null)MaterialTheme.colorScheme.onSurfaceVariant else Color.White)
                        Column(Modifier.align(Alignment.BottomStart).fillMaxWidth().padding(10.dp),verticalArrangement=Arrangement.spacedBy(5.dp)) {
                            Text(item.string("title"),color=Color.White,fontSize=11.sp,lineHeight=14.sp,maxLines=1,overflow=TextOverflow.Ellipsis)
                            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) { Text(item.optJSONObject("performance")?.number("roi")?.let { String.format(java.util.Locale.US,"%.1f%%",it) } ?: "—",color=Color.White,fontSize=12.sp);Text(item.optJSONObject("feed")?.let { if((it.number("price") ?: 0.0)>0)it.string("price")+" USDC" else "Free" } ?: "",color=Color.White,fontSize=9.sp) }
                        }
                    } else Text("@"+Person.parse(item.optJSONObject("author") ?: JSONObject()).handle,Modifier.align(Alignment.BottomStart).padding(8.dp).background(Color.Black.copy(alpha=.45f),RoundedCornerShape(100.dp)).padding(horizontal=5.dp,vertical=2.dp),color=Color.White,fontSize=9.sp,maxLines=1,overflow=TextOverflow.Ellipsis)
                } }
                if(page.items.isEmpty() && !page.loading)item(span={GridItemSpan(maxLineSpan)}) { EmptyState("No results","Try another name") }
                if(page.cursor!=null)item(span={GridItemSpan(maxLineSpan)}) { TextButton(onClick={vm.load(key,path+"&cursor="+Uri.encode(page.cursor),"items",append=true)},enabled=!page.loading,modifier=Modifier.fillMaxWidth()) { Text(if(page.loading)"Loading…" else "Load more") } }
            }
        }
    }
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun PostSheet(post: Post,vm: RallyViewModel,close: ()->Unit,onAsset: (String)->Unit,openBrowser: (String)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle();val key="replies:${post.id}";val path="/api/replies?post="+Uri.encode(post.id);val page=state.pages[key] ?: Page();var reply by rememberSaveable { mutableStateOf("") }
    LaunchedEffect(post.id) { vm.load(key,path,"posts") }
    ModalBottomSheet(onDismissRequest=close,sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing}) {
        LazyColumn(Modifier.fillMaxWidth().heightIn(max=760.dp).imePadding(),contentPadding=PaddingValues(bottom=24.dp)) {
            item { PostCard(post,{}, {close();onAsset(post.tradeTarget())}, {vm.action("/api/reaction",JSONObject().put("post",post.id).put("kind","like").put("active",!post.liked))},true,onRecord={close();onAsset("signals:"+post.author.id)}) }
            post.media?.takeIf { it.string("mime").startsWith("video") }?.let { media -> item { NativeVideo(safeImage(media.string("url")) ?: "") } }
            if(post.source.isNotBlank())item { TextButton(onClick={openBrowser(post.source)},Modifier.padding(horizontal=16.dp)) { Icon(Icons.Outlined.OpenInNew,null,Modifier.size(16.dp));Spacer(Modifier.width(8.dp));Text("Source") } }
            items(page.items,key={it.string("id")}) { j->PostCard(Post.parse(j),{}, {}, {}) }
            item { Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) { OutlinedTextField(reply,{reply=it},Modifier.fillMaxWidth(),placeholder={Text("Reply")},shape=RoundedCornerShape(16.dp));Button(onClick={vm.action("/api/posts",JSONObject().put("text",reply).put("parent",post.id)) { reply="";vm.load(key,path,"posts",true) }},enabled=reply.isNotBlank() && !state.busy,modifier=Modifier.align(Alignment.End)) { Text("Reply") } } }
        }
    }
}
@Composable fun NativeVideo(url: String) {
    val context=LocalContext.current;val owner=androidx.lifecycle.compose.LocalLifecycleOwner.current
    val player=remember(url) { ExoPlayer.Builder(context).build().apply { setMediaItem(MediaItem.fromUri(url));prepare();playWhenReady=false } }
    DisposableEffect(player,owner) { val observer=androidx.lifecycle.LifecycleEventObserver { _,event->if(event==androidx.lifecycle.Lifecycle.Event.ON_STOP)player.pause() };owner.lifecycle.addObserver(observer);onDispose { owner.lifecycle.removeObserver(observer);player.release() } }
    AndroidView(factory={PlayerView(it).apply { this.player=player;useController=true }},modifier=Modifier.fillMaxWidth().aspectRatio(16f/9))
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun ComposeSheet(vm: RallyViewModel,community: String?,close: ()->Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val draftKey=vm.draftKey(community)
    val initial=remember(draftKey) { vm.draft(draftKey) }
    var text by rememberSaveable(draftKey) { mutableStateOf(initial.text) };var asset by rememberSaveable(draftKey) { mutableStateOf(initial.asset) }
    var file by rememberSaveable(draftKey) { mutableStateOf(initial.file) };var media by rememberSaveable(draftKey) { mutableStateOf(initial.media) };var uploading by remember { mutableStateOf(false) };var error by remember { mutableStateOf<String?>(null) };var requestKey by rememberSaveable { mutableStateOf(initial.requestKey) };val scope=rememberCoroutineScope()
    val picker=rememberLauncherForActivityResult(ActivityResultContracts.OpenDocument()) { uri->file=uri?.toString();media=null;requestKey="android-"+java.util.UUID.randomUUID() }
    var signalEnabled by rememberSaveable(draftKey){mutableStateOf(initial.signalEnabled)};var signalTarget by rememberSaveable(draftKey){mutableStateOf(initial.signalTarget)};var signalStop by rememberSaveable(draftKey){mutableStateOf(initial.signalStop)};var signalDirection by rememberSaveable(draftKey){mutableStateOf(initial.signalDirection)}
    var published by remember { mutableStateOf(false) }
    val currentDraft by rememberUpdatedState(PostDraft(text,asset,file,media,requestKey,signalEnabled,signalTarget,signalStop,signalDirection))
    DisposableEffect(draftKey) { onDispose { if(!published)vm.saveDraft(draftKey,currentDraft) } }
    val pending=state.busy || uploading
    val sheet=rememberModalBottomSheetState(skipPartiallyExpanded=true)
    ModalBottomSheet(onDismissRequest={if(!pending)close()},sheetState=sheet,containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing}) {
        Column(Modifier.fillMaxWidth().heightIn(max=720.dp).verticalScroll(rememberScrollState()).imePadding().padding(24.dp),verticalArrangement=Arrangement.spacedBy(20.dp)) {
            Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) { Text("Create post",Modifier.weight(1f),style=MaterialTheme.typography.titleLarge);Button(onClick={scope.launch { error=null;try { if(file!=null && media==null) { uploading=true;media=vm.api.upload(Uri.parse(file)).string("id") };uploading=false;vm.action("/api/posts",JSONObject().put("text",text).put("asset",asset.ifBlank { JSONObject.NULL }).put("community",community ?: JSONObject.NULL).put("media",media ?: JSONObject.NULL).apply { if(signalEnabled)put("signal",JSONObject().put("direction",signalDirection).put("target",signalTarget).put("invalidation",signalStop).put("hours",24)) },requestKey) { published=true;vm.discardDraft(draftKey);vm.refreshSocial();scope.launch { sheet.hide();close();vm.message("Published") } } } catch(e:Exception){error=e.message} finally { uploading=false } }},enabled=(text.isNotBlank() || file!=null) && text.length<=2000 && !pending) { Text(if(uploading)"Uploading…" else if(state.busy)"Publishing…" else "Publish") } }
            OutlinedTextField(text,{text=it;requestKey="android-"+java.util.UUID.randomUUID()},Modifier.fillMaxWidth().heightIn(min=180.dp),enabled=!pending,placeholder={Text("What's happening?")},shape=RoundedCornerShape(18.dp),supportingText={Text("${text.length} / 2000")})
            OutlinedTextField(asset,{asset=it;requestKey="android-"+java.util.UUID.randomUUID()},Modifier.fillMaxWidth(),enabled=!pending,singleLine=true,label={Text("Token address (optional)")},shape=RoundedCornerShape(16.dp))
            Row(verticalAlignment=Alignment.CenterVertically){Text("Add a price signal",Modifier.weight(1f));Switch(checked=signalEnabled,enabled=!pending,onCheckedChange={signalEnabled=it;requestKey="android-"+java.util.UUID.randomUUID()})}
            if(signalEnabled){
                Segmented(listOf("Upside","Downside"),if(signalDirection=="up")"Upside" else "Downside",{signalDirection=if(it=="Upside")"up" else "down";requestKey="android-"+java.util.UUID.randomUUID()})
                OutlinedTextField(signalTarget,{signalTarget=it;requestKey="android-"+java.util.UUID.randomUUID()},Modifier.fillMaxWidth(),label={Text("Target · USD")},enabled=!pending,singleLine=true)
                OutlinedTextField(signalStop,{signalStop=it;requestKey="android-"+java.util.UUID.randomUUID()},Modifier.fillMaxWidth(),label={Text("Invalidation · USD")},enabled=!pending,singleLine=true)
                Text("Current price and time are recorded by Rally. Duration: 24 hours.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Row(verticalAlignment=Alignment.CenterVertically) { OutlinedButton(onClick={picker.launch(arrayOf("image/jpeg","image/png","image/webp","video/mp4","video/webm"))},enabled=!pending) { Icon(Icons.Outlined.PermMedia,null,Modifier.size(18.dp));Spacer(Modifier.width(8.dp));Text(if(file==null)"Photo / video" else "Change media") };if(file!=null)IconButton(onClick={file=null;media=null;requestKey="android-"+java.util.UUID.randomUUID()},enabled=!pending) { Icon(Icons.Outlined.Close,"Remove media") } }
            error?.let { Text(it,color=Sell,style=MaterialTheme.typography.bodySmall) }
        }
    }
}
