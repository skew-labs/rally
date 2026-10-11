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
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalContext
import androidx.compose.ui.platform.LocalUriHandler
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.compose.ui.graphics.luminance
import kotlinx.coroutines.*
import okhttp3.OkHttpClient
import okhttp3.Request
import okio.Buffer
import org.json.JSONObject
import java.io.IOException
import java.net.URI
import java.util.concurrent.TimeUnit

fun validateAlgorithmReferences(data: JSONObject): List<JSONObject> {
    val entries=data.objects("items")
    require(data.optInt("version")==1 && entries.size==100 && entries.map { it.string("id") }.toSet().size==100) { "Algorithms unavailable" }
    entries.forEach { a->
        require(a.string("status")=="reference" && Regex("rally-ref-\\d{3}").matches(a.string("id")))
        require(Regex("/assets/algorithm-ref-\\d{3}-[a-f0-9]{16}\\.png").matches(a.string("icon")))
        val uri=URI(a.string("sourceURL"));require(uri.scheme=="https" && !uri.host.isNullOrBlank() && uri.userInfo==null)
        for(field in listOf("brandIcon","brandIconDark"))if(!a.isNull(field))require(Regex("/assets/algorithm-brand-[a-z0-9-]+-[a-f0-9]{16}\\.png").matches(a.string(field)))
        a.optJSONObject("performance1Y")?.let { p->
            require(p.string("basis")=="published_factor" && p.optInt("months")==12 && p.number("returnPct")?.let { it.isFinite() && it > -100 }==true)
            val from=java.time.LocalDate.parse(p.string("from"));val to=java.time.LocalDate.parse(p.string("to"))
            require(from.dayOfMonth==1 && to.dayOfMonth==to.lengthOfMonth() && java.time.temporal.ChronoUnit.MONTHS.between(from.withDayOfMonth(1),to.withDayOfMonth(1))==11L && !to.isAfter(java.time.LocalDate.now(java.time.ZoneOffset.UTC)))
            require(p.string("sourceURL").startsWith("https://www.aqr.com/"))
        }
        require(!a.has("price") && !a.has("performance") && !a.has("tradeEnabled"))
    }
    return entries
}
private object PublicAlgorithmReferences {
    @Volatile var cache: JSONObject?=null
    private val client=OkHttpClient.Builder().connectTimeout(8,TimeUnit.SECONDS).callTimeout(12,TimeUnit.SECONDS).followRedirects(false).build()
    suspend fun load(): JSONObject=withContext(Dispatchers.IO) {
        cache?.let { return@withContext it }
        // Independent public read: no account cookies, wallet SDK or mutation method.
        client.newCall(Request.Builder().url(ORIGIN+ALGORITHM_LIBRARY_URL).header("Accept","application/json").build()).execute().use { response->
            if(!response.isSuccessful)throw IOException("Algorithms unavailable. Try again.")
            val body=response.body ?: throw IOException("Empty catalog")
            val input=body.source();val buffer=Buffer()
            while(buffer.size<=400_000 && input.read(buffer,(400_001-buffer.size).coerceAtMost(8192)) != -1L) { }
            if(buffer.size>400_000)throw IOException("Catalog is too large")
            val data=JSONObject(buffer.readUtf8());validateAlgorithmReferences(data);cache=data;data
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun UnifiedAlgorithms(vm: RallyViewModel,onAlgorithm: (JSONObject)->Unit) {
    val app by vm.state.collectAsStateWithLifecycle()
    var filter by rememberSaveable { mutableStateOf("All") };var rank by rememberSaveable { mutableStateOf("Top PnL") }
    val context=LocalContext.current;val links=LocalUriHandler.current
    val preferences=remember(context){context.getSharedPreferences("rally-reference-library",0)}
    var saved by remember { mutableStateOf(preferences.getStringSet("saved",emptySet()).orEmpty().toSet()) }
    var data by remember { mutableStateOf(PublicAlgorithmReferences.cache) };var error by remember { mutableStateOf<String?>(null) };var retry by remember { mutableIntStateOf(0) }
    var query by rememberSaveable { mutableStateOf("") };var source by rememberSaveable { mutableStateOf("") };var category by rememberSaveable { mutableStateOf("") };var onlySaved by rememberSaveable { mutableStateOf(false) }
    var selected by remember { mutableStateOf<JSONObject?>(null) }
    val save: (String)->Unit={id->val next=if(id in saved)saved-id else saved+id;saved=next;preferences.edit().putStringSet("saved",next).apply()}
    LaunchedEffect(retry) { if(data==null){error=null;try { data=PublicAlgorithmReferences.load() } catch(e:CancellationException){throw e} catch(e:Exception){error="Can't load strategies. Check your connection and retry."}} }
    val entries=data?.objects("items").orEmpty()
    val filtered=remember(entries,query,source,category,onlySaved,saved,filter){entries.filter { a->filter!="Paid" && (!onlySaved || a.string("id") in saved) && (source.isEmpty() || a.string("sourceId")==source) && (category.isEmpty() || a.string("category")==category) && query.trim().split(Regex("\\s+")).all { word->listOf("name","method","author","sourceName","rule").joinToString(" "){a.string(it)}.contains(word,true) } }}
    val feeds=rankedAlgorithms(app.boot?.objects("feeds").orEmpty(),rank=="Top ROI").filter { f->
        !onlySaved && source.isEmpty() && category.isEmpty() && (filter!="Free" || (f.number("price") ?: 0.0)==0.0) && (filter!="Paid" || (f.number("price") ?: 0.0)>0.0) && (algorithmTitle(f)+" "+algorithmOwner(f)).contains(query,true)
    }
    LazyColumn(Modifier.fillMaxSize().highRefresh(),contentPadding=PaddingValues(16.dp)) {
        item {
            OutlinedTextField(query,{query=it},Modifier.fillMaxWidth(),singleLine=true,placeholder={Text("Search algorithms, wallets, sources",fontSize=13.sp)},leadingIcon={Icon(Icons.Outlined.Search,null)},shape=RoundedCornerShape(16.dp))
            Segmented(listOf("All","Free","Paid"),filter,{filter=it},Modifier.padding(vertical=8.dp))
            Segmented(listOf("Top PnL","Top ROI"),rank,{rank=it})
        }
        items(feeds,key={it.string("id")},contentType={"feed"}) { f->AlgorithmListRow(f){onAlgorithm(algorithmItem(f))} }
        if(filter!="Paid")item {
            Row(Modifier.fillMaxWidth().padding(top=22.dp),verticalAlignment=Alignment.CenterVertically) { Text("Strategies",Modifier.weight(1f),fontWeight=FontWeight.Medium);FilterChip(selected=onlySaved,onClick={onlySaved=!onlySaved},label={Text("Saved")},leadingIcon={Icon(Icons.Outlined.BookmarkBorder,null,Modifier.size(16.dp))}) }
            LazyRow(Modifier.padding(vertical=10.dp),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                item { FilterChip(selected=source.isEmpty(),onClick={source=""},label={Text("All sources")}) }
                items(data?.objects("sources").orEmpty(),key={it.string("id")}) { b->FilterChip(selected=source==b.string("id"),onClick={source=if(source==b.string("id"))"" else b.string("id")},label={Text(b.string("name"),fontSize=12.sp)},leadingIcon={AlgorithmBrand(JSONObject().put("brandIcon",b.string("logo")).put("brandIconDark",b.string("logoDark")),24.dp)}) }
            }
            LazyRow(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                item { FilterChip(selected=category.isEmpty(),onClick={category=""},label={Text("All strategies")}) }
                items(entries.map { it.string("category") }.distinct()) { g->FilterChip(selected=category==g,onClick={category=if(category==g)"" else g},label={Text(g,fontSize=12.sp)}) }
            }
            Text("${filtered.size} algorithms · 1Y model = published factor",Modifier.padding(vertical=14.dp),fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if(filter!="Paid" && data==null && error==null)item { LoadingRows() }
        if(filter!="Paid" && error!=null)item { EmptyState("Algorithms unavailable",error.orEmpty(),"Retry",{retry++}) }
        items(filtered,key={it.string("id")},contentType={"reference"}) { a->
            Row(Modifier.fillMaxWidth().heightIn(min=92.dp),verticalAlignment=Alignment.CenterVertically) {
                Row(Modifier.weight(1f).clickable { selected=a }.padding(vertical=12.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)) {
                    AlgorithmBrand(a,44.dp)
                    Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                        Text(a.string("name"),fontSize=14.sp,fontWeight=FontWeight.Medium,maxLines=2,overflow=TextOverflow.Ellipsis)
                        Text(a.string("category"),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis)
                    }
                    Column(horizontalAlignment=Alignment.End) {
                        val record=a.optJSONObject("performance1Y")
                        Text(record?.number("returnPct")?.let(::algorithmPercent) ?: "—",fontSize=16.sp,fontWeight=FontWeight.Medium,color=if(record?.number("returnPct")==null)MaterialTheme.colorScheme.onSurface else performanceInk(record.number("returnPct")!!))
                        Text(if(record!=null)"1Y model" else "1Y return",fontSize=9.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                }
                IconToggleButton(checked=a.string("id") in saved,onCheckedChange={save(a.string("id"))},modifier=Modifier.size(48.dp).semantics { contentDescription="Save "+a.string("name") }) { Icon(if(a.string("id") in saved)Icons.Outlined.Bookmark else Icons.Outlined.BookmarkBorder,null,Modifier.size(19.dp)) }
            };HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant.copy(alpha=.5f))
        }
        if(filter!="Paid" && data!=null && filtered.isEmpty())item { EmptyState("No matching strategies","Try another source or search.") }
    }
    selected?.let { a->
        ModalBottomSheet(onDismissRequest={selected=null},sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true)) {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal=22.dp).navigationBarsPadding(),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(14.dp)) { AlgorithmBrand(a,64.dp);Column(Modifier.weight(1f)){Text(a.string("name"),fontSize=23.sp,fontWeight=FontWeight.Medium);Text(a.string("category"),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)} }
                val record=a.optJSONObject("performance1Y")
                Text(record?.number("returnPct")?.let(::algorithmPercent) ?: "—",fontSize=36.sp,fontWeight=FontWeight.Medium,color=if(record?.number("returnPct")==null)MaterialTheme.colorScheme.onSurface else performanceInk(record.number("returnPct")!!))
                Text(if(record==null)"No complete 1Y record published." else "1Y model · ${record.string("from")} — ${record.string("to")}",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                if(record!=null)Text("${record.string("universe")} · Hypothetical compounded factor excess returns; fees excluded. These are research results, not Rally trading returns.",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                Text(a.string("method"),fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                Text(a.string("rule"),fontSize=17.sp,lineHeight=26.sp)
                Button(onClick={save(a.string("id"))},Modifier.fillMaxWidth().heightIn(min=48.dp),shape=RoundedCornerShape(100.dp)){Text(if(a.string("id") in saved)"Saved" else "Save",fontSize=13.sp)}
                Column(Modifier.fillMaxWidth().padding(bottom=20.dp),horizontalAlignment=Alignment.End,verticalArrangement=Arrangement.spacedBy(4.dp)) {
                    Text("Source: "+a.string("sourceName",a.string("author")),Modifier.clickable { runCatching { links.openUri(a.string("sourceURL")) } }.padding(vertical=8.dp),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Independent Rally research · No affiliation",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}

@Composable private fun AlgorithmBrand(a: JSONObject,size: Dp) {
    val dark=MaterialTheme.colorScheme.surface.luminance()<.4f
    val logo=if(dark)a.string("brandIconDark",a.string("brandIcon",a.string("icon"))) else a.string("brandIcon",a.string("icon"))
    Artwork(safeImage(logo),a.string("name"),size,false)
}
