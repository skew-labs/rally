package com.rallydot.app

import androidx.compose.animation.AnimatedVisibility
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.*
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
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import kotlinx.coroutines.CancellationException
import org.json.JSONObject

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun WalletLoginSheet(vm: RallyViewModel,close: ()->Unit) {
    val wallet by vm.wallet.state.collectAsStateWithLifecycle()
    val app by vm.state.collectAsStateWithLifecycle()
    var email by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    val linked=app.boot?.string("wallet").orEmpty()
    LaunchedEffect(Unit) { vm.wallet.restore() }
    ModalBottomSheet(onDismissRequest=close,sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing}) {
        Column(Modifier.fillMaxWidth().heightIn(max=640.dp).imePadding().highRefresh().verticalScroll(rememberScrollState()).padding(horizontal=24.dp).padding(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
            Artwork(safeImage("/assets/community-rally.png"),"Rally",56.dp)
            Text(if(wallet.ready)"Your Rally wallet" else "Sign in to Rally",style=MaterialTheme.typography.headlineSmall)
            if(wallet.ready) {
                SelectionContainer { Text(wallet.address.orEmpty(),style=MaterialTheme.typography.bodyMedium) }
                if(linked.isNotEmpty() && !linked.equals(wallet.address,true)) {
                    Text("This account is linked to ${linked.take(6)}…${linked.takeLast(4)}. Your Rally wallet is different.",style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    Button(onClick={vm.walletAction { link() }},enabled=!wallet.busy,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)) { Text("Use this wallet") }
                } else Button(onClick={vm.walletAction { continueSession() }},enabled=!wallet.busy,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)) { Text("Continue") }
            } else {
                Button(onClick={vm.walletAction { google() }},enabled=!wallet.busy,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.buttonColors(containerColor=MaterialTheme.colorScheme.onSurface,contentColor=MaterialTheme.colorScheme.surface)) {
                    Artwork(safeImage("/assets/auth-google.svg"),"Google",20.dp,false);Spacer(Modifier.width(10.dp));Text("Continue with Google")
                }
                if(!wallet.codeSent) {
                    OutlinedTextField(email,{email=it},Modifier.fillMaxWidth(),enabled=!wallet.busy,singleLine=true,label={Text("Email")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Email),shape=RoundedCornerShape(16.dp))
                    OutlinedButton(onClick={vm.walletAction { sendCode(email) }},enabled=!wallet.busy && email.isNotBlank(),modifier=Modifier.fillMaxWidth().heightIn(min=52.dp),shape=RoundedCornerShape(100.dp)) { Text("Continue with email") }
                } else {
                    Text("Enter the code sent to ${wallet.email}",style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    OutlinedTextField(code,{code=it.filter(Char::isDigit).take(6)},Modifier.fillMaxWidth(),enabled=!wallet.busy,singleLine=true,label={Text("6-digit code")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.NumberPassword),shape=RoundedCornerShape(16.dp))
                    Button(onClick={vm.walletAction { verifyCode(code) }},enabled=!wallet.busy && code.length==6,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)) { Text("Sign in") }
                    TextButton(onClick={vm.walletAction { sendCode(wallet.email) }},enabled=!wallet.busy) { Text("Send a new code") }
                }
                Text("Your wallet stays with you. Sign and trade here.",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
            AnimatedVisibility(wallet.busy) { LinearProgressIndicator(Modifier.fillMaxWidth()) }
            wallet.error?.let { Text(it,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.error) }
            if(wallet.ready && linked.equals(wallet.address,true) && !wallet.busy)TextButton(onClick=close,modifier=Modifier.fillMaxWidth()) { Text("Done") }
        }
    }
}
@Composable fun OrderStatus(vm: RallyViewModel,compact: Boolean=false) {
    val state by vm.state.collectAsStateWithLifecycle();val p=state.order
    var hash by rememberSaveable { mutableStateOf("") }
    if(p.stage=="idle")return
    Surface(color=MaterialTheme.colorScheme.surfaceContainer,shape=RoundedCornerShape(18.dp)) {
        Column(Modifier.fillMaxWidth().padding(if(compact)12.dp else 16.dp),verticalArrangement=Arrangement.spacedBy(8.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically) {
                if(p.working)CircularProgressIndicator(Modifier.size(18.dp),strokeWidth=2.dp) else Icon(if(p.completed && p.stage!="failed")Icons.Outlined.CheckCircle else if(p.stage=="failed")Icons.Outlined.ErrorOutline else Icons.Outlined.Schedule,null,Modifier.size(20.dp),tint=if(p.completed && p.stage!="failed")MaterialTheme.colorScheme.tertiary else MaterialTheme.colorScheme.onSurfaceVariant)
                Text(p.label,Modifier.weight(1f).padding(start=10.dp),style=MaterialTheme.typography.bodyMedium)
                if(compact && p.stage=="unknown")TextButton(onClick={vm.showOrderDetails()}) { Text("Details") }
                if(p.stage=="pending")TextButton(onClick={vm.recoverOrder()}) { Text("Check") }
            }
            if(!compact)p.hash?.let { SelectionContainer { Text(it,style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant) } }
            if(!compact)p.error?.let { Text(it,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.error) }
            if(p.stage=="unknown" && !compact) {
                OutlinedTextField(hash,{hash=it.trim()},Modifier.fillMaxWidth(),singleLine=true,label={Text("Transaction hash from wallet")})
                TextButton(onClick={vm.recoverOrder(hash)},enabled=Regex("0x[0-9a-fA-F]{64}").matches(hash)) { Text("Check transaction") }
            }
        }
    }
}
@Composable fun PortfolioScreen(vm: RallyViewModel,onAsset: (String)->Unit) {
    val state by vm.state.collectAsStateWithLifecycle()
    var portfolio by remember { mutableStateOf<JSONObject?>(null) }
    var perpl by remember { mutableStateOf<JSONObject?>(null) }
    var error by remember { mutableStateOf<String?>(null) }
    var funding by rememberSaveable { mutableStateOf("") }
    var refreshing by remember { mutableIntStateOf(0) }
    LaunchedEffect(state.boot?.string("wallet"),refreshing,state.order.stage) {
        error=null
        try { portfolio=vm.api.get("/api/portfolio",true) } catch(e:CancellationException){throw e} catch(e:Exception){error=e.message}
        try { perpl=vm.api.get("/api/perpl/account",true) } catch(e:CancellationException){throw e} catch(_:Exception){perpl=null}
    }
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
        item { Row(verticalAlignment=Alignment.CenterVertically) { Text("Wallet",Modifier.weight(1f),style=MaterialTheme.typography.titleMedium);TextButton(onClick={vm.showWallet()}){Text("Manage")};IconButton(onClick={refreshing++}){Icon(Icons.Outlined.Refresh,"Refresh balances")} } }
        item { state.boot?.string("wallet")?.takeIf { it.isNotBlank() }?.let { SelectionContainer { Text(it,style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) } } ?: Button(onClick={vm.showWallet()}){Text("Connect wallet")} }
        item { OrderStatus(vm) }
        error?.let { item { Text(it,color=MaterialTheme.colorScheme.error) } }
        portfolio?.let { value->
            if((value.optJSONArray("unavailable")?.length() ?: 0)>0)item { Text("Some balances are unavailable",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall) }
            items(value.objects("holdings"),key={it.string("asset")}) { h->val token=h.optJSONObject("token") ?: JSONObject();Row(Modifier.fillMaxWidth().clickable { onAsset(token.string("id",h.string("asset"))) }.padding(vertical=10.dp),verticalAlignment=Alignment.CenterVertically) { Artwork(safeImage(token.string("logoURI",if(h.string("asset")=="MON")"/assets/MON.png" else "")),token.string("symbol",h.string("asset")),40.dp);Column(Modifier.weight(1f).padding(start=12.dp)) { Text(token.string("symbol",h.string("asset")),fontWeight=FontWeight.Medium);Text(token.string("name"),style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant) };Text(displayAmount(h.string("amount")),maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.widthIn(max=140.dp)) } }
            if(value.objects("holdings").isEmpty())item { Text("No balances to display",color=MaterialTheme.colorScheme.onSurfaceVariant) }
        }
        perpl?.let { value->item {
            Text("Perpl",style=MaterialTheme.typography.titleMedium)
            Fact("Trading balance",value.string("balanceAUSD",value.string("balance","—"))+" AUSD")
            OutlinedTextField(funding,{funding=it},Modifier.fillMaxWidth(),singleLine=true,label={Text("Amount in AUSD")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Decimal),shape=RoundedCornerShape(16.dp))
            Row(horizontalArrangement=Arrangement.spacedBy(12.dp)) { OutlinedButton(onClick={vm.execute(JSONObject().put("venue","perpl").put("kind","deposit").put("amount",funding))},enabled=validAmount(funding) && !state.order.blocksOrder,modifier=Modifier.weight(1f)) { Text("Deposit") };OutlinedButton(onClick={vm.execute(JSONObject().put("venue","perpl").put("kind","withdraw").put("amount",funding))},enabled=validAmount(funding) && !state.order.blocksOrder,modifier=Modifier.weight(1f)) { Text("Withdraw") } }
        } }
        item { TextButton(onClick={vm.load("activity","/api/activity","entries",true)}) { Text("Refresh activity") } }
    }
}

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun OrderDetailsSheet(vm: RallyViewModel,close: ()->Unit) {
    ModalBottomSheet(onDismissRequest=close,sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing}) {
        Column(Modifier.fillMaxWidth().heightIn(max=620.dp).imePadding().highRefresh().verticalScroll(rememberScrollState()).padding(24.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
            Text("Transaction",style=MaterialTheme.typography.headlineSmall)
            OrderStatus(vm)
        }
    }
}
