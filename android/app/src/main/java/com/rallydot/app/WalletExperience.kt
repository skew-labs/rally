package com.rallydot.app

import android.graphics.Bitmap
import androidx.compose.animation.AnimatedVisibility
import androidx.compose.animation.Crossfade
import androidx.compose.animation.core.tween
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.foundation.text.selection.SelectionContainer
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.graphics.asImageBitmap
import androidx.compose.ui.platform.LocalClipboardManager
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalHapticFeedback
import androidx.compose.ui.hapticfeedback.HapticFeedbackType
import androidx.compose.ui.text.AnnotatedString
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import com.google.zxing.BarcodeFormat
import com.google.zxing.qrcode.QRCodeWriter
import kotlinx.coroutines.*
import org.json.JSONObject
import java.util.Locale

@Composable fun WalletBalanceHero(vm: RallyViewModel) {
    val state by vm.state.collectAsStateWithLifecycle()
    WalletBalanceHero(state,{vm.showWalletPanel("send")},{vm.showWalletPanel("deposit")})
}
@Composable fun WalletBalanceHero(state: AppState,onSend: ()->Unit,onDeposit: ()->Unit) {
    val p=state.portfolio;val value=p?.optJSONObject("valuation")
    Column(Modifier.fillMaxWidth().padding(vertical=8.dp),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        Text(if(value?.optBoolean("partial")==true)"Priced balance · USD" else "Wallet balance · USD",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        val balance=money(value?.number("valueUSD"))
        Crossfade(balance,animationSpec=tween(180),label="Wallet value") { text->
            Text(text,fontSize=(if(text.length>13)34 else if(text.length>10)38 else 44).sp,fontWeight=FontWeight.Medium,maxLines=1,overflow=TextOverflow.Ellipsis,letterSpacing=(-1).sp)
        }
        val change=value?.number("change24hPercent")
        Text(if(change!=null)String.format(Locale.US,"%+.2f%% · 24h price change",change) else if(p==null || p.optBoolean("refreshing"))"Updating balances…" else "24h price change unavailable",color=if(change==null)MaterialTheme.colorScheme.onSurfaceVariant else if(change>=0)Gain else Sell,style=MaterialTheme.typography.bodyMedium)
        Row(Modifier.fillMaxWidth().padding(vertical=8.dp),horizontalArrangement=Arrangement.spacedBy(12.dp)) {
            Button(onClick=onSend,modifier=Modifier.weight(1f).heightIn(min=50.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=MaterialTheme.colorScheme.onSurface,contentColor=MaterialTheme.colorScheme.surface)) { Icon(Icons.Outlined.NorthEast,null,Modifier.size(18.dp));Spacer(Modifier.width(8.dp));Text("Send") }
            OutlinedButton(onClick=onDeposit,modifier=Modifier.weight(1f).heightIn(min=50.dp),shape=RoundedCornerShape(100.dp)) { Icon(Icons.Outlined.Add,null,Modifier.size(18.dp));Spacer(Modifier.width(8.dp));Text("Deposit") }
        }
        if((value?.optInt("unpricedAssets") ?: 0)>0)Text("${value!!.optInt("unpricedAssets")} assets without a current price",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        if((p?.optJSONArray("unavailable")?.length() ?: 0)>0)Text("Some balances are temporarily unavailable",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        state.portfolioError?.let { Text(it,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
    }
}

@Composable fun WalletHolding(h: JSONObject,onClick: ()->Unit) {
    val token=h.optJSONObject("token") ?: JSONObject();val symbol=token.string("symbol",h.string("asset"))
    Row(Modifier.fillMaxWidth().clickable(onClick=onClick).padding(vertical=14.dp),verticalAlignment=Alignment.CenterVertically) {
        Artwork(safeImage(token.string("logoURI",if(h.string("asset")=="MON")"/assets/MON.png" else "")),symbol,40.dp)
        Column(Modifier.weight(1f).padding(horizontal=12.dp)) { Text(symbol,fontWeight=FontWeight.Medium,maxLines=1,overflow=TextOverflow.Ellipsis);Text(displayAmount(h.string("amount"))+" "+symbol+if(h.optBoolean("staleBalance"))" · Last known" else "",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis) }
        Text(money(h.number("valueUSD")),Modifier.widthIn(max=130.dp),maxLines=1,overflow=TextOverflow.Ellipsis)
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun WalletAssetsSheet(vm: RallyViewModel,mode: String,close: ()->Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    WalletAssetsSheet(state,mode,close,{h,r,a->vm.sendAsset(h,r,a)},{vm.message("Address copied")})
}
@OptIn(ExperimentalMaterial3Api::class)
@Composable fun WalletAssetsSheet(state: AppState,mode: String,close: ()->Unit,onSend: (JSONObject,String,String)->Unit,onCopied: ()->Unit) {
    val wallet=state.boot?.string("wallet").orEmpty()
    val clipboard=LocalClipboardManager.current
    val haptic=LocalHapticFeedback.current
    val focus=LocalFocusManager.current
    var copied by remember(wallet) { mutableStateOf(false) }
    LaunchedEffect(copied) { if(copied) { delay(2200);copied=false } }
    var qr by remember(wallet) { mutableStateOf<Bitmap?>(null) }
    LaunchedEffect(wallet,mode) {
        if(mode=="deposit" && Regex("0x[0-9a-fA-F]{40}").matches(wallet))qr=withContext(Dispatchers.Default) {
            val bits=QRCodeWriter().encode(wallet,BarcodeFormat.QR_CODE,256,256)
            val pixels=IntArray(256*256) { if(bits[it%256,it/256])android.graphics.Color.BLACK else android.graphics.Color.WHITE }
            Bitmap.createBitmap(pixels,256,256,Bitmap.Config.ARGB_8888)
        }
    }
    val assets=state.portfolio?.objects("holdings").orEmpty().filter { (it.number("amount") ?: 0.0)>0 && !it.optBoolean("staleBalance") }
    var selected by rememberSaveable(wallet) { mutableStateOf("") };var expanded by remember { mutableStateOf(false) }
    val holding=assets.find { it.string("asset")==selected } ?: assets.firstOrNull()
    var destination by rememberSaveable(wallet) { mutableStateOf("") };var amount by rememberSaveable(wallet) { mutableStateOf("") }
    ModalBottomSheet(onDismissRequest=close,sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing}) {
        BoxWithConstraints(Modifier.fillMaxWidth().imePadding().highRefresh()) {
            val fontScale=LocalDensity.current.fontScale
            val preferred=if(mode=="deposit")570.dp else 590.dp
            Column(Modifier.fillMaxWidth().height(maxHeight.coerceAtMost(preferred+(48.dp*(fontScale-1).coerceAtLeast(0f))))) {
                Column(Modifier.weight(1f).verticalScroll(rememberScrollState()).padding(horizontal=24.dp,vertical=16.dp),verticalArrangement=Arrangement.spacedBy(18.dp),horizontalAlignment=Alignment.CenterHorizontally) {
                    Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) { Text(if(mode=="deposit")"Deposit" else "Send",Modifier.weight(1f),style=MaterialTheme.typography.headlineSmall);Text("Monad",style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                    if(mode=="deposit") {
                        Box(Modifier.size(228.dp).background(Color.White,RoundedCornerShape(24.dp)),contentAlignment=Alignment.Center) {
                            qr?.let { Image(it.asImageBitmap(),"Wallet address QR code",Modifier.size(208.dp)) } ?: CircularProgressIndicator(Modifier.size(24.dp),strokeWidth=2.dp)
                        }
                        Text("Send assets on Monad to this address.",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall)
                        Surface(Modifier.fillMaxWidth(),shape=RoundedCornerShape(14.dp),color=MaterialTheme.colorScheme.surfaceContainer) { SelectionContainer { Text(wallet,Modifier.padding(14.dp),style=MaterialTheme.typography.bodySmall) } }
                    } else {
                        Box(Modifier.fillMaxWidth()) {
                            OutlinedButton(onClick={expanded=true},enabled=!state.order.blocksOrder && assets.isNotEmpty(),modifier=Modifier.fillMaxWidth().heightIn(min=62.dp),shape=RoundedCornerShape(18.dp),border=BorderStroke(1.dp,MaterialTheme.colorScheme.outlineVariant),colors=ButtonDefaults.outlinedButtonColors(contentColor=MaterialTheme.colorScheme.onSurface,containerColor=MaterialTheme.colorScheme.surfaceContainer)) {
                                holding?.let { h->val t=h.optJSONObject("token") ?: JSONObject();Artwork(safeImage(t.string("logoURI")),t.string("symbol",h.string("asset")),28.dp);Text(t.string("symbol",h.string("asset")),Modifier.weight(1f).padding(horizontal=12.dp));Text(displayAmount(h.string("amount")),maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.widthIn(max=120.dp)) } ?: Text(if(state.portfolio?.optBoolean("refreshing")!=false)"Loading assets…" else "No assets to send")
                                Spacer(Modifier.width(8.dp));Icon(Icons.Outlined.ExpandMore,null,Modifier.size(18.dp))
                            }
                            DropdownMenu(expanded,{expanded=false}) { assets.forEach { h->DropdownMenuItem(text={Text(h.optJSONObject("token")?.string("symbol",h.string("asset")) ?: h.string("asset"))},onClick={selected=h.string("asset");expanded=false;amount=""}) } }
                        }
                        OutlinedTextField(destination,{destination=it.trim()},Modifier.fillMaxWidth(),enabled=!state.order.blocksOrder,singleLine=true,label={Text("Recipient")},placeholder={Text("0x…")},shape=RoundedCornerShape(16.dp),colors=OutlinedTextFieldDefaults.colors(unfocusedBorderColor=Color.Transparent,unfocusedContainerColor=MaterialTheme.colorScheme.surfaceContainer,focusedContainerColor=MaterialTheme.colorScheme.surfaceContainer))
                        val input=amount.toDoubleOrNull();val available=holding?.number("amount");val usdValue=holding?.number("valueUSD")
                        TradeAmount(amount,{amount=it},"Amount",holding?.optJSONObject("token")?.string("symbol",holding?.string("asset").orEmpty()) ?: "",Buy,{focus.clearFocus()},enabled=!state.order.blocksOrder)
                        if(input!=null && available!=null && input>available)Text("Not enough balance",Modifier.fillMaxWidth(),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.error)
                        Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                            Text(if(input!=null && input>0 && usdValue!=null && available!=null && available>0)money(input*usdValue/available) else "— USD",Modifier.weight(1f),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                            for(part in listOf(25,50))TextButton(onClick={
                                holding?.let { h->val decimals=if(h.string("asset")=="MON")18 else h.optJSONObject("token")?.optInt("decimals") ?: 0
                                    if(decimals in 0..36)runCatching { amount=h.string("amount").toBigDecimal().multiply(java.math.BigDecimal(part)).divide(java.math.BigDecimal(100)).setScale(decimals,java.math.RoundingMode.DOWN).stripTrailingZeros().toPlainString() }
                                }
                            },enabled=holding!=null && !state.order.blocksOrder,contentPadding=PaddingValues(horizontal=10.dp),colors=ButtonDefaults.textButtonColors(contentColor=MaterialTheme.colorScheme.onSurface)) { Text("$part%",style=MaterialTheme.typography.labelMedium) }
                        }
                        HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
                        Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) { Text("Network",Modifier.weight(1f),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Artwork(safeImage("/assets/MON.png"),"Monad",18.dp);Spacer(Modifier.width(6.dp));Text("Monad · Fee in MON",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) }
                        if(state.order.stage!="idle")Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
                            if(state.order.working)CircularProgressIndicator(Modifier.size(16.dp),strokeWidth=2.dp)
                            else if(state.order.completed && state.order.stage=="complete")Icon(Icons.Outlined.CheckCircle,null,Modifier.size(18.dp),tint=Gain)
                            Text(state.order.label,style=MaterialTheme.typography.bodySmall)
                        }
                        state.order.error?.let { Text(it,Modifier.fillMaxWidth(),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.error) }
                    }
                }
                Column(Modifier.fillMaxWidth().padding(horizontal=24.dp,vertical=16.dp)) {
                    if(mode=="deposit")Button(onClick={clipboard.setText(AnnotatedString(wallet));copied=true;haptic.performHapticFeedback(HapticFeedbackType.Confirm);onCopied()},modifier=Modifier.fillMaxWidth().heightIn(min=54.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=MaterialTheme.colorScheme.onSurface,contentColor=MaterialTheme.colorScheme.surface)) { Icon(if(copied)Icons.Outlined.Check else Icons.Outlined.ContentCopy,null,Modifier.size(18.dp));Spacer(Modifier.width(8.dp));Text(if(copied)"Copied" else "Copy address") }
                    else Button(onClick={holding?.let { haptic.performHapticFeedback(HapticFeedbackType.Confirm);onSend(it,destination,amount) }},enabled=holding!=null && validAmount(amount) && (amount.toDoubleOrNull() ?: Double.MAX_VALUE)<=(holding.number("amount") ?: 0.0) && Regex("0x[0-9a-fA-F]{40}").matches(destination) && destination!="0x"+"0".repeat(40) && !destination.equals(wallet,true) && !state.order.blocksOrder,modifier=Modifier.fillMaxWidth().heightIn(min=54.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=Buy,contentColor=Color.White)) { Text(if(state.order.working)"Sending…" else if(state.order.stage=="complete")"Send again" else "Send") }
                }
            }
        }
    }
}

@Composable fun TokenHolders(vm: RallyViewModel,asset: Asset) {
    if(!asset.id.startsWith("0x"))return
    var data by remember(asset.id) { mutableStateOf<JSONObject?>(null) };var error by remember(asset.id) { mutableStateOf(false) }
    LaunchedEffect(asset.id) {
        repeat(25) {
            try { data=vm.api.get("/api/token-holders?asset="+android.net.Uri.encode(asset.id),true);if(data?.optBoolean("refreshing")!=true)return@LaunchedEffect }
            catch(e:CancellationException) { throw e } catch(_:Exception) { error=true;return@LaunchedEffect }
            delay(2000)
        }
    }
    Column(Modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(12.dp)) {
        Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) { Text("Holders",Modifier.weight(1f),style=MaterialTheme.typography.titleSmall);data?.number("total")?.let { Text(compact(it),style=MaterialTheme.typography.labelMedium,color=MaterialTheme.colorScheme.onSurfaceVariant) } }
        val holders=data?.objects("holders").orEmpty()
        if(holders.isEmpty())Text(if(error || data?.has("error")==true)"Holder data temporarily unavailable" else if(data?.optBoolean("indexed")==false)"Holder indexing is unavailable for this asset" else if(data?.optBoolean("refreshing")!=false)"Updating holders…" else "No indexed holders yet",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
        holders.take(10).forEachIndexed { index,h->Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) { Text("${index+1}",Modifier.width(26.dp),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant);Column(Modifier.weight(1f).padding(end=12.dp)) { val address=h.string("address");Text(h.string("name").takeIf { it.isNotBlank() && !it.startsWith("0x") } ?: address.take(6)+"…"+address.takeLast(4),style=MaterialTheme.typography.bodySmall,maxLines=1,overflow=TextOverflow.Ellipsis);Text(address.take(6)+"…"+address.takeLast(4),style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant) };Text(displayAmount(h.string("amount")),Modifier.widthIn(max=100.dp),style=MaterialTheme.typography.bodySmall,maxLines=1,overflow=TextOverflow.Ellipsis) } }
        if(holders.isNotEmpty())Text("nad.fun · ${age(data?.optLong("fetchedAt") ?: 0)}"+if(data?.optBoolean("stale")==true)" · Last known" else "",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
    }
}
