package com.rallydot.app

import androidx.compose.animation.*
import androidx.compose.animation.core.tween
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.selection.selectable
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.*
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.json.JSONObject
import java.util.Locale

fun discoveryCreator(feed: JSONObject,people: List<JSONObject>): Person=Person.parse(people.firstOrNull { it.string("id")==feed.string("owner") } ?: feed.optJSONObject("creator") ?: JSONObject().put("name","Rally").put("handle","rally"))
fun homeAlgorithms(boot: JSONObject?): List<JSONObject> {
    val all=boot?.objects("feeds").orEmpty();val following=boot?.objects("people").orEmpty().filter { it.optBoolean("following") }.map { it.string("id") }.toSet()
    return (all.filter { it.string("id")==boot?.string("activeFeed") && it.string("owner")!="rally" || it.string("owner") in following || (it.number("price") ?: 0.0)>0 && it.optBoolean("access") }+all.filter { !it.optJSONObject("research")?.string("wallet").isNullOrBlank() }+all.filter { it.has("algorithm_version") && !it.isNull("algorithm_version") }).distinctBy { it.string("id") }.take(2)
}

@Composable fun HomeOverview(vm: RallyViewModel,onAlgorithm: (JSONObject)->Unit,onAlgorithms: ()->Unit,onPortfolio: ()->Unit,onPost: (Post)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    val wallet=state.boot?.string("wallet").orEmpty();val owner=state.boot?.optJSONObject("me")?.string("id").orEmpty()
    val following=state.boot?.objects("people").orEmpty().any { it.optBoolean("following") }
    val key="home-activity:$owner:$following"
    LaunchedEffect(owner,following,state.boot!=null) { if(state.boot!=null)vm.load(key,"/api/posts?mode="+(if(following)"following" else "for-you")+"&feed=latest","posts") }
    LaunchedEffect(wallet) { if(wallet.isNotBlank())vm.loadPortfolio() }
    val balance=state.portfolio?.takeIf { it.string("wallet").equals(wallet,true) }?.optJSONObject("valuation")
    val narrow=androidx.compose.ui.platform.LocalConfiguration.current.screenWidthDp<600
    val feeds=homeAlgorithms(state.boot).take(if(narrow)1 else 2);val post=state.pages[key]?.items?.firstOrNull()?.let(Post::parse)
    Column(Modifier.fillMaxWidth().padding(horizontal=20.dp)) {
        Row(Modifier.fillMaxWidth().clickable { if(wallet.isBlank())vm.showWallet() else onPortfolio() }.padding(top=8.dp,bottom=12.dp),verticalAlignment=Alignment.CenterVertically) {
            Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                Text(if(balance?.optBoolean("partial")==true)"Priced balance" else if(wallet.isBlank())"Your Rally" else "Your balance",fontSize=12.sp,lineHeight=15.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                Text(money(balance?.number("valueUSD")),fontSize=30.sp,lineHeight=38.sp,fontWeight=FontWeight.Medium,letterSpacing=(-.8).sp)
                val change=balance?.number("change24hPercent")
                Text(if(wallet.isBlank())"Sign in to see your balance" else if(change!=null)String.format(Locale.US,"%+.2f%% · 24h price change",change) else if(state.portfolio==null)"Updating balances…" else "24h change unavailable",fontSize=11.sp,lineHeight=14.sp,color=if(change==null)MaterialTheme.colorScheme.onSurfaceVariant else performanceInk(change))
            }
            Surface(shape=RoundedCornerShape(12.dp),color=MaterialTheme.colorScheme.surfaceContainer) { Box(Modifier.size(44.dp),contentAlignment=Alignment.Center){Icon(Icons.Outlined.ChevronRight,if(wallet.isBlank())"Sign in" else "Open portfolio",Modifier.size(20.dp))} }
        }
        Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) { Text(if(following)"Your algorithms" else "Algorithms to watch",Modifier.weight(1f),fontSize=15.sp,lineHeight=19.sp,fontWeight=FontWeight.Medium);TextButton(onClick=onAlgorithms){Text("See all",fontSize=12.sp,lineHeight=15.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)} }
        feeds.forEach { f->AlgorithmListRow(f,discoveryCreator(f,state.boot?.objects("people").orEmpty())) { onAlgorithm(algorithmItem(f)) } }
        if(post!=null)Row(Modifier.fillMaxWidth().clickable { onPost(post) }.padding(vertical=14.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)) {
            ProfileArtwork(post.author.image,post.author.name,28.dp)
            Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) { Text(post.author.name+" · "+if(following)"Following" else "Latest activity",fontSize=10.sp,lineHeight=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis);Text(post.text,fontSize=12.sp,lineHeight=15.sp,maxLines=1,overflow=TextOverflow.Ellipsis) }
            Icon(Icons.Outlined.ChevronRight,null,Modifier.size(16.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant)
        }
    }
}

@Composable fun TokenInformation(vm: RallyViewModel,asset: Asset,onCommunity: (String)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    var section by rememberSaveable(asset.key) { mutableStateOf(if(asset.kind=="spot")"Holders" else "Details") }
    val community=state.boot?.objects("communities")?.firstOrNull { it.optJSONObject("token")?.string("address")?.equals(asset.id,true)==true }
    Column(Modifier.fillMaxWidth()) {
        DetailInformationTabs(if(asset.kind=="spot")listOf("Holders","Community","Details") else listOf("Details","Community"),section,{section=it})
        // Only the lower pane changes. Price history and the order draft stay alive.
        Crossfade(section,animationSpec=tween(140),label="Token information") { shown->
            Column(Modifier.fillMaxWidth().heightIn(min=100.dp).padding(vertical=16.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
                when(shown) {
                    "Holders"->TokenHolders(vm,asset)
                    "Community"->if(community==null)Text("No linked community yet",fontSize=12.sp,lineHeight=15.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) else Row(Modifier.fillMaxWidth().clickable { onCommunity(community.string("id")) }.padding(vertical=12.dp),verticalAlignment=Alignment.CenterVertically){Column(Modifier.weight(1f)){Text(community.string("name"),fontWeight=FontWeight.Medium);Text("${community.optInt("members")} members",fontSize=12.sp,lineHeight=15.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)};Icon(Icons.Outlined.ChevronRight,null)}
                    else->{if(asset.cap!=null)Fact("Market cap","$"+compact(asset.cap));if(asset.raw.number("liquidity")!=null)Fact("Liquidity",money(asset.raw.number("liquidity")));Fact("Market",asset.venue);Fact("Updated",age(asset.time))}
                }
            }
        }
    }
}

@Composable fun DetailInformationTabs(tabs: List<String>,selected: String,onSelect: (String)->Unit) {
    Column { Row(Modifier.fillMaxWidth()) { tabs.forEach { label->
        Column(Modifier.weight(1f).selectable(selected==label,onClick={onSelect(label)},role=androidx.compose.ui.semantics.Role.Tab),horizontalAlignment=Alignment.CenterHorizontally) {
            Box(Modifier.heightIn(min=48.dp).padding(horizontal=4.dp,vertical=12.dp),contentAlignment=Alignment.Center){Text(label,fontSize=12.sp,lineHeight=15.sp,maxLines=1,overflow=TextOverflow.Ellipsis,color=if(selected==label)MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant)}
            HorizontalDivider(thickness=2.dp,color=if(selected==label)MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.surface)
        }
    } };HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant) }
}
