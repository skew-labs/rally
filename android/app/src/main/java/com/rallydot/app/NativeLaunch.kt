package com.rallydot.app

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun LaunchSheet(vm: RallyViewModel,close: ()->Unit) {
    val app by vm.state.collectAsStateWithLifecycle()
    val scope=rememberCoroutineScope()
    val account=vm.me?.string("id").orEmpty()
    var name by rememberSaveable(account) { mutableStateOf("") }
    var symbol by rememberSaveable(account) { mutableStateOf("") }
    var description by rememberSaveable(account) { mutableStateOf("") }
    var image by rememberSaveable(account) { mutableStateOf<String?>(null) }
    var media by rememberSaveable(account) { mutableStateOf<String?>(null) }
    var burn by rememberSaveable(account) { mutableStateOf("0") }
    var liquidity by rememberSaveable(account) { mutableStateOf("0") }
    var key by rememberSaveable(account) { mutableStateOf("android-launch-"+java.util.UUID.randomUUID()) }
    var preparing by remember { mutableStateOf(false) }
    var error by remember { mutableStateOf<String?>(null) }
    var fee by remember { mutableStateOf<String?>(null) }
    val locked=app.order.blocksOrder || preparing
    fun changed() { key="android-launch-"+java.util.UUID.randomUUID() }
    val picker=rememberLauncherForActivityResult(ActivityResultContracts.GetContent()) { uri->if(uri!=null && !locked) { image=uri.toString();media=null;changed() } }
    LaunchedEffect(Unit) { try { fee=vm.api.get("/api/nadfun/config").string("creationFeeMON") } catch(e:CancellationException){throw e} catch(e:Exception){error=e.message} }
    ModalBottomSheet(onDismissRequest=close,sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing}) {
        Column(Modifier.fillMaxWidth().heightIn(max=760.dp).imePadding().highRefresh().verticalScroll(rememberScrollState()).padding(horizontal=24.dp).padding(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
            Text("Launch on Monad",style=MaterialTheme.typography.headlineSmall)
            Row(verticalAlignment=Alignment.CenterVertically) {
                Artwork(image?.let { if(it.startsWith("content://"))it else safeImage(it) },symbol.ifEmpty { "Token" },64.dp)
                OutlinedButton(onClick={picker.launch("image/*")},enabled=!locked,modifier=Modifier.padding(start=16.dp),shape=RoundedCornerShape(100.dp)) { Icon(Icons.Outlined.AddPhotoAlternate,null,Modifier.size(18.dp));Spacer(Modifier.width(8.dp));Text("Token image") }
            }
            Text("JPG, PNG or WebP · up to 5 MB",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            OutlinedTextField(name,{name=it.take(32);changed()},Modifier.fillMaxWidth(),enabled=!locked,singleLine=true,label={Text("Name")},shape=RoundedCornerShape(16.dp))
            OutlinedTextField(symbol,{symbol=it.filter { c->c.isLetterOrDigit() && c.code<128 }.take(10);changed()},Modifier.fillMaxWidth(),enabled=!locked,singleLine=true,label={Text("Symbol")},shape=RoundedCornerShape(16.dp))
            OutlinedTextField(description,{description=it.take(500);changed()},Modifier.fillMaxWidth(),enabled=!locked,label={Text("Description")},maxLines=3,shape=RoundedCornerShape(16.dp))
            Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                OutlinedTextField(burn,{burn=it.filter(Char::isDigit).take(3);changed()},Modifier.weight(1f),enabled=!locked,singleLine=true,label={Text("Burn %")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number),shape=RoundedCornerShape(16.dp))
                OutlinedTextField(liquidity,{liquidity=it.filter(Char::isDigit).take(3);changed()},Modifier.weight(1f),enabled=!locked,singleLine=true,label={Text("Liquidity %")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Number),shape=RoundedCornerShape(16.dp))
            }
            val burnPercent=burn.toIntOrNull();val lpPercent=liquidity.toIntOrNull()
            val validShares=burnPercent!=null && lpPercent!=null && burnPercent in 0..100 && lpPercent in 0..100 && burnPercent+lpPercent<=100
            if(validShares)Fact("Your creator fee share","${100-burnPercent!!-lpPercent!!}%")
            Fact("Creation fee",fee?.let { "$it MON + network fee" } ?: "Loading…")
            Text("nad.fun V2 · Bonding curve → DEX. Fee shares apply to this token's trading fees.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            OrderStatus(vm)
            error?.let { Text(it,color=MaterialTheme.colorScheme.error,style=MaterialTheme.typography.bodySmall) }
            Button(onClick={
                if(!vm.wallet.state.value.ready) { vm.showWallet();return@Button }
                val capturedAccount=account
                preparing=true;error=null
                scope.launch {
                    try {
                        require(vm.me?.string("id")==capturedAccount) { "Account changed" }
                        val uploaded=media ?: vm.api.upload(Uri.parse(image!!),5*1024*1024).string("id").also { media=it }
                        require(vm.me?.string("id")==capturedAccount) { "Account changed" }
                        val allocations=JSONObject().put("creator",(100-burnPercent!!-lpPercent!!)*100).put("burn",burnPercent*100).put("liquidity",lpPercent*100)
                        vm.launchToken(JSONObject().put("name",name.trim()).put("symbol",symbol).put("description",description).put("media",uploaded).put("allocations",allocations),key,fee!!)
                    } catch(e:CancellationException){throw e} catch(e:Exception){error=e.message} finally { preparing=false }
                }
            },enabled=!locked && name.trim().isNotEmpty() && symbol.isNotEmpty() && image!=null && validShares && fee!=null,modifier=Modifier.fillMaxWidth().heightIn(min=54.dp),shape=RoundedCornerShape(100.dp)) { if(preparing)CircularProgressIndicator(Modifier.size(18.dp),strokeWidth=2.dp) else Text("Launch token") }
        }
    }
}
