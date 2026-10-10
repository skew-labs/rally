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
@Composable fun WalletLoginSheet(vm: RallyViewModel,close: ()->Unit,openBrowser: (String)->Unit) {
    val wallet by vm.wallet.state.collectAsStateWithLifecycle()
    val app by vm.state.collectAsStateWithLifecycle()
    var email by rememberSaveable { mutableStateOf("") }
    var code by rememberSaveable { mutableStateOf("") }
    var emailOpen by rememberSaveable { mutableStateOf(false) }
    val completedAtOpen=remember { wallet.completed }
    val accountAtOpen=remember { app.boot?.optJSONObject("me")?.string("id") }
    val linked=app.boot?.string("wallet").orEmpty()
    LaunchedEffect(Unit) { vm.wallet.restore() }
    LaunchedEffect(wallet.completed,wallet.busy) { if(wallet.completed>completedAtOpen && !wallet.busy)close() }
    LaunchedEffect(app.boot?.optJSONObject("me")?.string("id"),app.connecting) {
        if(accountAtOpen==null && app.boot?.optJSONObject("me")!=null && !app.connecting && linked.isNotEmpty())close()
    }
    ModalBottomSheet(onDismissRequest={if(wallet.busy)vm.cancelWalletLogin();if(app.connecting)vm.cancelConnect();close()},sheetState=rememberModalBottomSheetState(skipPartiallyExpanded=true),containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing}) {
        Column(Modifier.fillMaxWidth().heightIn(max=640.dp).imePadding().highRefresh().verticalScroll(rememberScrollState()).padding(horizontal=24.dp).padding(bottom=24.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
            Artwork(safeImage("/assets/community-rally.png"),"Rally",44.dp)
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
                if(wallet.externalConfigured)externalWalletBrands.forEach { brand->
                    OutlinedButton(onClick={vm.walletAction { connectExternal(brand) }},enabled=!wallet.busy,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp),shape=RoundedCornerShape(16.dp)) {
                        Artwork(safeImage("/assets/${brand.image}"),brand.name,24.dp,false);Spacer(Modifier.width(12.dp));Text(brand.name,Modifier.weight(1f),maxLines=1)
                        if(vm.wallet.installed(brand))Text("Installed",style=MaterialTheme.typography.labelSmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    }
                } else OutlinedButton(onClick={vm.connect(openBrowser)},enabled=!wallet.busy && !app.connecting,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp),shape=RoundedCornerShape(16.dp)) {
                    listOf("agent-metamask.svg","wallet-coinbase.svg","wallet-rainbow.svg").forEach { Artwork(safeImage("/assets/$it"),"",20.dp,false);Spacer(Modifier.width(5.dp)) };Spacer(Modifier.width(6.dp));Text("Connect wallet")
                }
                if(!emailOpen && !wallet.codeSent)TextButton(onClick={emailOpen=true},enabled=!wallet.busy,modifier=Modifier.fillMaxWidth()) { Text("Continue with email") }
                if(emailOpen && !wallet.codeSent) {
                    OutlinedTextField(email,{email=it},Modifier.fillMaxWidth(),enabled=!wallet.busy,singleLine=true,label={Text("Email")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.Email),shape=RoundedCornerShape(16.dp))
                    OutlinedButton(onClick={vm.walletAction { sendCode(email) }},enabled=!wallet.busy && email.isNotBlank(),modifier=Modifier.fillMaxWidth().heightIn(min=52.dp),shape=RoundedCornerShape(100.dp)) { Text("Continue with email") }
                } else if(wallet.codeSent) {
                    Text("Enter the code sent to ${wallet.email}",style=MaterialTheme.typography.bodyMedium,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    OutlinedTextField(code,{code=it.filter(Char::isDigit).take(6)},Modifier.fillMaxWidth(),enabled=!wallet.busy,singleLine=true,label={Text("6-digit code")},keyboardOptions=KeyboardOptions(keyboardType=KeyboardType.NumberPassword),shape=RoundedCornerShape(16.dp))
                    Button(onClick={vm.walletAction { verifyCode(code) }},enabled=!wallet.busy && code.length==6,modifier=Modifier.fillMaxWidth().heightIn(min=52.dp)) { Text("Sign in") }
                    TextButton(onClick={vm.walletAction { sendCode(wallet.email) }},enabled=!wallet.busy) { Text("Send a new code") }
                }
                if(app.connecting) {
                    Text("Finish signing in your wallet · ${app.connectionCode.orEmpty()}",style=MaterialTheme.typography.bodySmall,color=MaterialTheme.colorScheme.onSurfaceVariant)
                    TextButton(onClick={vm.resumeConnect(openBrowser)}) { Text("Return to wallet") }
                    TextButton(onClick={vm.cancelConnect()}) { Text("Cancel") }
                }
            }
            AnimatedVisibility(wallet.busy) { Row(verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                CircularProgressIndicator(Modifier.size(20.dp),strokeWidth=2.dp);Text(wallet.phase ?: "Connecting…",Modifier.weight(1f),style=MaterialTheme.typography.bodyMedium);TextButton(onClick={vm.cancelWalletLogin()}) { Text("Cancel") }
            } }
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
    val portfolio=state.portfolio
    val error=state.portfolioError
    var perpl by remember { mutableStateOf<JSONObject?>(null) }
    var funding by rememberSaveable { mutableStateOf("") }
    var refreshing by remember { mutableIntStateOf(0) }
    LaunchedEffect(state.boot?.string("wallet"),refreshing) { vm.loadPortfolio(refreshing>0) }
    LaunchedEffect(state.boot?.string("wallet"),refreshing,state.order.completed) {
        try { perpl=vm.api.get("/api/perpl/account",true) } catch(e:CancellationException){throw e} catch(_:Exception){perpl=null}
    }
    LazyColumn(contentPadding=PaddingValues(20.dp),verticalArrangement=Arrangement.spacedBy(16.dp)) {
        item { Row(verticalAlignment=Alignment.CenterVertically) { Text("Wallet",Modifier.weight(1f),style=MaterialTheme.typography.titleMedium);TextButton(onClick={vm.showWallet()}){Text("Manage")};IconButton(onClick={refreshing++}){Icon(Icons.Outlined.Refresh,"Refresh balances")} } }
        item { if(!state.boot?.string("wallet").isNullOrBlank())WalletBalanceHero(vm) else Button(onClick={vm.showWallet()}) { Text("Connect wallet") } }
        item { OrderStatus(vm) }
        error?.let { item { Text(it,color=MaterialTheme.colorScheme.error) } }
        portfolio?.let { value->
            if((value.optJSONArray("unavailable")?.length() ?: 0)>0)item { Text("Some balances are unavailable",color=MaterialTheme.colorScheme.onSurfaceVariant,style=MaterialTheme.typography.bodySmall) }
            items(value.objects("holdings").filter { (it.number("amount") ?: 0.0)>0 },key={it.string("asset")}) { h-> WalletHolding(h,{onAsset(h.string("asset"))}) }
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
