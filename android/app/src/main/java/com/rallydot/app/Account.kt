package com.rallydot.app

import android.net.Uri
import androidx.compose.foundation.*
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.launch
import org.json.JSONObject

@Composable fun ProfileScreen(vm: RallyViewModel,openBrowser: (String)->Unit,onExtra: (String)->Unit,onAsset: (String)->Unit={}) {
    val state by vm.state.collectAsStateWithLifecycle();val me=state.boot?.optJSONObject("me")
    LaunchedEffect(state.boot?.string("wallet")) { vm.loadPortfolio() }
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(18.dp)) {
        if(me!=null && !state.boot?.string("wallet").isNullOrBlank())item { WalletBalanceHero(vm) }
        item {
            if(me==null)Surface(shape=RoundedCornerShape(24.dp),color=MaterialTheme.colorScheme.surface) {
                Column(Modifier.fillMaxWidth().padding(24.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                    Artwork(safeImage("/assets/community-rally.png"),"Rally",64.dp)
                    Text("Welcome to Rally",style=MaterialTheme.typography.headlineSmall)
                    Text("Your people. Your markets.",style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Row(horizontalArrangement=Arrangement.spacedBy(12.dp),verticalAlignment=Alignment.CenterVertically) {
                        listOf("agent-metamask.svg" to "MetaMask","wallet-coinbase.svg" to "Coinbase Wallet","wallet-rainbow.svg" to "Rainbow").forEach { (file,name)->Artwork(safeImage("/assets/$file"),name,32.dp,false) }
                    }
                    Button(onClick={vm.showWallet()},enabled=!state.connecting,modifier=Modifier.fillMaxWidth().heightIn(min=54.dp),shape=RoundedCornerShape(16.dp),colors=ButtonDefaults.buttonColors(containerColor=MaterialTheme.colorScheme.onSurface,contentColor=MaterialTheme.colorScheme.surface)) { Text(if(state.connecting)"Waiting for approval…" else "Connect account") }
                    Text("Google, email or your wallet",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    if(state.connecting) {
                        Text("Finish connecting in the secure browser",style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                        Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) { Text("Device code ${state.connectionCode.orEmpty()}",Modifier.weight(1f),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant);TextButton(onClick={vm.resumeConnect(openBrowser)}) { Text("Open again") };TextButton(onClick={vm.cancelConnect()}) { Text("Cancel") } }
                    }
                }
            } else {
                val person=Person.parse(me)
                Column(Modifier.fillMaxWidth().padding(vertical=16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                    Artwork(person.image,person.name,48.dp);Text(person.name,style=MaterialTheme.typography.titleLarge);Text("@${person.handle}",color=MaterialTheme.colorScheme.onSurfaceVariant)
                    if(me.string("bio").isNotBlank())Text(me.string("bio"),style=MaterialTheme.typography.bodyMedium)
                    Text("${me.optInt("followers")} followers",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall)
                }
                me.optJSONObject("communityToken")?.let { token->Surface(shape=RoundedCornerShape(20.dp),color=MaterialTheme.colorScheme.surface) { Row(Modifier.fillMaxWidth().clickable { onAsset(token.string("tokenAddress",token.string("address"))) }.padding(18.dp),verticalAlignment=Alignment.CenterVertically) { Artwork(safeImage(token.string("logoURI")),token.string("symbol"),44.dp);Spacer(Modifier.width(12.dp));Column(Modifier.weight(1f)) { Text(token.string("name"),fontWeight=FontWeight.Medium,maxLines=1,overflow=TextOverflow.Ellipsis);Text("${token.optInt("buybackBps")/100}% buyback",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) };Icon(Icons.Outlined.ChevronRight,null,tint=MaterialTheme.colorScheme.onSurfaceVariant) } } }
            }
        }
        item { Surface(shape=RoundedCornerShape(22.dp),color=MaterialTheme.colorScheme.surface) { Column {
            listOf(Triple("Wallet",Icons.Outlined.AccountBalanceWallet,"Wallet"),Triple("Algorithms",Icons.Outlined.Layers,"Algorithms"),Triple("Agents",Icons.Outlined.Hub,"Agents"),Triple("Activity",Icons.Outlined.History,"Activity")).forEach { (label,icon,destination)->OptionRow(label,icon,{onExtra(destination)}) }
            if(me!=null){OptionRow("Notifications",Icons.Outlined.Notifications,{onExtra("Notifications")});OptionRow("Share trades",Icons.Outlined.Share,{onExtra("Share trades")});OptionRow("Signal record",Icons.Outlined.ShowChart,{onExtra("Signal record")});OptionRow("Token benefits",Icons.Outlined.Verified,{onExtra("Token benefits")});OptionRow("Weekly league",Icons.Outlined.EmojiEvents,{onExtra("Weekly league")})}
            if(me!=null)OptionRow("Sign out",Icons.Outlined.Logout,{vm.signOut()})
        } } }
        item { Text("Rally for Android · ${BuildConfig.VERSION_NAME}",Modifier.fillMaxWidth(),textAlign=androidx.compose.ui.text.style.TextAlign.Center,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}
@Composable fun OptionRow(label: String,icon: androidx.compose.ui.graphics.vector.ImageVector,onClick: ()->Unit) {
    Row(Modifier.fillMaxWidth().clickable(onClick=onClick).padding(horizontal=20.dp,vertical=18.dp).heightIn(min=24.dp),verticalAlignment=Alignment.CenterVertically) { Icon(icon,null,tint=MaterialTheme.colorScheme.onSurfaceVariant);Text(label,Modifier.weight(1f).padding(horizontal=14.dp));Icon(Icons.Outlined.ChevronRight,null,tint=MaterialTheme.colorScheme.onSurfaceVariant) }
}
@Composable fun AlgorithmsScreen(vm: RallyViewModel,onAlgorithm: (JSONObject)->Unit) {
    var section by androidx.compose.runtime.saveable.rememberSaveable { mutableStateOf("Marketplace") }
    Column(Modifier.fillMaxSize()) {
        Segmented(listOf("Marketplace","Library · 100"),section,{section=it},Modifier.padding(horizontal=16.dp,vertical=8.dp))
        Box(Modifier.weight(1f)) { if(section=="Marketplace")AlgorithmList(vm,onAlgorithm) else AlgorithmReferenceLibrary() }
    }
}
@Composable fun AgentsScreen(state: AppState) {
    val brands=listOf(Triple("Codex","OpenAI","agent-openai.svg"),Triple("Claude","Anthropic","agent-claude.png"),Triple("Hermes","Nous Research","agent-hermes.png"),Triple("Muse","Meta","agent-meta.svg"),Triple("Grok Bot","xAI","agent-grok.svg"))
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        item { Text("Bring your agent",style=MaterialTheme.typography.titleMedium) }
        items(brands) { (name,company,image)->Row(Modifier.fillMaxWidth().padding(vertical=10.dp),verticalAlignment=Alignment.CenterVertically) { Artwork(safeImage("/assets/$image"),name,48.dp,false);Column(Modifier.padding(start=14.dp)) { Text(name,fontWeight=FontWeight.Medium);Text(company,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) } } }
        item { Text("Connect through Rally's MCP endpoint",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodyMedium);SelectionContainer { Text(ORIGIN+"/mcp",Modifier.padding(vertical=12.dp),color=Violet) } }
        val connections=state.boot?.objects("connections").orEmpty()
        if(connections.isNotEmpty())item { Text("Your connections",style=MaterialTheme.typography.titleMedium) }
        items(connections,key={it.string("id")}) { c->Fact(c.string("name","Agent"),if(c.optBoolean("revoked"))"Revoked" else "Connected") }
    }
}
@Composable fun ActivityScreen(vm: RallyViewModel) {
    val state by vm.state.collectAsStateWithLifecycle();val key="activity";val page=state.pages[key] ?: Page(loading=true)
    LaunchedEffect(state.boot?.optJSONObject("me")?.string("id")) { if(vm.me!=null)vm.load(key,"/api/activity","entries",true) }
    if(vm.me==null)EmptyState("Sign in to view activity") else LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        if(page.loading)item { LinearProgressIndicator(Modifier.fillMaxWidth()) }
        if(page.error!=null)item { EmptyState("Activity unavailable",page.error,"Retry",{vm.load(key,"/api/activity","entries",true)}) }
        items(page.items,key={it.string("id")}) { e->Surface(shape=RoundedCornerShape(20.dp),color=MaterialTheme.colorScheme.surface) { Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) { Fact(e.string("kind").replaceFirstChar { it.uppercase() },e.string("state"));Text(e.string("venue",e.string("feedName")),color=MaterialTheme.colorScheme.onSurfaceVariant);Text(age(e.optLong("created")),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) } } }
        if(!page.loading && page.items.isEmpty() && page.error==null)item { EmptyState("No activity yet") }
    }
}
@Composable fun LeaderboardScreen(vm: RallyViewModel,onAlgorithm: (JSONObject)->Unit,onLeague: ()->Unit={}) {
    val state by vm.state.collectAsStateWithLifecycle();val key="leaderboard";val page=state.pages[key] ?: Page(loading=true)
    LaunchedEffect(Unit) { vm.load(key,"/api/performance/leaderboard","entries") }
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        item { TextButton(onClick=onLeague){Text("Weekly league")};Text("Realized returns · 30 days",style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        if(page.loading && page.items.isEmpty())item { LoadingRows() }
        if(page.error!=null)item { EmptyState("Rankings unavailable",page.error,"Retry",{vm.load(key,"/api/performance/leaderboard","entries",true)}) }
        itemsIndexed(page.items,key={_,item->item.string("id")}) { index,item->Row(Modifier.fillMaxWidth().clickable { onAlgorithm(item) }.padding(vertical=16.dp),verticalAlignment=Alignment.CenterVertically) { Text("${index+1}",Modifier.width(32.dp),color=MaterialTheme.colorScheme.onSurfaceVariant);val person=Person.parse(item.optJSONObject("author") ?: JSONObject());Artwork(person.image,person.name,42.dp);Column(Modifier.weight(1f).padding(start=12.dp)) { Text(item.string("name"),fontWeight=FontWeight.Medium);Text(person.handle,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) };Text(item.optJSONObject("performance")?.number("roi")?.let { String.format(java.util.Locale.US,"%.2f%%",it) } ?: "—",color=Gain) } }
        if(!page.loading && page.items.isEmpty() && page.error==null)item { EmptyState("No verified rankings yet","Rankings use recorded closed trades.") }
    }
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun AlgorithmSheet(item: JSONObject,vm: RallyViewModel,close: ()->Unit,openBrowser: (String)->Unit) {
    val initial=item.optJSONObject("feed") ?: item;val id=initial.string("id",item.string("id")).removePrefix("feed:")
    var benefitOwner by remember {mutableStateOf<String?>(null)}
    var preview by remember(id) { mutableStateOf<JSONObject?>(null) };var error by remember(id) { mutableStateOf<String?>(null) };val scope=rememberCoroutineScope()
    val feed=preview?.optJSONObject("feed") ?: initial
    val price=feed.number("price") ?: 0.0
    val app by vm.state.collectAsStateWithLifecycle()
    val sheet=rememberModalBottomSheetState(skipPartiallyExpanded=true)
    LaunchedEffect(id) { try { preview=vm.api.get("/api/discover/preview?id="+Uri.encode("feed:$id")) } catch(e:Exception){error=e.message} }
    if(benefitOwner!=null){ModalBottomSheet(onDismissRequest={benefitOwner=null},containerColor=MaterialTheme.colorScheme.surface){Box(Modifier.fillMaxWidth().heightIn(max=650.dp)){TokenBenefitsScreen(vm,benefitOwner!!)}};return}
    ModalBottomSheet(onDismissRequest=close,sheetState=sheet,containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing}) {
        Column(Modifier.fillMaxWidth().heightIn(max=720.dp).padding(horizontal=20.dp,vertical=12.dp)) {
            Column(Modifier.weight(1f,false).verticalScroll(rememberScrollState()).padding(bottom=16.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
            AlgorithmArtwork(feed,48.dp);Text(algorithmTitle(feed),style=MaterialTheme.typography.headlineSmall)
            item.optJSONObject("author")?.let { a->val p=Person.parse(a);Row(verticalAlignment=Alignment.CenterVertically) { Artwork(p.image,p.name,36.dp);Text(p.name,Modifier.padding(start=10.dp),color=MaterialTheme.colorScheme.onSurfaceVariant) } }
            val research=feed.optJSONObject("research");val roi=algorithmReturn(feed)
            if(roi!=null) {
                Text(algorithmPercent(roi),fontSize=36.sp,fontWeight=FontWeight.Medium,color=performanceInk(roi))
                Fact("Sampled wallet ROI", "Closed trades")
                Fact("Realized PnL",compact(research?.number("pnlMON"))+" MON")
                research?.objects("trades")?.take(5)?.forEach { t->Fact(t.string("symbol"),algorithmPercent(t.number("returnPct"))) }
                Text("Wallet results, not algorithm returns.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
            } else preview?.optJSONObject("performance")?.takeIf { it.string("state")=="verified" }?.number("roi")?.let { Fact("Creator ROI · 30d",algorithmPercent(it)) }
            Fact("Subscription",if(price>0)feed.string("price")+" USDC / ${feed.optInt("periodDays",30)} days" else "Free")
            preview?.let { p->p.objects("posts").take(1).forEach { Text(it.string("text"),style=MaterialTheme.typography.bodyLarge) };p.optJSONObject("post")?.let { Text(it.string("text"),style=MaterialTheme.typography.bodyLarge) } }
            error?.let { Text(it,color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall) }
            TextButton(onClick={benefitOwner=feed.string("owner")}){Text("Community token benefits")}
            OrderStatus(vm)
            }
            Button(onClick={ if(price>0 && !feed.optBoolean("access"))vm.subscribe(JSONObject(feed.toString()).put("id",id)) else vm.action("/api/feeds/use",JSONObject().put("id",id)) { scope.launch { sheet.hide();close();vm.message("Feed selected") } } },enabled=preview!=null && !app.busy && !app.order.blocksOrder,modifier=Modifier.fillMaxWidth().heightIn(min=54.dp),shape=RoundedCornerShape(16.dp)) { Text(if(price>0 && !feed.optBoolean("access"))"Buy · "+feed.string("price")+" USDC" else if(price>0)"Open feed" else "Get for free") }
        }
    }
}
