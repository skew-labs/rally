package com.rallydot.app

import android.content.Context
import android.net.Uri
import androidx.activity.compose.BackHandler
import androidx.compose.animation.*
import androidx.compose.animation.core.*
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.*
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.SubcomposeAsyncImage
import kotlinx.coroutines.launch
import org.json.JSONObject

val Violet=Color(0xFF7659F6)
val Buy=Color(0xFF0866FF)
val Sell=Color(0xFFD62F49)
val Gain=Color(0xFF12845A)
@Composable fun RallyTheme(dark: Boolean,content: @Composable ()->Unit) {
    val scheme=if(dark)darkColorScheme(primary=Violet,background=Color(0xFF0F1014),surface=Color(0xFF0F1014),surfaceContainer=Color(0xFF1C1D24),surfaceVariant=Color(0xFF252630),onSurface=Color(0xFFF6F6FA),onSurfaceVariant=Color(0xFFABAEBE),outlineVariant=Color(0xFF2C2E39))
        else lightColorScheme(primary=Violet,background=Color(0xFFFAFAFC),surface=Color.White,surfaceContainer=Color(0xFFF1F2F7),surfaceVariant=Color(0xFFF1F2F7),onSurface=Color(0xFF171820),onSurfaceVariant=Color(0xFF727785),outlineVariant=Color(0xFFE8EAF0))
    MaterialTheme(colorScheme=scheme,typography=Typography().let { t -> t.copy(titleLarge=t.titleLarge.copy(fontWeight=FontWeight.SemiBold),titleMedium=t.titleMedium.copy(fontWeight=FontWeight.Medium),bodyLarge=t.bodyLarge.copy(lineHeight=23.sp),labelLarge=t.labelLarge.copy(fontWeight=FontWeight.Medium)) },content=content)
}
data class Tab(val label: String,val icon: ImageVector)
val Tabs=listOf(Tab("Home",Icons.Outlined.Home),Tab("Communities",Icons.Outlined.PeopleOutline),Tab("Discover",Icons.Outlined.Search),Tab("Leaderboard",Icons.Outlined.EmojiEvents),Tab("Profile",Icons.Outlined.PersonOutline))

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun RallyApp(vm: RallyViewModel,openBrowser: (String)->Unit,link: Uri?) {
    val data by vm.state.collectAsStateWithLifecycle()
    val context=LocalContext.current
    val settings=remember { context.getSharedPreferences("appearance",Context.MODE_PRIVATE) }
    val systemDark=isSystemInDarkTheme()
    var dark by rememberSaveable { mutableStateOf(settings.getBoolean("dark",systemDark)) }
    var tab by rememberSaveable { mutableIntStateOf(0) }
    var home by rememberSaveable { mutableStateOf("Markets") }
    var extra by rememberSaveable { mutableStateOf<String?>(null) }
    var asset by remember { mutableStateOf<Asset?>(null) }
    var post by remember { mutableStateOf<Post?>(null) }
    var algorithm by remember { mutableStateOf<JSONObject?>(null) }
    var community by rememberSaveable { mutableStateOf<String?>(null) }
    var composing by rememberSaveable { mutableStateOf(false) }
    val scope=rememberCoroutineScope()
    val snack=remember { SnackbarHostState() }
    LaunchedEffect(data.message) { data.message?.let { snack.showSnackbar(it);vm.message(null) } }
    fun showAsset(id: String) {
        val rows=data.pages.values.flatMap { it.items }
        val known=rows.firstOrNull { it.string("id")==id || it.string("address")==id } ?: rows.mapNotNull { it.optJSONObject("assetInfo") }.firstOrNull { it.string("id",it.string("address"))==id }
        if(known!=null && known.has("symbol")) { asset=Asset.parse(known);return }
        scope.launch { try {
            val result=if(id=="MON")vm.api.get("/api/markets") else vm.api.get("/api/market-asset?address="+Uri.encode(id))
            val token=if(id=="MON")result.objects("tokens").firstOrNull { it.string("id")=="MON" } else result.optJSONObject("token") ?: result.optJSONObject("asset") ?: result.takeIf { it.has("symbol") }
            if(token!=null)asset=Asset.parse(token) else vm.message("Token details unavailable")
        } catch(e:Exception) { vm.message(e.message ?: "Could not load token") } }
    }
    LaunchedEffect(link) {
        if(link?.scheme=="https" && link.host=="rallydot.com") {
            if(link.getQueryParameter("view")=="token")link.getQueryParameter("id")?.let(::showAsset)
            when(link.getQueryParameter("view")) { "communities"->tab=1;"discover"->tab=2;"leaderboard"->tab=3;"account","agents","feeds","earnings"->tab=4;"launchpad"->{tab=0;home="Launch"};"swipe"->{tab=0;home="Swipe"};"home"->{tab=0;home=when(link.getQueryParameter("section")){"feed"->"Feed";"launchpad"->"Launch";"swipe"->"Swipe";else->"Markets"}} }
        }
    }
    BackHandler(asset==null && post==null && algorithm==null && !composing && (extra!=null || community!=null || tab!=0 || home!="Markets")) {
        when { extra!=null->extra=null;community!=null->community=null;tab!=0->tab=0;else->home="Markets" }
    }
    RallyTheme(dark) {
        val title=extra ?: when { tab==0->"rally.";tab==1 && community!=null->data.boot?.objects("communities")?.firstOrNull { it.string("id")==community }?.string("name") ?: "Community";else->Tabs[tab].label }
        BoxWithConstraints(Modifier.fillMaxSize().background(MaterialTheme.colorScheme.background)) {
            val wide=maxWidth>=600.dp
            val compactRail=maxHeight<600.dp
            Row(Modifier.fillMaxSize()) {
                if(wide)NavigationRail(Modifier.fillMaxHeight().windowInsetsPadding(WindowInsets.safeDrawing),containerColor=MaterialTheme.colorScheme.surface) {
                    if(!compactRail) { Spacer(Modifier.height(24.dp));Text("r.",fontSize=30.sp,fontWeight=FontWeight.Bold,color=Violet);Spacer(Modifier.height(24.dp)) }
                    Tabs.forEachIndexed { i,t -> NavigationRailItem(selected=tab==i && extra==null,onClick={tab=i;extra=null;community=null},icon={Icon(t.icon,t.label)},label=if(compactRail)null else { {Text(if(i==1)"Community" else if(i==3)"Ranks" else t.label,maxLines=1,overflow=TextOverflow.Ellipsis)} }) }
                }
                Scaffold(modifier=Modifier.weight(1f),containerColor=MaterialTheme.colorScheme.background,
                    contentWindowInsets=WindowInsets.safeDrawing,
                    topBar={TopAppBar(title={Text(title,maxLines=1,overflow=TextOverflow.Ellipsis,fontWeight=if(tab==0 && extra==null)FontWeight.Bold else FontWeight.SemiBold,fontSize=if(tab==0 && extra==null)29.sp else 23.sp)},navigationIcon={if(extra!=null || community!=null)IconButton(onClick={extra=null;community=null}){Icon(Icons.Outlined.ArrowBack,"Back")}},actions={
                        IconButton(onClick={dark=!dark;settings.edit().putBoolean("dark",dark).apply()}) { Icon(if(dark)Icons.Outlined.LightMode else Icons.Outlined.DarkMode,"Change theme") }
                        if(tab==0)IconButton(onClick={tab=2}) { Icon(Icons.Outlined.Search,"Search") }
                    },colors=TopAppBarDefaults.topAppBarColors(containerColor=MaterialTheme.colorScheme.background))},
                    bottomBar={if(!wide)Column { HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant);NavigationBar(containerColor=MaterialTheme.colorScheme.surface,tonalElevation=0.dp) { Tabs.forEachIndexed { i,t -> NavigationBarItem(selected=tab==i && extra==null,onClick={tab=i;extra=null;community=null},icon={Icon(t.icon,t.label)},label={Text(if(i==1)if(androidx.compose.ui.platform.LocalDensity.current.fontScale>1.3f)"Groups" else "Community" else if(i==3)"Ranks" else t.label,fontSize=10.sp,maxLines=1,overflow=TextOverflow.Ellipsis)},colors=NavigationBarItemDefaults.colors(indicatorColor=Violet.copy(alpha=.10f),selectedIconColor=Violet,selectedTextColor=Violet)) } } }},
                    snackbarHost={SnackbarHost(snack)}) { padding ->
                    Column(Modifier.fillMaxSize().padding(padding)) {
                        data.bootError?.let { Row(Modifier.fillMaxWidth().padding(horizontal=20.dp),verticalAlignment=Alignment.CenterVertically) { Text(it,Modifier.weight(1f),color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall);TextButton(onClick={vm.bootstrap()}) { Text("Retry") } } }
                        if(tab==0 && extra==null)Segmented(listOf("Markets","Launch","Swipe","Feed"),home,{home=it},Modifier.padding(horizontal=20.dp,vertical=8.dp))
                        AnimatedContent(targetState=extra ?: "$tab:${if(tab==0)home else community.orEmpty()}",transitionSpec={fadeIn(tween(150)) togetherWith fadeOut(tween(100))},label="screen") { destination ->
                            when {
                                destination=="Algorithms"->AlgorithmsScreen(vm,{algorithm=it})
                                destination=="Agents"->AgentsScreen(data)
                                destination=="Activity"->ActivityScreen(vm)
                                destination=="0:Markets"->MarketsScreen(vm,{asset=it})
                                destination=="0:Launch"->MarketsScreen(vm,{asset=it},launch=true,create={openBrowser(Uri.parse(ORIGIN+"/native-wallet").buildUpon().appendQueryParameter("nativeAction","launch").appendQueryParameter("account",vm.me?.string("id")).build().toString())})
                                destination=="0:Swipe"->SwipeScreen(vm,{asset=it})
                                destination=="0:Feed"->FeedScreen(vm,onPost={post=it},onAsset=::showAsset,compose={if(vm.me!=null)composing=true else tab=4},onAlgorithm={extra="Algorithms"})
                                destination.startsWith("1:") && community!=null->FeedScreen(vm,community=community,onPost={post=it},onAsset=::showAsset,compose={if(vm.me!=null)composing=true else tab=4})
                                destination.startsWith("1:")->CommunitiesScreen(vm,{community=it})
                                destination.startsWith("2:")->DiscoverScreen(vm,onPost={post=it},onAlgorithm={algorithm=it})
                                destination.startsWith("3:")->LeaderboardScreen(vm,{algorithm=it})
                                else->ProfileScreen(vm,openBrowser,{extra=it})
                            }
                        }
                    }
                }
            }
        }
        asset?.let { selected -> AssetSheet(selected,vm,{asset=null},openBrowser) }
        post?.let { selected -> PostSheet(selected,vm,{post=null},::showAsset,openBrowser) }
        algorithm?.let { selected -> AlgorithmSheet(selected,vm,{algorithm=null},openBrowser) }
        if(composing)ComposeSheet(vm,community,{composing=false})
    }
}
@Composable fun Segmented(options: List<String>,selected: String,onSelect: (String)->Unit,modifier: Modifier=Modifier) {
    Row(modifier.fillMaxWidth().clip(RoundedCornerShape(16.dp)).background(MaterialTheme.colorScheme.surfaceContainer).padding(4.dp)) {
        options.forEach { option -> val active=option==selected; val color by animateColorAsState(if(active)MaterialTheme.colorScheme.surface else Color.Transparent,label="selection")
            Box(Modifier.weight(1f).heightIn(min=44.dp).clip(RoundedCornerShape(12.dp)).background(color).clickable(role=Role.Tab,onClick={onSelect(option)}).semantics { this.selected=active }.padding(horizontal=4.dp,vertical=12.dp),contentAlignment=Alignment.Center) { Text(option,maxLines=1,fontSize=13.sp,fontWeight=if(active)FontWeight.SemiBold else FontWeight.Normal,color=if(active)MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant) }
        }
    }
}
@Composable fun Artwork(url: String?,label: String,size: Dp=48.dp,round: Boolean=true) {
    Box(Modifier.size(size).clip(if(round)CircleShape else RoundedCornerShape(14.dp)).background(MaterialTheme.colorScheme.surfaceContainer),contentAlignment=Alignment.Center) {
        val fallback: @Composable ()->Unit = { Text(label.take(2).uppercase(),fontSize=(size.value*.28f).sp,color=MaterialTheme.colorScheme.onSurfaceVariant,fontWeight=FontWeight.Medium) }
        if(url!=null)SubcomposeAsyncImage(url,contentDescription=label,modifier=Modifier.fillMaxSize(),contentScale=androidx.compose.ui.layout.ContentScale.Crop,loading={fallback()},error={fallback()}) else fallback()
    }
}
@Composable fun EmptyState(title: String,detail: String?=null,action: String?=null,onAction: ()->Unit={}) {
    Column(Modifier.fillMaxWidth().padding(horizontal=32.dp,vertical=48.dp),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(12.dp)) {
        Text(title,style=MaterialTheme.typography.titleMedium);detail?.let { Text(it,color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodyMedium,textAlign=androidx.compose.ui.text.style.TextAlign.Center) };if(action!=null)TextButton(onClick=onAction){Text(action)}
    }
}
@Composable fun LoadingRows() {
    Column(Modifier.padding(20.dp),verticalArrangement=Arrangement.spacedBy(24.dp)) { repeat(7) { Row(verticalAlignment=Alignment.CenterVertically) { Box(Modifier.size(48.dp).clip(CircleShape).background(MaterialTheme.colorScheme.surfaceContainer));Spacer(Modifier.width(14.dp));Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(10.dp)) { Box(Modifier.width(100.dp).height(13.dp).clip(RoundedCornerShape(4.dp)).background(MaterialTheme.colorScheme.surfaceContainer));Box(Modifier.width(60.dp).height(10.dp).clip(RoundedCornerShape(4.dp)).background(MaterialTheme.colorScheme.surfaceContainer)) };Box(Modifier.width(75.dp).height(14.dp).clip(RoundedCornerShape(4.dp)).background(MaterialTheme.colorScheme.surfaceContainer)) } } }
}
