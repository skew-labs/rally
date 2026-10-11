package com.rallydot.app

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
import androidx.compose.ui.graphics.luminance
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.json.JSONObject
import java.util.Locale

fun algorithmTitle(f: JSONObject): String {
    val r=f.optJSONObject("research")
    if(!r?.string("wallet").isNullOrBlank())return (r?.objects("tokens")?.firstOrNull()?.string("symbol") ?: "Public wallet")+" trader"
    return when(f.string("id")){"wallet-reentry"->"Buying again";"wallet-confluence"->"Buying together";"wallet-exits"->"Taking profit";else->f.string("name","Algorithm").replace(Regex("\\s*·\\s*v\\d+$"),"")}
}
fun algorithmReturn(f: JSONObject): Double?=f.optJSONObject("research")?.takeIf { it.string("wallet").isNotBlank() }?.number("returnPct")
fun algorithmPercent(n: Double?)=n?.let { String.format(Locale.US,"%+.1f%%",it) } ?: "—"
fun algorithmPrice(f: JSONObject)=if((f.number("price") ?: 0.0)>0)f.string("price")+" USDC" else "Free"
@Composable fun performanceInk(value: Double)=if(MaterialTheme.colorScheme.surface.luminance()<.3f) { if(value>=0)Color(0xFF78DDB5) else Color(0xFFFF8195) } else if(value>=0)Gain else Sell
fun algorithmItem(f: JSONObject)=JSONObject().put("id","feed:"+f.string("id")).put("title",algorithmTitle(f)).put("feed",f).put("author",f.optJSONObject("creator") ?: JSONObject())
fun rankedAlgorithms(feeds: List<JSONObject>,roi: Boolean=false)=feeds.sortedWith(compareByDescending<JSONObject> { !it.optJSONObject("research")?.string("wallet").isNullOrBlank() }.thenByDescending { if(roi)algorithmReturn(it) ?: -Double.MAX_VALUE else it.optJSONObject("research")?.number("pnlMON") ?: -Double.MAX_VALUE })
fun communityReference(c: JSONObject,now: Long=System.currentTimeMillis()/1000): Double? {
    val t=c.optJSONObject("token") ?: return null
    if(t.optBoolean("stale") || now-t.optLong("verifiedAt")>120)return null
    return t.optJSONObject("stats")?.number("referenceMarketCapUSDC")
}
private fun algorithmOwner(f: JSONObject): String {
    val wallet=f.optJSONObject("research")?.string("wallet").orEmpty()
    return if(wallet.length>12)wallet.take(6)+"…"+wallet.takeLast(4) else "@"+(f.optJSONObject("creator")?.string("handle","rally") ?: "rally")
}
@Composable fun AlgorithmArtwork(f: JSONObject,size: Dp=44.dp) {
    val t=f.optJSONObject("research")?.objects("tokens")?.firstOrNull()
    if(t!=null)Artwork(safeImage(t.string("logoURI")),t.string("symbol"),size)
    else Surface(shape=RoundedCornerShape(12.dp),color=MaterialTheme.colorScheme.surfaceContainer) { Box(Modifier.size(size),contentAlignment=Alignment.Center){Icon(Icons.Outlined.Layers,null,Modifier.size(size*.55f),tint=MaterialTheme.colorScheme.onSurfaceVariant)} }
}
@Composable private fun DiscoveryAction(label: String,description: String,onClick: ()->Unit,enabled: Boolean=true,buy: Boolean=false) {
    Button(onClick=onClick,enabled=enabled,modifier=Modifier.heightIn(min=44.dp).widthIn(min=62.dp).semantics { contentDescription=description },contentPadding=PaddingValues(horizontal=12.dp,vertical=8.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=if(buy)Buy else MaterialTheme.colorScheme.onSurface,contentColor=if(buy)Color.White else MaterialTheme.colorScheme.surface)) { Text(label,maxLines=1,fontSize=12.sp) }
}
@Composable fun AlgorithmListRow(feed: JSONObject,onOpen: ()->Unit) {
    val roi=algorithmReturn(feed);val pnl=feed.optJSONObject("research")?.number("pnlMON")
    Row(Modifier.fillMaxWidth().heightIn(min=104.dp).clickable(onClick=onOpen).padding(vertical=14.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)) {
        AlgorithmArtwork(feed,40.dp)
        Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(5.dp)) {
            Text(algorithmTitle(feed),fontSize=14.sp,fontWeight=FontWeight.Medium,maxLines=1,overflow=TextOverflow.Ellipsis)
            Text(algorithmOwner(feed),fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis)
            if(pnl!=null && roi!=null)Text("${compact(pnl)} MON realized",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis)
        }
        Column(horizontalAlignment=Alignment.End,verticalArrangement=Arrangement.spacedBy(3.dp)) {
            if(roi!=null){Text(algorithmPercent(roi),fontSize=17.sp,color=performanceInk(roi),fontWeight=FontWeight.Medium);Text("Wallet ROI",fontSize=9.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
            DiscoveryAction(if((feed.number("price") ?: 0.0)==0.0)"Get" else if(feed.optBoolean("access"))"Open" else "Buy","Preview "+algorithmTitle(feed),onOpen)
            Text(algorithmPrice(feed),fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
    HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant.copy(alpha=.6f))
}
@Composable fun AlgorithmList(vm: RallyViewModel,onAlgorithm: (JSONObject)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    var query by rememberSaveable { mutableStateOf("") };var filter by rememberSaveable { mutableStateOf("All") };var rank by rememberSaveable { mutableStateOf("Top PnL") }
    val feeds=rankedAlgorithms(state.boot?.objects("feeds").orEmpty(),rank=="Top ROI").filter { (filter!="Free" || (it.number("price") ?: 0.0)==0.0) && (filter!="Paid" || (it.number("price") ?: 0.0)>0.0) && (algorithmTitle(it)+" "+algorithmOwner(it)).contains(query,true) }
    LazyColumn(Modifier.highRefresh(),contentPadding=PaddingValues(horizontal=16.dp,vertical=12.dp)) {
        item { DiscoverySearch(query,{query=it},"Search algorithms");Segmented(listOf("All","Free","Paid"),filter,{filter=it},Modifier.padding(vertical=8.dp));Segmented(listOf("Top PnL","Top ROI"),rank,{rank=it});Text("Sampled wallet results · closed trades",Modifier.padding(vertical=12.dp),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        if(state.boot==null)item { LoadingRows() }
        items(feeds,key={it.string("id")},contentType={"algorithm"}) { f->AlgorithmListRow(f){onAlgorithm(algorithmItem(f))} }
        if(state.boot!=null && feeds.isEmpty())item { EmptyState("No matching algorithms") }
    }
}
@Composable private fun DiscoverySearch(value: String,onValue: (String)->Unit,label: String) {
    OutlinedTextField(value,onValue,Modifier.fillMaxWidth().semantics { contentDescription=label },singleLine=true,placeholder={Text(label,fontSize=14.sp)},leadingIcon={Icon(Icons.Outlined.Search,null)},shape=RoundedCornerShape(16.dp))
}
@Composable fun CommunityList(vm: RallyViewModel,onCommunity: (String)->Unit,onAsset: (Asset)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    var query by rememberSaveable { mutableStateOf("") };var filter by rememberSaveable { mutableStateOf("All") };var rank by rememberSaveable { mutableStateOf("Active") }
    val communities=state.boot?.objects("communities").orEmpty().filter { (filter!="Tokens" || it.optJSONObject("token")!=null) && (filter!="Joined" || it.optBoolean("joined")) && (it.string("name")+" "+it.optJSONObject("token")?.string("symbol").orEmpty()).contains(query,true) }.sortedWith(if(rank=="Members")compareByDescending { it.optInt("members") } else compareByDescending<JSONObject> { it.optInt("posts24h") }.thenByDescending { it.optLong("lastPostAt") }.thenByDescending { it.optJSONObject("token")!=null })
    LazyColumn(Modifier.highRefresh(),contentPadding=PaddingValues(horizontal=16.dp,vertical=12.dp)) {
        item { DiscoverySearch(query,{query=it},"Search communities");Segmented(listOf("All","Tokens","Joined"),filter,{filter=it},Modifier.padding(vertical=8.dp));Segmented(listOf("Active","Members"),rank,{rank=it}) }
        if(state.boot==null)item { LoadingRows() }
        items(communities,key={it.string("id")},contentType={"community"}) { c->
            val token=c.optJSONObject("token");val image=token?.string("logoURI") ?: if(c.string("id")=="monad")"/assets/MON.png" else c.string("logoURI")
            Row(Modifier.fillMaxWidth().heightIn(min=112.dp).clickable { onCommunity(c.string("id")) }.padding(vertical=14.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                Artwork(safeImage(image),c.string("name"),44.dp)
                Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(5.dp)) {
                    Text(c.string("name"),fontSize=15.sp,fontWeight=FontWeight.Medium,maxLines=1,overflow=TextOverflow.Ellipsis)
                    Text(listOfNotNull(token?.string("symbol"),"${c.optInt("members")} members").joinToString(" · "),fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis)
                    Text("${c.optInt("posts24h")} posts in 24h",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    if(token!=null)Text(communityReference(c)?.let { "$"+compact(it)+" cap" } ?: "Price unavailable",fontSize=13.sp,fontWeight=FontWeight.Medium)
                }
                Column(horizontalAlignment=Alignment.End,verticalArrangement=Arrangement.spacedBy(4.dp)) {
                    DiscoveryAction(if(c.optBoolean("joined"))"Open" else "Join","${if(c.optBoolean("joined"))"Open" else "Join"} "+c.string("name"),{if(c.optBoolean("joined"))onCommunity(c.string("id")) else vm.action("/api/join",JSONObject().put("id",c.string("id")).put("active",true))},!state.busy)
                    token?.optJSONObject("asset")?.let { asset->DiscoveryAction("Buy","Buy "+token.string("symbol"),{onAsset(Asset.parse(JSONObject(asset.toString()).put("nativeSide","buy")))},buy=true) }
                }
            };HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant.copy(alpha=.6f))
        }
        if(state.boot!=null && communities.isEmpty())item { EmptyState("No matching communities") }
    }
}
@Composable fun AlgorithmSwipeCard(feed: JSONObject,onPreview: ()->Unit) {
    val roi=algorithmReturn(feed);val research=feed.optJSONObject("research")
    Column(Modifier.fillMaxSize().padding(20.dp)) {
        Column(Modifier.weight(1f).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(18.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(14.dp)) { AlgorithmArtwork(feed,52.dp);Column(Modifier.weight(1f)) { Text("Algorithm",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);Text(algorithmTitle(feed),fontSize=23.sp,fontWeight=FontWeight.Medium);Text(algorithmOwner(feed),fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) } }
            if(roi!=null){Spacer(Modifier.height(12.dp));Text(algorithmPercent(roi),fontSize=48.sp,fontWeight=FontWeight.Medium,color=performanceInk(roi));Text("Sampled wallet ROI · closed trades",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);Text("${compact(research?.number("pnlMON"))} MON realized",fontSize=20.sp);Text("Wallet results, not algorithm returns.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
            else Text(if(feed.string("id").startsWith("wallet-"))"Watch public wallet activity" else "Preview this creator’s feed",style=MaterialTheme.typography.bodyLarge)
            TextButton(onClick=onPreview,contentPadding=PaddingValues(0.dp)){Text(if(roi!=null)"See closed trades" else "See feed preview")}
        }
        HorizontalDivider();Row(Modifier.fillMaxWidth().padding(vertical=16.dp),horizontalArrangement=Arrangement.SpaceBetween) { Text(algorithmPrice(feed),fontWeight=FontWeight.Medium);Text(if((feed.number("price") ?: 0.0)>0)"${feed.optInt("periodDays",30)} days" else "No payment needed",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
        Button(onClick=onPreview,Modifier.fillMaxWidth().heightIn(min=52.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=Buy,contentColor=Color.White)){Text("Preview algorithm")}
    }
}
@Composable fun CommunityRoom(vm: RallyViewModel,id: String,onAsset: (Asset)->Unit,onAlgorithm: (JSONObject)->Unit,onBenefits: (String)->Unit,feed: @Composable ()->Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val community=state.boot?.objects("communities")?.firstOrNull { it.string("id")==id }
    val token=community?.optJSONObject("token")
    var section by rememberSaveable(id) { mutableStateOf("Feed") }
    Column(Modifier.fillMaxSize()) {
        if(token!=null) {
            Row(Modifier.fillMaxWidth().padding(horizontal=16.dp,vertical=8.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                Artwork(safeImage(token.string("logoURI")),token.string("symbol"),40.dp)
                Column(Modifier.weight(1f)) { Text(token.string("symbol"),fontWeight=FontWeight.Medium);Text(communityReference(community)?.let { "$"+compact(it)+" cap" } ?: "Price unavailable",fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                DiscoveryAction(if(community.optBoolean("joined"))"Joined" else "Join","Join community",{vm.action("/api/join",JSONObject().put("id",id).put("active",!community.optBoolean("joined")))},!state.busy)
            }
            token.optJSONObject("asset")?.let { raw->Row(Modifier.padding(horizontal=16.dp)) { TradeButtons("Buy","Sell",{onAsset(Asset.parse(JSONObject(raw.toString()).put("nativeSide","buy")))},{onAsset(Asset.parse(JSONObject(raw.toString()).put("nativeSide","sell")))},true) } }
            Segmented(listOf("Feed","Algorithms","Benefits"),section,{section=it},Modifier.padding(horizontal=16.dp,vertical=8.dp))
        }
        Box(Modifier.weight(1f)) {
            if(section=="Algorithms" && token!=null) {
                val feeds=state.boot?.objects("feeds").orEmpty().filter { it.string("owner")==token.string("owner") }
                LazyColumn(contentPadding=PaddingValues(horizontal=16.dp,vertical=8.dp)) { items(feeds,key={it.string("id")}) { f->AlgorithmListRow(f){onAlgorithm(algorithmItem(f))} };if(feeds.isEmpty())item { EmptyState("No algorithms yet") } }
            } else if(section=="Benefits" && token!=null)TokenBenefitsScreen(vm,token.string("owner"))
            else feed()
        }
    }
}
