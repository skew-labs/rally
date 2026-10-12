package com.rallydot.app

import android.net.Uri
import androidx.activity.compose.rememberLauncherForActivityResult
import androidx.activity.result.PickVisualMediaRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.text.KeyboardOptions
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.runtime.saveable.rememberSaveable
import androidx.compose.ui.Modifier
import androidx.compose.ui.Alignment
import androidx.compose.ui.platform.LocalFocusManager
import androidx.compose.ui.text.input.KeyboardCapitalization
import androidx.compose.ui.text.input.KeyboardType
import androidx.compose.ui.unit.dp
import kotlinx.coroutines.CancellationException
import kotlinx.coroutines.launch
import org.json.JSONObject

@OptIn(ExperimentalMaterial3Api::class)
@Composable fun ProfileEditor(me: JSONObject,save: suspend (JSONObject,Uri?)->Unit,saved: ()->Unit,close: ()->Unit) {
    val id=me.string("id")
    var name by rememberSaveable(id) { mutableStateOf(me.string("name")) }
    var handle by rememberSaveable(id) { mutableStateOf(me.string("handle")) }
    var bio by rememberSaveable(id) { mutableStateOf(me.string("bio")) }
    var photo by rememberSaveable(id) { mutableStateOf<String?>(null) }
    var removed by rememberSaveable(id) { mutableStateOf(false) }
    var pending by remember { mutableStateOf(false) };var error by remember { mutableStateOf<String?>(null) }
    val scope=rememberCoroutineScope();val focus=LocalFocusManager.current
    val picker=rememberLauncherForActivityResult(ActivityResultContracts.PickVisualMedia()) { uri->if(uri!=null && !pending) { photo=uri.toString();removed=false;error=null } }
    val sheet=rememberModalBottomSheetState(skipPartiallyExpanded=true,confirmValueChange={ !pending })
    ModalBottomSheet(onDismissRequest={if(!pending)close()},sheetState=sheet,containerColor=MaterialTheme.colorScheme.surface,contentWindowInsets={WindowInsets.safeDrawing}) {
        Column(Modifier.fillMaxWidth().imePadding().padding(horizontal=20.dp).padding(bottom=20.dp)) {
            Row(Modifier.fillMaxWidth().padding(bottom=12.dp),verticalAlignment=Alignment.CenterVertically) {
                Text("Edit profile",Modifier.weight(1f),style=MaterialTheme.typography.titleLarge)
                Button(enabled=!pending,onClick={
                    focus.clearFocus()
                    val username=handle.trim().removePrefix("@").lowercase(java.util.Locale.ROOT)
                    if(name.trim().isEmpty()){error="Enter your name";return@Button}
                    if(!Regex("[a-z0-9_]{3,24}").matches(username)){error="Use 3–24 letters, numbers or underscores";return@Button}
                    pending=true;error=null
                    scope.launch { try {
                        val fields=JSONObject().put("name",name.trim()).put("handle",username).put("bio",bio.trim())
                        if(removed)fields.put("avatarMedia","")
                        save(fields,photo?.let(Uri::parse));pending=false;sheet.hide();saved()
                    } catch(e:CancellationException){throw e} catch(e:Exception){error=e.message ?: "Could not save. Try again."} finally {pending=false} }
                }) { if(pending)CircularProgressIndicator(Modifier.size(18.dp),strokeWidth=2.dp) else Text("Save") }
            }
            error?.let { Text(it,Modifier.padding(bottom=12.dp),color=MaterialTheme.colorScheme.error,style=MaterialTheme.typography.bodyMedium) }
            Column(Modifier.weight(1f,false).verticalScroll(rememberScrollState()),verticalArrangement=Arrangement.spacedBy(16.dp)) {
                Row(Modifier.fillMaxWidth().padding(vertical=8.dp),verticalAlignment=Alignment.CenterVertically,horizontalArrangement=Arrangement.spacedBy(12.dp)) {
                    Artwork(photo ?: if(removed)null else safeImage(me.string("avatar")),name,72.dp)
                    TextButton(enabled=!pending,onClick={picker.launch(PickVisualMediaRequest(ActivityResultContracts.PickVisualMedia.ImageOnly))}) { Text("Change photo") }
                    if(photo!=null || !removed && me.string("avatar").isNotBlank())TextButton(enabled=!pending,onClick={photo=null;removed=true}) { Text("Remove") }
                }
                OutlinedTextField(name,{if(it.length<=48)name=it},Modifier.fillMaxWidth(),enabled=!pending,singleLine=true,label={Text("Name")},keyboardOptions=KeyboardOptions(capitalization=KeyboardCapitalization.Words))
                OutlinedTextField(handle,{if(it.length<=25)handle=it},Modifier.fillMaxWidth(),enabled=!pending,singleLine=true,label={Text("Username")},supportingText={Text("3–24 letters, numbers or underscores")},keyboardOptions=KeyboardOptions(capitalization=KeyboardCapitalization.None,autoCorrectEnabled=false,keyboardType=KeyboardType.Ascii))
                OutlinedTextField(bio,{if(it.length<=240)bio=it},Modifier.fillMaxWidth(),enabled=!pending,minLines=3,maxLines=5,label={Text("Bio")},supportingText={Text("${bio.length} / 240")})
                TextButton(enabled=!pending,onClick=close,modifier=Modifier.align(Alignment.CenterHorizontally)) {Text("Cancel")}
            }
        }
    }
}
