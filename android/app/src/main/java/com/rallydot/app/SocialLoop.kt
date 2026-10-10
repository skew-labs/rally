package com.rallydot.app

import android.Manifest
import android.net.Uri
import android.os.Build
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.*
import org.json.JSONArray
import org.json.JSONObject
import java.util.Locale

private fun signalPrice(value: String)=value.toDoubleOrNull()?.let { if(it<.01)String.format(Locale.US,"$%.7f",it) else money(it) } ?: "—"
private fun observedChange(j: JSONObject,key: String="priceChangePercent")=j.number(key)?.let { String.format(Locale.US,"%+.2f%%",it) } ?: "—"
@Composable fun SignalCard(signal: JSONObject,onAsset: ()->Unit,onRecord: (()->Unit)?=null) {
    val entry=signal.getJSONObject("entry");val latest=signal.getJSONObject("latest");val terms=signal.getJSONObject("terms")
    Surface(shape=RoundedCornerShape(18.dp),color=MaterialTheme.colorScheme.surfaceContainer,modifier=Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween) { Text(if(terms.string("direction")=="up")"Upside signal" else "Downside signal",style=MaterialTheme.typography.labelMedium);Text(signal.string("state").replace('_',' '),style=MaterialTheme.typography.labelSmall,color=if(signal.string("state")=="invalidated")Sell else MaterialTheme.colorScheme.onSurfaceVariant) }
            Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) { Text(signalPrice(latest.string("price")),style=MaterialTheme.typography.headlineSmall);Text(observedChange(signal),color=if((signal.number("priceChangePercent") ?: 0.0)>=0)Gain else Sell) }
            Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.spacedBy(10.dp)) { listOf("At publication" to entry.string("price"),"Target" to terms.string("target"),"Invalidation" to terms.string("invalidation")).forEach { (label,value)->Column(Modifier.weight(1f)) { Text(label,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(signalPrice(value),style=MaterialTheme.typography.bodySmall,maxLines=2) } } }
            Text("${entry.string("source")} · ${age(entry.optLong("observedAt"))}${if(signal.optBoolean("stale"))" · Price stale" else ""}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            Text("Observed prices · not realized profit",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            Row(horizontalArrangement=Arrangement.spacedBy(8.dp)) { TextButton(onClick=onAsset) { Icon(Icons.Outlined.ShowChart,null,Modifier.size(18.dp));Spacer(Modifier.width(8.dp));Text("Open token") };if(onRecord!=null)TextButton(onClick=onRecord){Text("Track record")} }
        }
    }
}
@Composable fun VerifiedTradeCard(fill: JSONObject,onAsset: ()->Unit) {
    Surface(shape=RoundedCornerShape(18.dp),color=MaterialTheme.colorScheme.surfaceContainer,modifier=Modifier.fillMaxWidth()) {
        Column(Modifier.padding(16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
            Text("Verified fill · Finalized",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
            Row(verticalAlignment=Alignment.CenterVertically) { Column(Modifier.weight(1f)) { Text("${fill.string("label",if(fill.string("side")=="buy")"Bought" else "Sold")} ${fill.string("quantity")} ${fill.string("symbol")}",fontWeight=FontWeight.Medium);Text("${fill.string("venue")} · ${age(fill.optLong("created"))}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) };Button(onClick=onAsset,colors=ButtonDefaults.buttonColors(containerColor=Buy)) { Text(if(fill.string("kind")=="perps")"Trade" else "Buy") } }
            Text("Choose your own amount. This does not copy a trade automatically.",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}
@Composable fun NotificationsScreen(vm: RallyViewModel,onPost: (Post)->Unit,onAsset: (String)->Unit) {
    val app by vm.state.collectAsStateWithLifecycle();val context=LocalContext.current;val scope=rememberCoroutineScope()
    var result by remember { mutableStateOf<JSONObject?>(null) };var settings by remember { mutableStateOf<JSONObject?>(null) };var market by remember { mutableStateOf<JSONObject?>(null) };var error by remember { mutableStateOf<String?>(null) };var busy by remember { mutableStateOf(false) }
    suspend fun reload(){result=vm.api.get("/api/notifications",true);settings=vm.api.get("/api/push/settings",true);market=vm.api.get("/api/market-alerts",true)}
    fun enable(){scope.launch { busy=true;try { val cfg=settings?.getJSONObject("config") ?: error("Push configuration unavailable");RallyPush.enable(context,vm.api,vm.me?.string("id") ?: error("Sign in first"),cfg);reload() } catch(e:Exception){error=e.message} finally {busy=false} } }
    val permission=rememberLauncherForActivityResult(ActivityResultContracts.RequestPermission()) { granted->if(granted)enable() else error="Allow notifications in Android settings" }
    LaunchedEffect(vm.me?.string("id")){if(vm.me!=null)try {reload()}catch(e:Exception){error=e.message}}
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(14.dp)) {
        if(vm.me==null)item { EmptyState("Sign in to see notifications") }
        if(settings!=null)item {
            val ready=settings!!.getJSONObject("config").optBoolean("android");val enabled=RallyPush.enabledFor(context,vm.me?.string("id").orEmpty()) && settings!!.optBoolean("enabled")
            Column(verticalArrangement=Arrangement.spacedBy(12.dp)) { Text("Lock-screen notifications",style=MaterialTheme.typography.titleMedium);Text(if(ready)"Subscribed posts, saved signals and watched tokens" else "Android push is ready to connect when Firebase is configured.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                Button(onClick={if(enabled)scope.launch {busy=true;try{RallyPush.disable(context,vm.api);reload()}catch(e:Exception){error=e.message}finally{busy=false}} else if(Build.VERSION.SDK_INT>=33)permission.launch(Manifest.permission.POST_NOTIFICATIONS) else enable()},enabled=ready&&!busy,modifier=Modifier.fillMaxWidth()) {Text(if(enabled)"Turn off on this device" else "Enable notifications")}
            }
        }
        error?.let { item { Text(it,color=Sell,style=MaterialTheme.typography.bodySmall) } }
        val watched=app.boot?.optJSONArray("watches")
        if(watched!=null && watched.length()>0)item {
            Column { Text("Watched-token alerts",style=MaterialTheme.typography.titleMedium)
                for(i in 0 until watched.length()) { val asset=watched.optString(i);val enabled=market?.objects("alerts")?.firstOrNull { it.string("asset")==asset }?.optBoolean("enabled") ?: false
                    Row(Modifier.fillMaxWidth().padding(vertical=8.dp),verticalAlignment=Alignment.CenterVertically) { Text(if(asset.startsWith("0x"))asset.take(8)+"…" else asset,Modifier.weight(1f));Switch(checked=enabled,enabled=!busy,onCheckedChange={active->scope.launch {busy=true;try {vm.api.post("/api/market-alerts",JSONObject().put("asset",asset).put("enabled",active).put("thresholdBps",500));reload()}catch(e:Exception){error=e.message}finally{busy=false}}}) }
                };Text("5% changes · finalized DEX migrations",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
        }
        items(result?.objects("notifications").orEmpty(),key={it.string("id")}) { n->val detail=n.optJSONObject("detail");Column(Modifier.fillMaxWidth().clickable {scope.launch {try {vm.api.post("/api/notifications/read",JSONObject().put("ids",JSONArray().put(n.string("id"))));val route=RallyPush.route(n.string("url"));val id=n.string("post");if(id.isNotEmpty())onPost(Post.parse(vm.api.get("/api/post?id="+Uri.encode(id),true))) else (route?.getQueryParameter("token") ?: route?.getQueryParameter("id"))?.let(onAsset);reload()}catch(e:Exception){error=e.message}}}.padding(vertical=12.dp),verticalArrangement=Arrangement.spacedBy(6.dp)) {Text(detail?.string("title") ?: "Rally activity",fontWeight=FontWeight.Medium);Text(detail?.string("body") ?: n.string("text"),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(age(n.optLong("created")),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)} }
    }
}
@Composable fun ShareTradesScreen(vm: RallyViewModel,onPost: (Post)->Unit) {
    val scope=rememberCoroutineScope();var result by remember {mutableStateOf<JSONObject?>(null)};var error by remember {mutableStateOf<String?>(null)};var busy by remember {mutableStateOf(false)}
    LaunchedEffect(vm.me?.string("id")){try{result=vm.api.get("/api/trades/shareable",true)}catch(e:Exception){error=e.message}}
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
        item {Text("Only the fills you choose are public.",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodyMedium)}
        error?.let {item {Text(it,color=Sell)}}
        items(result?.objects("trades").orEmpty(),key={it.string("id")}) {t->Column(Modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(10.dp)) { Text("${if(t.string("side")=="buy")"Bought" else "Sold"} ${t.string("quantity")} ${t.string("symbol")}",fontWeight=FontWeight.Medium);Text("${t.string("venue")} · Finalized",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            if(t.string("sharedPost").isEmpty())Button(onClick={scope.launch {busy=true;try {val p=vm.api.post("/api/trades/share",JSONObject().put("trade",t.string("id")));onPost(Post.parse(p));result=vm.api.get("/api/trades/shareable",true);vm.refreshSocial()}catch(e:Exception){error=e.message}finally{busy=false}}},enabled=!busy){Text("Share fill")}
            else if(!t.optBoolean("withdrawn"))TextButton(onClick={scope.launch {busy=true;try {vm.api.post("/api/trades/withdraw",JSONObject().put("post",t.string("sharedPost")));result=vm.api.get("/api/trades/shareable",true);vm.refreshSocial()}catch(e:Exception){error=e.message}finally{busy=false}}},enabled=!busy){Text("Stop sharing")} else Text("Withdrawn",style=MaterialTheme.typography.labelSmall)
            HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
        } }
        if(result!=null && result!!.objects("trades").isEmpty())item {EmptyState("No finalized fills to share yet")}
        if(result==null && error==null)item {LoadingRows()}
    }
}
@Composable fun WeeklyLeagueScreen(vm: RallyViewModel) {
    val state by vm.state.collectAsStateWithLifecycle();val scope=rememberCoroutineScope();var data by remember {mutableStateOf<JSONObject?>(null)};var error by remember {mutableStateOf<String?>(null)};var feed by rememberSaveable {mutableStateOf("")};var busy by remember {mutableStateOf(false)}
    val own=state.boot?.objects("feeds").orEmpty().filter {it.string("owner")==vm.me?.string("id")&&it.string("algorithm_version").isNotEmpty()}
    LaunchedEffect(Unit){try{data=vm.api.get("/api/league",true)}catch(e:Exception){error=e.message}}
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(18.dp)) {
        item {Text("24h price discovery",style=MaterialTheme.typography.titleLarge);Text("UTC week ${data?.string("week").orEmpty()} · Same candidates and features",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}
        if(own.isNotEmpty())item {Column {own.forEach {f->FilterChip(selected=(feed.ifBlank {own.first().string("id")}==f.string("id")),onClick={feed=f.string("id")},label={Text(f.string("name"))})};Button(onClick={scope.launch {busy=true;try {data=vm.api.post("/api/league/enroll",JSONObject().put("feed",feed.ifBlank {own.first().string("id")}))}catch(e:Exception){error=e.message}finally{busy=false}}},enabled=!busy){Text("Enter this week")} } }
        error?.let {item {Text(it,color=Sell)}}
        items(data?.objects("entries").orEmpty(),key={it.string("feed")}) {e->Column(verticalArrangement=Arrangement.spacedBy(8.dp)) {Row(verticalAlignment=Alignment.CenterVertically){Text(if(e.isNull("rank"))"—" else e.string("rank"),Modifier.width(30.dp));Column(Modifier.weight(1f)){Text(e.string("name"),fontWeight=FontWeight.Medium,maxLines=1,overflow=TextOverflow.Ellipsis);Text("${e.optInt("samples")} measured · ${e.optInt("pending")} pending",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)};Text(observedChange(e),color=if((e.number("priceChangePercent") ?: 0.0)>=0)Gain else Sell)};Text("${e.number("discoveryDelaySeconds")?.let {"${(it/60).toInt()}m post-to-pick"} ?: "—"} · ${e.optJSONObject("reader")?.number("engagementRate")?.let {"$it%"} ?: "—"} engagement · ${e.optJSONObject("performance")?.number("roi")?.let {"$it% realized ROI"} ?: "No closed trades"}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant);HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)} }
        if(data!=null && data!!.objects("entries").isEmpty())item {EmptyState("No league entries yet","Publish a custom algorithm to join.")}
        item {Text("Three measured samples to rank. Price movement, reader engagement and realized trade profit are separate metrics.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}
    }
}
@Composable fun SignalRecordScreen(vm: RallyViewModel,onPost: (Post)->Unit,owner: String=vm.me?.string("id").orEmpty()) {
    var data by remember {mutableStateOf<JSONObject?>(null)};var error by remember {mutableStateOf<String?>(null)};val scope=rememberCoroutineScope()
    LaunchedEffect(owner){try {data=vm.api.get("/api/signals?owner="+Uri.encode(owner),true)}catch(e:Exception){error=e.message}}
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
        data?.optJSONObject("counts")?.let {counts->item {Row(Modifier.fillMaxWidth(),horizontalArrangement=Arrangement.SpaceBetween){listOf("Target" to "target_reached","Invalidated" to "invalidated","Expired" to "expired").forEach {(title,id)->Column{Text(title,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(counts.optInt(id).toString(),style=MaterialTheme.typography.headlineSmall)}}}}}
        items(data?.objects("signals").orEmpty(),key={it.string("post")}) {s->Row(Modifier.fillMaxWidth().clickable {scope.launch {try {onPost(Post.parse(vm.api.get("/api/post?id="+Uri.encode(s.string("post")),true)))}catch(e:Exception){error=e.message}}}.padding(vertical=14.dp),verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text(s.getJSONObject("entry").string("symbol"));Text(s.string("state").replace('_',' '),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)};Text(observedChange(s))}}
        item {Text("${data?.optInt("withdrawn") ?: 0} withdrawn. Deleted calls remain in counts. Observed prices are not realized profit.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)}
        error?.let {item{Text(it,color=Sell)}}
    }
}
@Composable fun TokenBenefitsScreen(vm: RallyViewModel,owner: String) {
    val state by vm.state.collectAsStateWithLifecycle();val scope=rememberCoroutineScope();var data by remember(owner) {mutableStateOf<JSONObject?>(null)};var editing by rememberSaveable(owner){mutableStateOf(false)};var tiers by remember(owner){mutableStateOf<List<JSONObject>>(emptyList())};var gates by remember(owner){mutableStateOf<Set<String>>(emptySet())};var error by remember(owner){mutableStateOf<String?>(null)};var busy by remember{mutableStateOf(false)}
    val feeds=state.boot?.objects("feeds").orEmpty().filter{it.string("owner")==owner}
    LaunchedEffect(owner){try {data=vm.api.get("/api/benefits?owner="+Uri.encode(owner),true)}catch(e:Exception){error=e.message}}
    fun update(index: Int,key: String,value: Any){tiers=tiers.mapIndexed {i,t->if(i==index)JSONObject(t.toString()).put(key,value) else t}}
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(18.dp)) {
        if(!editing){
            item {Text("Hold the community token to unlock benefits.",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodyMedium)}
            items(data?.objects("tiers").orEmpty(),key={it.string("label")}) {t->Column(verticalArrangement=Arrangement.spacedBy(6.dp)){Text(t.string("label"),style=MaterialTheme.typography.titleMedium);Text("Hold ${t.string("minimum")} tokens · ${t.optInt("discountBps")/100}% off algorithms",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Text("${t.optJSONArray("feeds")?.length() ?: 0} feeds included",style=MaterialTheme.typography.bodySmall);if(data?.optJSONObject("tier")?.string("label")==t.string("label"))Text("Qualified",color=Violet,style=MaterialTheme.typography.labelMedium);HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)} }
            if(!data?.string("token").isNullOrEmpty() && vm.me!=null)item {
                Button(onClick={scope.launch{busy=true;try{data=vm.api.post("/api/benefits/refresh",JSONObject().put("owner",owner));vm.bootstrap()}catch(e:Exception){error=e.message}finally{busy=false}}},enabled=!busy,modifier=Modifier.fillMaxWidth()){Text(if(data?.optBoolean("verified")==true)"Refresh holdings" else "Check my holdings")}
                if(data?.optBoolean("verified")==true){Text("Finalized block ${data?.optLong("observedBlock")}",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Row(verticalAlignment=Alignment.CenterVertically){Text("Show my member badge",Modifier.weight(1f),style=MaterialTheme.typography.bodyMedium);Switch(checked=data?.optBoolean("showBadge")==true,onCheckedChange={enabled->scope.launch{try{data=vm.api.post("/api/benefits/badge",JSONObject().put("owner",owner).put("enabled",enabled))}catch(e:Exception){error=e.message}}})}}
            }
            if(data?.optBoolean("editable")==true)item {OutlinedButton(onClick={tiers=data!!.objects("tiers").ifEmpty{listOf(JSONObject().put("label","Member").put("minimum","100").put("discountBps",1000).put("feeds",JSONArray()))};gates=data!!.optJSONArray("gatedFeeds")?.let {a->(0 until a.length()).map {a.getString(it)}.toSet()} ?: emptySet();editing=true},modifier=Modifier.fillMaxWidth()){Text("Set benefits")}}
        }else{
            itemsIndexed(tiers) {index,t->Column(verticalArrangement=Arrangement.spacedBy(12.dp)) {
                Text("Tier ${index+1}",style=MaterialTheme.typography.titleMedium)
                OutlinedTextField(t.string("label"),{update(index,"label",it)},Modifier.fillMaxWidth(),label={Text("Name")},singleLine=true)
                OutlinedTextField(t.string("minimum"),{update(index,"minimum",it)},Modifier.fillMaxWidth(),label={Text("Minimum tokens")},singleLine=true)
                OutlinedTextField((t.optInt("discountBps")/100).toString(),{update(index,"discountBps",((it.toIntOrNull() ?: 0)*100).coerceIn(0,9000))},Modifier.fillMaxWidth(),label={Text("Algorithm discount · %")},singleLine=true)
                feeds.forEach {f->val selected=t.optJSONArray("feeds")?.let {a->(0 until a.length()).map {a.getString(it)}.toSet()} ?: emptySet();Row(verticalAlignment=Alignment.CenterVertically){Checkbox(checked=f.string("id")in selected,onCheckedChange={on->update(index,"feeds",JSONArray((if(on)selected+f.string("id") else selected-f.string("id")).toList()))});Text("Include ${f.string("name")}",style=MaterialTheme.typography.bodySmall)}}
                HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
            } }
            if(tiers.size<5)item {TextButton(onClick={tiers=tiers+JSONObject().put("label","").put("minimum","").put("discountBps",0).put("feeds",JSONArray())}){Text("Add tier")}}
            item {Text("Require holdings or subscription",style=MaterialTheme.typography.titleSmall);feeds.forEach {f->Row(verticalAlignment=Alignment.CenterVertically){Checkbox(checked=f.string("id")in gates,onCheckedChange={on->gates=if(on)gates+f.string("id") else gates-f.string("id")});Text(f.string("name"),style=MaterialTheme.typography.bodySmall)}}}
            item {Button(onClick={scope.launch{busy=true;try{data=vm.api.post("/api/benefits/save",JSONObject().put("tiers",JSONArray(tiers)).put("gatedFeeds",JSONArray(gates.toList())));editing=false;vm.bootstrap()}catch(e:Exception){error=e.message}finally{busy=false}}},enabled=!busy,modifier=Modifier.fillMaxWidth()){Text("Save benefits")};TextButton(onClick={editing=false}){Text("Cancel")}}
        }
        error?.let {item{Text(it,color=Sell,style=MaterialTheme.typography.bodySmall)}}
        if(data==null && error==null)item{LoadingRows()}
    }
}
