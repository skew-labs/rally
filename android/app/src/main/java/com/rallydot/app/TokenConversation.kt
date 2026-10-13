package com.rallydot.app

import android.net.Uri
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.foundation.text.ClickableText
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.outlined.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.*
import androidx.compose.ui.draw.clip
import androidx.compose.ui.focus.FocusRequester
import androidx.compose.ui.focus.focusRequester
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.platform.LocalSoftwareKeyboardController
import androidx.compose.ui.text.*
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.*
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import org.json.JSONObject
import java.util.UUID

@Composable fun TokenCommentRow(post: Post,onReply: ()->Unit,onAsset: ()->Unit,onLike: ()->Unit,onAuthor: ()->Unit,onCreatorToken: (String)->Unit={},onMention: (String)->Unit={},inside: Boolean=false,reactionPending: Boolean=false) {
    var expanded by rememberSaveable(post.id){mutableStateOf(false)}
    var overflow by remember(post.id){mutableStateOf(false)}
    Row(Modifier.fillMaxWidth().padding(horizontal=if(inside)0.dp else 16.dp,vertical=12.dp),horizontalArrangement=Arrangement.spacedBy(10.dp)) {
        Box(Modifier.clickable(onClick=onAuthor)){ProfileArtwork(post.author.image,post.author.name,32.dp,identity=post.author.avatarIdentity)}
        Column(Modifier.weight(1f),verticalArrangement=Arrangement.spacedBy(5.dp)) {
            Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                Column(Modifier.weight(1f).clickable(onClick=onAuthor)) { Text(post.author.name,fontSize=12.sp,fontWeight=FontWeight.SemiBold,maxLines=1,overflow=TextOverflow.Ellipsis);Text("@${post.author.handle}",fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant,maxLines=1,overflow=TextOverflow.Ellipsis) }
                if(post.author.agent)Text("Agent",fontSize=9.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
                Text(age(post.created),fontSize=10.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
            }
            post.raw.optJSONObject("replyTo")?.optJSONObject("author")?.let { author->Text("↳ @"+author.string("handle"),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant) }
            val linkColor=MaterialTheme.colorScheme.primary
            val text=remember(post.text,post.raw,linkColor){buildAnnotatedString {
                append(post.text)
                val people=post.raw.objects("mentions").associateBy {it.string("handle").lowercase()}
                Regex("(?<![\\w@])@([a-zA-Z0-9_]{3,24})(?![\\w])").findAll(post.text).forEach { match->people[match.groupValues[1].lowercase()]?.let { p->addStringAnnotation("person",p.string("id"),match.range.first,match.range.last+1);addStyle(SpanStyle(color=linkColor),match.range.first,match.range.last+1)} }
            }}
            @Suppress("DEPRECATION")
            ClickableText(text,style=MaterialTheme.typography.bodyMedium.copy(fontSize=13.sp,lineHeight=19.sp,color=MaterialTheme.colorScheme.onSurface),maxLines=if(inside||expanded)Int.MAX_VALUE else 4,overflow=TextOverflow.Ellipsis,onTextLayout={if(!expanded)overflow=it.hasVisualOverflow},onClick={offset->val person=text.getStringAnnotations("person",offset,offset).firstOrNull();if(person!=null)onMention(person.item) else onReply()})
            if(!inside&&(overflow||expanded))TextButton(onClick={expanded=!expanded},contentPadding=PaddingValues(0.dp),modifier=Modifier.heightIn(min=36.dp)){Text(if(expanded)"Show less" else "Show more",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
            post.media?.let { media->coil.compose.AsyncImage(safeImage(media.string("poster",media.string("url"))),"Comment media",Modifier.fillMaxWidth().heightIn(max=240.dp).clip(RoundedCornerShape(12.dp)).clickable(onClick=onReply),contentScale=androidx.compose.ui.layout.ContentScale.Crop) }
            val token=post.raw.optJSONObject("assetInfo")
            if(!inside && post.asset.isNotBlank())Row(Modifier.heightIn(min=36.dp).clip(RoundedCornerShape(100.dp)).background(MaterialTheme.colorScheme.surfaceContainer).clickable(onClick=onAsset).padding(horizontal=8.dp,vertical=4.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(6.dp)) {
                TokenArtwork(Asset.parse(JSONObject(token?.toString() ?: "{}").put("id",post.asset)),24.dp)
                Text(token?.string("symbol")?.ifBlank {null} ?: if(post.asset.startsWith("0x"))post.asset.take(6)+"…"+post.asset.takeLast(4) else post.asset,fontSize=12.sp,fontWeight=FontWeight.Medium,maxLines=1,overflow=TextOverflow.Ellipsis,modifier=Modifier.weight(1f,false))
                Icon(Icons.Outlined.ChevronRight,null,Modifier.size(14.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant)
            }
            Row(Modifier.fillMaxWidth(),verticalAlignment=Alignment.CenterVertically) {
                TextButton(onClick=onLike,enabled=!reactionPending,contentPadding=PaddingValues(0.dp),modifier=Modifier.heightIn(min=44.dp).widthIn(min=44.dp)){Icon(if(post.liked)Icons.Outlined.Favorite else Icons.Outlined.FavoriteBorder,"Like comment",Modifier.size(16.dp),tint=if(post.liked)Sell else MaterialTheme.colorScheme.onSurfaceVariant);if(post.likes>0)Text(" ${post.likes}",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                TextButton(onClick=onReply,contentPadding=PaddingValues(horizontal=8.dp),modifier=Modifier.heightIn(min=44.dp)){Icon(Icons.Outlined.ChatBubbleOutline,"Reply",Modifier.size(16.dp),tint=MaterialTheme.colorScheme.onSurfaceVariant);Text(" "+if(post.replies>0)post.replies.toString() else "Reply",fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)}
                Spacer(Modifier.weight(1f))
                post.raw.optJSONObject("author")?.optJSONObject("communityToken")?.let { own->TextButton(onClick={onCreatorToken(own.string("address"))},contentPadding=PaddingValues(4.dp),modifier=Modifier.widthIn(max=110.dp)){TokenArtwork(Asset.parse(JSONObject(own.toString()).put("id",own.string("address"))),18.dp);Spacer(Modifier.width(4.dp));Text(own.string("symbol"),fontSize=10.sp,maxLines=1,overflow=TextOverflow.Ellipsis)} }
            }
        }
    }
    HorizontalDivider(color=MaterialTheme.colorScheme.outlineVariant)
}

@Composable fun TokenConversation(vm: RallyViewModel,asset: Asset,onAuthor: (String)->Unit={},onToken: (String)->Unit={}) {
    val state by vm.state.collectAsStateWithLifecycle();val owner=vm.me?.string("id")
    val key="comments:${asset.id}:$owner";val path="/api/posts?discussion=1&feed=latest&mode=for-you&asset="+Uri.encode(asset.id)
    val page=state.pages[key] ?: Page(loading=true)
    var text by rememberSaveable(asset.id,owner){mutableStateOf("")};var parent by rememberSaveable(asset.id,owner){mutableStateOf<String?>(null)};var handle by rememberSaveable(asset.id,owner){mutableStateOf("")};var requestKey by rememberSaveable(asset.id,owner){mutableStateOf("android-comment-"+UUID.randomUUID())}
    val focus=remember {FocusRequester()};val focusManager=LocalFocusManager.current;val keyboard=LocalSoftwareKeyboardController.current
    LaunchedEffect(parent){if(parent!=null)focus.requestFocus()}
    LaunchedEffect(key){vm.load(key,path,"posts")}
    Column(Modifier.fillMaxWidth(),verticalArrangement=Arrangement.spacedBy(8.dp)) {
        if(parent!=null)Row(verticalAlignment=Alignment.CenterVertically){Text("Replying to @$handle",Modifier.weight(1f),fontSize=11.sp,color=MaterialTheme.colorScheme.onSurfaceVariant);IconButton(onClick={parent=null}){Icon(Icons.Outlined.Close,"Cancel reply",Modifier.size(16.dp))}}
        Row(Modifier.fillMaxWidth().imePadding(),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(8.dp)) {
            OutlinedTextField(text,{text=it;requestKey="android-comment-"+UUID.randomUUID()},Modifier.weight(1f).focusRequester(focus),placeholder={Text("Comment on $${asset.symbol}…",fontSize=12.sp)},maxLines=4,shape=RoundedCornerShape(18.dp),enabled=!state.busy,textStyle=LocalTextStyle.current.copy(fontSize=13.sp))
            FilledIconButton(onClick={vm.action("/api/posts",JSONObject().put("text",text.trim()).put("asset",asset.id).apply {parent?.let{put("parent",it)}},requestKey){text="";parent=null;focusManager.clearFocus();keyboard?.hide();requestKey="android-comment-"+UUID.randomUUID();vm.load(key,path,"posts",true)}},enabled=text.isNotBlank() && text.length<=4000 && !state.busy,colors=IconButtonDefaults.filledIconButtonColors(containerColor=Color(0xFF075DE3),contentColor=Color.White)){Icon(Icons.Outlined.ArrowUpward,"Post comment")}
        }
        if(page.loading && page.items.isEmpty())LinearProgressIndicator(Modifier.fillMaxWidth())
        if(page.error!=null)TextButton(onClick={vm.load(key,path,"posts",true)}){Text("Retry conversation")}
        if(!page.loading && page.items.isEmpty() && page.error==null)Text("Be the first to comment.",Modifier.padding(vertical=20.dp),fontSize=12.sp,color=MaterialTheme.colorScheme.onSurfaceVariant)
        page.items.forEach { row->key(row.string("id")){val p=Post.parse(row).withReaction(state.reactions[row.string("id")]);TokenCommentRow(p,{parent=p.id;handle=p.author.handle},{},{vm.react(p)},{onAuthor(p.author.id)},onCreatorToken=onToken,onMention=onAuthor,inside=true,reactionPending=state.reactions[p.id]?.pending==true)} }
        if(page.cursor!=null)TextButton(onClick={vm.load(key,path+"&cursor="+Uri.encode(page.cursor),"posts",append=true)},enabled=!page.loading,modifier=Modifier.fillMaxWidth()){Text("Load more")}
    }
}
