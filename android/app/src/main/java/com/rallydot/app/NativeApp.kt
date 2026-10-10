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
import androidx.compose.runtime.saveable.rememberSaveableStateHolder
import androidx.compose.ui.*
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.graphicsLayer
import androidx.compose.ui.graphics.vector.ImageVector
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import coil.compose.AsyncImage
import coil.request.ImageRequest
import androidx.compose.ui.platform.LocalView
import androidx.compose.ui.graphics.toArgb
import androidx.core.view.WindowCompat
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import kotlinx.coroutines.launch
import org.json.JSONObject

val Violet=Color(0xFF765AF2)
val Buy=Color(0xFF0866FF)
val Sell=Color(0xFFD62F49)
val Gain=Color(0xFF12845A)
@Composable fun RallyTheme(dark: Boolean,content: @Composable ()->Unit) {
    val scheme=if(dark)darkColorScheme(primary=Color(0xFFAD96FF),background=Color(0xFF18181C),surface=Color(0xFF18181C),surfaceContainer=Color(0xFF24242B),surfaceVariant=Color(0xFF1E1E23),onSurface=Color(0xFFEDEDF2),onSurfaceVariant=Color(0xFFA0A0B0),outlineVariant=Color(0xFF2A2A32),tertiary=Color(0xFF75D1AD),error=Color(0xFFFF8797))
        else lightColorScheme(primary=Violet,background=Color.White,surface=Color.White,surfaceContainer=Color(0xFFF0F0F4),surfaceVariant=Color(0xFFF9F9FB),onSurface=Color(0xFF202024),onSurfaceVariant=Color(0xFF686873),outlineVariant=Color(0xFFECECF0),tertiary=Color(0xFF188461),error=Color(0xFFD94C60))
    MaterialTheme(colorScheme=scheme,typography=RallyTypography,content=content)
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
    var launching by rememberSaveable { mutableStateOf(false) }
    var composing by rememberSaveable { mutableStateOf(false) }
    val scope=rememberCoroutineScope()
    val screenStates=rememberSaveableStateHolder()
    val rememberedDestinations=remember { linkedSetOf<String>() }
    val accountId=data.boot?.optJSONObject("me")?.string("id") ?: "guest"
    LaunchedEffect(accountId) {
        rememberedDestinations.forEach { screenStates.removeState(it) }
        rememberedDestinations.clear()
    }
    val snack=remember { SnackbarHostState() }
    LaunchedEffect(data.message) { data.message?.let { snack.showSnackbar(it);vm.message(null) } }
    fun showAsset(id: String) {
        if(id.startsWith("signals:")){extra="Signals:"+id.removePrefix("signals:");return}
        if(id.startsWith("perpl:")){scope.launch {try{val m=vm.api.get("/api/perps",true).objects("markets").firstOrNull {it.string("id")==id.removePrefix("perpl:")&&it.string("venue")=="Perpl"};if(m!=null)asset=Asset.parse(m,"perps") else vm.message("Perpl market unavailable")}catch(e:Exception){vm.message(e.message)}};return}
        val rows=data.pages.values.flatMap { it.items }
        val known=rows.firstOrNull { it.string("id")==id || it.string("address")==id } ?: rows.mapNotNull { it.optJSONObject("assetInfo") }.firstOrNull { it.string("id",it.string("address"))==id }
        if(known!=null && known.has("symbol")) { asset=Asset.parse(known);return }
        scope.launch { try {
            val token=vm.resolveAsset(id)
            if(token!=null)asset=token else vm.message("Token details unavailable")
        } catch(e:Exception) { vm.message(e.message ?: "Could not load token") } }
    }
    LaunchedEffect(link) {
        if(link?.scheme=="https" && link.host=="rallydot.com") {
            if(link.getQueryParameter("view")=="token")(link.getQueryParameter("id") ?: link.getQueryParameter("token"))?.let(::showAsset)
            if(link.getQueryParameter("view")=="post")(link.getQueryParameter("id") ?: link.getQueryParameter("post"))?.let { id->scope.launch { try{post=Post.parse(vm.api.get("/api/post?id="+Uri.encode(id),true))}catch(e:Exception){vm.message(e.message)} } }
            when(link.getQueryParameter("view")) { "notifications"->{tab=4;extra="Notifications"};"communities"->tab=1;"discover"->tab=2;"leaderboard"->tab=3;"account","agents","feeds","earnings"->tab=4;"launchpad"->{tab=0;home="Launch"};"swipe"->{tab=0;home="Swipe"};"home"->{tab=0;home=when(link.getQueryParameter("section")){"feed"->"Feed";"launchpad"->"Launch";"swipe"->"Swipe";else->"Markets"}} }
        }
    }
    BackHandler(asset==null && post==null && algorithm==null && !composing && (extra!=null || community!=null || tab!=0 || home!="Markets")) {
        when { extra!=null->extra=null;community!=null->community=null;tab!=0->tab=0;else->home="Markets" }
    }
    RallyTheme(dark) {
        val view=LocalView.current
        val background=MaterialTheme.colorScheme.background.toArgb()
        SideEffect {
            var owner: Context=view.context
            while(owner is android.content.ContextWrapper && owner !is android.app.Activity)owner=owner.baseContext
            (owner as? android.app.Activity)?.window?.let { window ->
                window.decorView.setBackgroundColor(background)
                WindowCompat.getInsetsController(window,view).apply {
                    isAppearanceLightStatusBars=!dark
                    isAppearanceLightNavigationBars=!dark
                }
            }
        }
        val title=extra?.let {if(it.startsWith("Benefits:"))"Token benefits" else if(it.startsWith("Signals:"))"Signal record" else it} ?: when { tab==0->"rally.";tab==1 && community!=null->data.boot?.objects("communities")?.firstOrNull { it.string("id")==community }?.string("name") ?: "Community";else->Tabs[tab].label }
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
                    topBar={TopAppBar(title={if(tab==0 && extra==null)RallyBrand() else Text(title,maxLines=1,overflow=TextOverflow.Ellipsis,fontWeight=FontWeight.SemiBold,fontSize=25.sp)},navigationIcon={if(extra!=null || community!=null)IconButton(onClick={extra=null;community=null}){Icon(Icons.Outlined.ArrowBack,"Back")}},actions={
                        IconButton(onClick={dark=!dark;settings.edit().putBoolean("dark",dark).apply();if(android.os.Build.VERSION.SDK_INT>=31)context.getSystemService(android.app.UiModeManager::class.java).setApplicationNightMode(if(dark)android.app.UiModeManager.MODE_NIGHT_YES else android.app.UiModeManager.MODE_NIGHT_NO)}) { Icon(if(dark)Icons.Outlined.LightMode else Icons.Outlined.DarkMode,"Change theme") }
                        if(tab==0)IconButton(onClick={tab=2}) { Icon(Icons.Outlined.Search,"Search") }
                    },colors=TopAppBarDefaults.topAppBarColors(containerColor=MaterialTheme.colorScheme.background))},
                    bottomBar={if(!wide)RallyNavigation(tab) { tab=it;extra=null;community=null }},
                    snackbarHost={SnackbarHost(snack)}) { padding ->
                    Column(Modifier.fillMaxSize().padding(padding)) {
                        if(data.order.blocksOrder && asset==null && algorithm==null && !launching)Box(Modifier.padding(horizontal=20.dp,vertical=6.dp).clickable { extra="Wallet" }) { OrderStatus(vm,compact=true) }
                        data.bootError?.let { Row(Modifier.fillMaxWidth().padding(horizontal=20.dp),verticalAlignment=Alignment.CenterVertically) { Text(it,Modifier.weight(1f),color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall);TextButton(onClick={vm.bootstrap()}) { Text("Retry") } } }
                        if(tab==0 && extra==null)Segmented(listOf("Markets","Launch","Swipe","Feed"),home,{home=it},Modifier.padding(horizontal=20.dp,vertical=8.dp))
                        val destination=extra ?: "$tab:${if(tab==0)home else community.orEmpty()}"
                        LaunchedEffect(destination,accountId) {
                            val stateKey="$accountId/$destination"
                            rememberedDestinations.remove(stateKey);rememberedDestinations.add(stateKey)
                            while(rememberedDestinations.size>20)screenStates.removeState(rememberedDestinations.first().also { rememberedDestinations.remove(it) })
                        }
                        AnimatedContent(targetState=destination,modifier=Modifier.weight(1f).fillMaxWidth().highRefresh(),transitionSpec={
                            val homeOptions=listOf("0:Markets","0:Launch","0:Swipe","0:Feed")
                            val from=homeOptions.indexOf(initialState);val to=homeOptions.indexOf(targetState)
                            val direction=if(to>from)1 else -1
                            if(from>=0 && to>=0)
                                (fadeIn(tween(150))+slideInHorizontally(tween(180)) { direction*it/40 }) togetherWith
                                    fadeOut(tween(80)) using SizeTransform(clip=false)
                            else fadeIn(tween(120)) togetherWith fadeOut(tween(70)) using SizeTransform(clip=false)
                        },label="screen") { shown ->
                            screenStates.SaveableStateProvider("$accountId/$shown") {
                                when {
                                    shown=="Notifications"->NotificationsScreen(vm,{post=it},::showAsset)
                                    shown=="Share trades"->ShareTradesScreen(vm,{post=it})
                                    shown=="Signal record"->SignalRecordScreen(vm,{post=it})
                                    shown.startsWith("Signals:")->SignalRecordScreen(vm,{post=it},shown.substringAfter(":"))
                                    shown=="Weekly league"->WeeklyLeagueScreen(vm)
                                    shown.startsWith("Benefits:")->TokenBenefitsScreen(vm,shown.substringAfter(":"))
                                    shown=="Token benefits"->TokenBenefitsScreen(vm,vm.me?.string("id").orEmpty())
                                    shown=="Algorithms"->AlgorithmsScreen(vm,{algorithm=it})
                                    shown=="Agents"->AgentsScreen(data)
                                    shown=="Activity"->ActivityScreen(vm)
                                    shown=="Wallet"->PortfolioScreen(vm,::showAsset)
                                    shown=="0:Markets"->MarketsScreen(vm,{asset=it})
                                    shown=="0:Launch"->MarketsScreen(vm,{asset=it},launch=true,create={if(vm.me==null)vm.showWallet() else launching=true})
                                    shown=="0:Swipe"->SwipeScreen(vm,{asset=it},{post=it})
                                    shown=="0:Feed"->FeedScreen(vm,onPost={post=it},onAsset=::showAsset,compose={if(vm.me!=null)composing=true else tab=4},onAlgorithm={extra="Algorithms"})
                                    shown.startsWith("1:") && shown.substringAfter(':').isNotEmpty()->FeedScreen(vm,community=shown.substringAfter(':'),onPost={post=it},onAsset=::showAsset,compose={if(vm.me!=null)composing=true else tab=4})
                                    shown.startsWith("1:")->CommunitiesScreen(vm,{community=it},{extra="Benefits:$it"})
                                    shown.startsWith("2:")->DiscoverScreen(vm,onPost={post=it},onAlgorithm={algorithm=it})
                                    shown.startsWith("3:")->LeaderboardScreen(vm,{algorithm=it},{extra="Weekly league"})
                                    else->ProfileScreen(vm,openBrowser,{extra=it})
                                }
                            }
                        }
                    }
                }
            }
        }
        asset?.let { selected -> AssetSheet(selected,vm,{asset=null},openBrowser) }
        post?.let { selected -> PostSheet(selected,vm,{post=null},::showAsset,openBrowser) }
        algorithm?.let { selected -> AlgorithmSheet(selected,vm,{algorithm=null},openBrowser) }
        if(data.orderDetails)OrderDetailsSheet(vm,{vm.showOrderDetails(false)})
        data.walletPanel?.let { WalletAssetsSheet(vm,it,{vm.showWalletPanel(null)}) }
        if(data.walletOpen)WalletLoginSheet(vm,{vm.showWallet(false)},openBrowser)
        if(launching)LaunchSheet(vm,{launching=false})
        if(composing)ComposeSheet(vm,community,{composing=false})
    }
}
@Composable fun Segmented(options: List<String>,selected: String,onSelect: (String)->Unit,modifier: Modifier=Modifier,accent: Color?=null) {
    val active=options.indexOf(selected).coerceAtLeast(0)
    val haptic=LocalHapticFeedback.current
    val largeText=androidx.compose.ui.platform.LocalDensity.current.fontScale>1.3f
    BoxWithConstraints(modifier.fillMaxWidth().clip(RoundedCornerShape(100.dp)).background(MaterialTheme.colorScheme.surfaceContainer).padding(4.dp)) {
        val cell=maxWidth/options.size
        val offset=animateDpAsState(cell*active,animationSpec=spring(dampingRatio=1f,stiffness=700f),label="selected tab")
        Box(Modifier.matchParentSize().padding(end=(maxWidth-cell).coerceAtLeast(0.dp)).graphicsLayer { translationX=offset.value.toPx() }.clip(RoundedCornerShape(100.dp)).background(MaterialTheme.colorScheme.surface).highRefresh())
        Row(Modifier.fillMaxWidth()) {
            options.forEach { option -> val chosen=option==selected
                Box(Modifier.weight(1f).heightIn(min=44.dp).clip(RoundedCornerShape(100.dp)).clickable(role=Role.Tab,onClick={if(!chosen) { haptic.performHapticFeedback(HapticFeedbackType.SegmentTick);onSelect(option) } }).semantics { this.selected=chosen;contentDescription=option }.padding(horizontal=4.dp,vertical=12.dp),contentAlignment=Alignment.Center) {
                    Text(if(largeText && option=="Prediction")"Predict" else option,maxLines=1,overflow=TextOverflow.Ellipsis,fontSize=13.sp,fontWeight=if(chosen)FontWeight.Medium else FontWeight.Normal,color=if(chosen)accent ?: MaterialTheme.colorScheme.onSurface else MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}
@Composable fun Artwork(url: String?,label: String,size: Dp=48.dp,round: Boolean=true) {
    val context=LocalContext.current
    val density=androidx.compose.ui.platform.LocalDensity.current
    val pixels=with(density) { size.roundToPx() }.coerceAtLeast(1)
    val request=remember(url,context,pixels) {
        val artwork: Any?=when(url) {
            ORIGIN+"/assets/agent-meta.svg"->R.drawable.brand_meta
            ORIGIN+"/assets/agent-grok.svg"->R.drawable.brand_grok
            else->url
        }
        ImageRequest.Builder(context).data(artwork).size(pixels).crossfade(if(android.os.Build.VERSION.SDK_INT>=26 && !android.animation.ValueAnimator.areAnimatorsEnabled())0 else 100).build()
    }
    var loaded by remember(url) { mutableStateOf(false) }
    val companyLogo=url?.startsWith(ORIGIN+"/assets/agent-")==true
    Box(Modifier.size(size).clip(if(round)CircleShape else RoundedCornerShape(14.dp)).background(if(companyLogo)Color.White else MaterialTheme.colorScheme.surfaceContainer),contentAlignment=Alignment.Center) {
        if(!loaded)Text(label.take(2).uppercase(),fontSize=(size.value*.28f).sp,color=if(companyLogo)Color(0xFF727785) else MaterialTheme.colorScheme.onSurfaceVariant,fontWeight=FontWeight.Medium)
        if(url!=null)AsyncImage(request,contentDescription=label,onSuccess={loaded=true},onError={loaded=false},modifier=Modifier.fillMaxSize(),contentScale=androidx.compose.ui.layout.ContentScale.Crop)
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
