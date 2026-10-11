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
    require(data.optInt("version")==1 && entries.size==100 && entries.map { it.string("id") }.toSet().size==100) { "Library unavailable" }
    entries.forEach { a->
        require(a.string("status")=="reference" && Regex("rally-ref-\\d{3}").matches(a.string("id")))
        require(Regex("/assets/algorithm-ref-\\d{3}-[a-f0-9]{16}\\.png").matches(a.string("icon")))
        val uri=URI(a.string("sourceURL"));require(uri.scheme=="https" && !uri.host.isNullOrBlank() && uri.userInfo==null)
        if(!a.isNull("brandIcon"))require(Regex("/assets/algorithm-brand-[a-z0-9-]+-[a-f0-9]{16}\\.png").matches(a.string("brandIcon")))
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
            if(!response.isSuccessful)throw IOException("Library unavailable. Try again.")
            val body=response.body ?: throw IOException("Empty library")
            val input=body.source();val buffer=Buffer()
            while(buffer.size<=400_000 && input.read(buffer,(400_001-buffer.size).coerceAtMost(8192)) != -1L) { }
            if(buffer.size>400_000)throw IOException("Library is too large")
            val data=JSONObject(buffer.readUtf8());validateAlgorithmReferences(data);cache=data;data
        }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun AlgorithmReferenceLibrary() {
    val context=LocalContext.current;val links=LocalUriHandler.current
    val preferences=remember(context){context.getSharedPreferences("rally-reference-library",0)}
    var saved by remember { mutableStateOf(preferences.getStringSet("saved",emptySet()).orEmpty().toSet()) }
    var data by remember { mutableStateOf(PublicAlgorithmReferences.cache) };var error by remember { mutableStateOf<String?>(null) };var retry by remember { mutableIntStateOf(0) }
    var query by rememberSaveable { mutableStateOf("") };var source by rememberSaveable { mutableStateOf("") };var category by rememberSaveable { mutableStateOf("") };var onlySaved by rememberSaveable { mutableStateOf(false) }
    var selected by remember { mutableStateOf<JSONObject?>(null) }
    val save: (String)->Unit={id->val next=if(id in saved)saved-id else saved+id;saved=next;preferences.edit().putStringSet("saved",next).apply()}
    LaunchedEffect(retry) { if(data==null){error=null;try { data=PublicAlgorithmReferences.load() } catch(e:CancellationException){throw e} catch(e:Exception){error="Can't load the library. Check your connection and retry."}} }
    val entries=data?.objects("items").orEmpty()
    val filtered=remember(entries,query,source,category,onlySaved,saved){entries.filter { a->(!onlySaved || a.string("id") in saved) && (source.isEmpty() || a.string("sourceId")==source) && (category.isEmpty() || a.string("category")==category) && query.trim().split(Regex("\\s+")).all { word->listOf("name","method","author","sourceName","rule").joinToString(" "){a.string(it)}.contains(word,true) } }}
    LazyColumn(Modifier.fillMaxSize().highRefresh(),contentPadding=PaddingValues(16.dp)) {
        item {
            OutlinedTextField(query,{query=it},Modifier.fillMaxWidth(),singleLine=true,placeholder={Text("Search strategies or sources",fontSize=13.sp)},leadingIcon={Icon(Icons.Outlined.Search,null)},shape=RoundedCornerShape(16.dp))
            LazyRow(Modifier.padding(vertical=10.dp),horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                item { FilterChip(selected=source.isEmpty(),onClick={source=""},label={Text("All sources")}) }
                items(data?.objects("sources").orEmpty(),key={it.string("id")}) { b->FilterChip(selected=source==b.string("id"),onClick={source=if(source==b.string("id"))"" else b.string("id")},label={Text(b.string("name"),fontSize=12.sp)}) }
            }
            LazyRow(horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                item { FilterChip(selected=onlySaved,onClick={onlySaved=!onlySaved},label={Text("Saved")},leadingIcon={Icon(Icons.Outlined.BookmarkBorder,null,Modifier.size(16.dp))}) }
                item { FilterChip(selected=category.isEmpty(),onClick={category=""},label={Text("All methods")}) }
                items(entries.map { it.string("category") }.distinct()) { g->FilterChip(selected=category==g,onClick={category=if(category==g)"" else g},label={Text(g,fontSize=12.sp)}) }
            }
            Text("${filtered.size} in library",Modifier.padding(vertical=14.dp),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
        }
        if(data==null && error==null)item { LoadingRows() }
        if(error!=null)item { EmptyState("Library unavailable",error.orEmpty(),"Retry",{retry++}) }
        items(filtered,key={it.string("id")},contentType={"reference"}) { a->
            Row(Modifier.fillMaxWidth().heightIn(min=92.dp),verticalAlignment=Alignment.CenterVertically) {
                Row(Modifier.weight(1f).clickable { selected=a }.padding(vertical=12.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(10.dp)) {
                    Artwork(safeImage(a.string("brandIcon",a.string("icon"))),a.string("name"),52.dp,false)
                    Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(4.dp)) {
                        Text(a.string("name"),fontSize=14.sp,fontWeight=FontWeight.Medium,maxLines=2,overflow=TextOverflow.Ellipsis)
                        Text(a.string("category"),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis)
                    }
                }
                IconToggleButton(checked=a.string("id") in saved,onCheckedChange={save(a.string("id"))},modifier=Modifier.size(48.dp).semantics { contentDescription="Save "+a.string("name") }) { Icon(if(a.string("id") in saved)Icons.Outlined.Bookmark else Icons.Outlined.BookmarkBorder,null,Modifier.size(19.dp)) }
            };HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant.copy(alpha=.5f))
        }
        if(data!=null && filtered.isEmpty())item { EmptyState("No references found","Try another source or search.") }
    }
    selected?.let { a->
        ModalBottomSheet(onDismissRequest={selected=null},sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true)) {
            Column(Modifier.fillMaxWidth().verticalScroll(rememberScrollState()).padding(horizontal=22.dp).navigationBarsPadding(),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(14.dp)) { Artwork(safeImage(a.string("brandIcon",a.string("icon"))),a.string("name"),64.dp,false);Column(Modifier.weight(1f)){Text(a.string("name"),fontSize=23.sp,fontWeight=FontWeight.Medium);Text(a.string("category"),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)} }
                Text(a.string("method"),fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                Text(a.string("rule"),fontSize=17.sp,lineHeight=26.sp)
                Button(onClick={save(a.string("id"))},Modifier.fillMaxWidth().heightIn(min=48.dp),shape=RoundedCornerShape(100.dp)){Text(if(a.string("id") in saved)"Saved" else "Save",fontSize=13.sp)}
                Column(Modifier.fillMaxWidth().padding(bottom=20.dp),horizontalAlignment=Alignment.End,verticalArrangement=Arrangement.spacedBy(4.dp)) {
                    Text("Source: "+a.string("sourceName",a.string("author")),Modifier.clickable { runCatching { links.openUri(a.string("sourceURL")) } }.padding(vertical=8.dp),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Text("Independent Rally reference · No live results or affiliation",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                }
            }
        }
    }
}
