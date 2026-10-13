package com.rallydot.app

import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.*
import androidx.compose.runtime.Composable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalWindowInfo
import androidx.compose.ui.platform.LocalDensity
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import java.util.Locale

fun marketCompactUSD(value: Double?): String {
    if(value==null || !value.isFinite() || value<0)return "—"
    val (scale,suffix)=when { value>=1e9->1e9 to "B";value>=1e6->1e6 to "M";value>=1e3->1e3 to "K";else->1.0 to "" }
    return "$"+String.format(Locale.US,"%,.2f",value/scale).trimEnd('0').trimEnd('.')+suffix
}
fun marketTokenAge(stamp: Long,now: Long=System.currentTimeMillis()/1000): String? {
    if(stamp<=0 || stamp>now)return null
    val d=now-stamp
    return when {d<60->"now";d<3600->"${d/60}m";d<86400->"${d/3600}h";d<2592000->"${d/86400}d";d<31536000->"${d/2592000}mo";else->"${d/31536000}y"}
}
@Composable fun TokenMarketRow(asset: Asset,category: String,onClick: ()->Unit,onBuy: ()->Unit) {
    val compact=LocalWindowInfo.current.containerSize.width/LocalDensity.current.density<360f
    val stamp=asset.raw.optLong(if(category=="Graduated")"graduatedAt" else "created")
    val age=marketTokenAge(stamp)
    val change=asset.change?.takeIf { !asset.stale }
    val gain=MaterialTheme.colorScheme.tertiary
    Row(Modifier.fillMaxWidth().rallyClickable(onClick).padding(horizontal=if(compact)10.dp else 16.dp,vertical=8.dp).heightIn(min=60.dp),verticalAlignment=Alignment.CenterVertically) {
        TokenArtwork(asset,if(compact)34.dp else 40.dp);Spacer(Modifier.width(if(compact)7.dp else 9.dp))
        Column(Modifier.weight(1f).padding(end=6.dp),verticalArrangement=Arrangement.spacedBy(5.dp)) {
            Row(verticalAlignment=Alignment.CenterVertically) {
                Text(asset.symbol,Modifier.weight(1f,false),maxLines=1,overflow=TextOverflow.Ellipsis,fontSize=if(compact)13.sp else 14.sp,lineHeight=18.sp,fontWeight=FontWeight.Medium)
                if(age!=null)Text(age,Modifier.padding(start=5.dp).semantics { contentDescription=(if(category=="Graduated")"Graduated " else "Launched ")+age+" ago" },fontSize=if(compact)9.sp else 10.sp,lineHeight=14.sp,color=gain,maxLines=1)
            }
            Text(marketCompactUSD(asset.raw.number("volume"))+" Vol",fontSize=if(compact)10.sp else 12.sp,lineHeight=16.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.semantics { contentDescription="24-hour volume "+marketCompactUSD(asset.raw.number("volume")) })
        }
        Column(horizontalAlignment=Alignment.End,verticalArrangement=Arrangement.spacedBy(5.dp)) {
            Text(if(asset.cap!=null && asset.cap>0)marketCompactUSD(asset.cap)+" MC" else money(asset.price),fontWeight=FontWeight.Medium,fontSize=if(compact)13.sp else 14.sp,lineHeight=18.sp,maxLines=1)
            val percent=change?.let { (if(it>=0)"▲ " else "▼ ")+String.format(Locale.US,"%,.2f%%",kotlin.math.abs(it)) }
            Text(if(asset.stale)"Last known" else percent ?: "—",fontSize=11.sp,lineHeight=16.sp,color=if(change==null)MaterialTheme.colorScheme.onSurfaceVariant else if(change>=0)gain else MaterialTheme.colorScheme.error,maxLines=1,modifier=Modifier.semantics { contentDescription="24-hour price change: "+(percent ?: "unavailable") })
        }
        Spacer(Modifier.width(6.dp))
        TextButton(onClick=onBuy,enabled=asset.executable,modifier=Modifier.width(44.dp).heightIn(min=44.dp).semantics { contentDescription="Buy ${asset.symbol}" },contentPadding=PaddingValues(0.dp),shape=RoundedCornerShape(100.dp),colors=ButtonDefaults.textButtonColors(containerColor=Buy.copy(alpha=.1f),contentColor=Buy)) { Text("Buy",fontSize=11.sp,fontWeight=FontWeight.SemiBold,maxLines=1) }
    }
}
