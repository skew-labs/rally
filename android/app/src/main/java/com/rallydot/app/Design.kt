package com.rallydot.app

import androidx.compose.animation.core.*
import androidx.compose.animation.animateColorAsState
import androidx.compose.foundation.*
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.interaction.collectIsPressedAsState
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.*
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.*
import androidx.compose.ui.graphics.*
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.semantics.*
import androidx.compose.ui.text.font.*
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*

val RallyFont=FontFamily(Font(R.font.inter_regular,FontWeight.Normal),Font(R.font.inter_medium,FontWeight.Medium),Font(R.font.inter_semibold,FontWeight.SemiBold),Font(R.font.inter_bold,FontWeight.Bold))
val RallyTypography=Typography().let { t->t.copy(
    headlineLarge=t.headlineLarge.copy(fontFamily=RallyFont,fontWeight=FontWeight.SemiBold,letterSpacing=(-.8).sp),
    headlineMedium=t.headlineMedium.copy(fontFamily=RallyFont,fontWeight=FontWeight.SemiBold,letterSpacing=(-.65).sp),
    headlineSmall=t.headlineSmall.copy(fontFamily=RallyFont,fontSize=24.sp,fontWeight=FontWeight.SemiBold,letterSpacing=(-.6).sp),
    titleLarge=t.titleLarge.copy(fontFamily=RallyFont,fontSize=22.sp,fontWeight=FontWeight.SemiBold,letterSpacing=(-.5).sp),
    titleMedium=t.titleMedium.copy(fontFamily=RallyFont,fontSize=15.sp,fontWeight=FontWeight.Medium,letterSpacing=(-.2).sp),
    titleSmall=t.titleSmall.copy(fontFamily=RallyFont,fontSize=14.sp,fontWeight=FontWeight.Medium),
    bodyLarge=t.bodyLarge.copy(fontFamily=RallyFont,fontSize=15.sp,lineHeight=24.sp,letterSpacing=(-.18).sp),
    bodyMedium=t.bodyMedium.copy(fontFamily=RallyFont,fontSize=14.sp,lineHeight=21.sp,letterSpacing=(-.1).sp),
    bodySmall=t.bodySmall.copy(fontFamily=RallyFont,fontSize=11.sp,lineHeight=16.sp),
    labelLarge=t.labelLarge.copy(fontFamily=RallyFont,fontSize=13.sp,fontWeight=FontWeight.Medium),
    labelMedium=t.labelMedium.copy(fontFamily=RallyFont,fontSize=11.sp,fontWeight=FontWeight.Medium),
    labelSmall=t.labelSmall.copy(fontFamily=RallyFont,fontSize=10.sp,fontWeight=FontWeight.Medium)
)}

// Votes on redraws only. Android retains control over battery, thermal and display limits.
@OptIn(ExperimentalComposeUiApi::class)
fun Modifier.highRefresh()=preferredFrameRate(FrameRateCategory.High)

@Composable fun Modifier.pressFeedback(source: MutableInteractionSource): Modifier {
    val pressed by source.collectIsPressedAsState()
    val scale=animateFloatAsState(if(pressed).975f else 1f,spring(dampingRatio=1f,stiffness=1100f),label="press")
    return highRefresh().graphicsLayer { scaleX=scale.value;scaleY=scale.value }
}

@Composable fun RallyBrand() {
    Row(verticalAlignment=Alignment.Bottom) {
        Text("rally",fontFamily=RallyFont,fontWeight=FontWeight.Bold,fontSize=27.sp,letterSpacing=(-1.5).sp,lineHeight=32.sp)
        Box(Modifier.padding(start=2.dp,bottom=5.dp).size(5.dp).background(Violet,CircleShape))
    }
}

@Composable fun RallyNavigation(selected: Int,onSelect: (Int)->Unit) {
    val density=androidx.compose.ui.platform.LocalDensity.current
    val outline=listOf(R.drawable.nav_home,R.drawable.nav_communities,R.drawable.nav_search,0,R.drawable.nav_account)
    val filled=listOf(R.drawable.nav_home_selected,R.drawable.nav_communities_selected,R.drawable.nav_search_selected,0,R.drawable.nav_account_selected)
    val labels=listOf("Home",if(density.fontScale>1.3f)"Groups" else "Communities","Discover","Leaderboard","Profile")
    Surface(Modifier.fillMaxWidth().navigationBarsPadding().padding(horizontal=10.dp,vertical=8.dp),shape=RoundedCornerShape(24.dp),color=MaterialTheme.colorScheme.surface,border=BorderStroke(1.dp,MaterialTheme.colorScheme.outlineVariant)) {
        Row(Modifier.fillMaxWidth().heightIn(min=64.dp).padding(horizontal=4.dp,vertical=5.dp)) {
            labels.forEachIndexed { index,label->
                val active=selected==index
                val interactions=remember { MutableInteractionSource() }
                val color=MaterialTheme.colorScheme.onSurface
                val tint=if(active)color else MaterialTheme.colorScheme.onSurfaceVariant
                Column(Modifier.weight(1f).pressFeedback(interactions).clickable(interactionSource=interactions,indication=null,role=Role.Tab,onClick={onSelect(index)}).semantics { this.selected=active;contentDescription=Tabs[index].label }.padding(vertical=3.dp),horizontalAlignment=Alignment.CenterHorizontally,verticalArrangement=Arrangement.spacedBy(3.dp)) {
                    val backdrop by animateColorAsState(if(active)if(MaterialTheme.colorScheme.surface.luminance()<.2f)Color(0xFF302A43) else Color(0xFFEEEAFA) else Color.Transparent,tween(140),label="navigation")
                    Box(Modifier.size(width=46.dp,height=34.dp).background(backdrop,RoundedCornerShape(18.dp)),contentAlignment=Alignment.Center) {
                        if(index==3)Icon(Icons.Outlined.EmojiEvents,null,Modifier.size(24.dp),tint=tint)
                        else Icon(painterResource(if(active)filled[index] else outline[index]),null,Modifier.size(24.dp),tint=tint)
                    }
                    Text(label,fontSize=if(density.fontScale>1.3f && index==3)8.sp else 9.sp,lineHeight=12.sp,color=tint,maxLines=1,overflow=TextOverflow.Ellipsis)
                }
            }
        }
    }
}
