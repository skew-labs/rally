package com.rallydot.app

import android.app.Application
import androidx.activity.compose.setContent
import androidx.compose.material3.Text
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.padding
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.compose.runtime.mutableStateOf
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelProvider
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.json.JSONObject
import org.junit.Test
import org.junit.Assert.*
import kotlinx.coroutines.*
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

class ProfileEditingTest {
 @Test fun profileSaveUsesCanonicalResponseWithoutWaitingForBootstrap() {
  val inst=InstrumentationRegistry.getInstrumentation();val app=inst.targetContext.applicationContext as Application
  val credentials=CredentialStore(app,"qa-profile-session",true);val pending=DurablePairing(app,"qa-profile-pairing");credentials.clear();pending.clear()
  var posts=0;var reads=0;var reject=false
  val person=JSONObject().put("id","qa-profile").put("name","Original").put("handle","original").put("avatar","")
  val client=OkHttpClient.Builder().addInterceptor { chain->
   val r=chain.request();val path=r.url.encodedPath;var code=200
   val body=when(path) {
    "/api/bootstrap"->{reads++;JSONObject().put("me",person).put("wallet","")}
    "/api/auth/config"->JSONObject().put("privy",JSONObject().put("enabled",false))
    "/api/profile"->{posts++;if(reject){code=409;JSONObject().put("message","That username is taken")}else JSONObject().put("id","qa-profile").put("name","Canonical Name").put("handle","canonical").put("avatar","/media/"+"a".repeat(32))}
    else->throw AssertionError("Unexpected request $path")
   }
   Response.Builder().request(r).protocol(Protocol.HTTP_1_1).code(code).message("QA").body(body.toString().toResponseBody("application/json".toMediaType())).build()
  }.build()
  val store=ViewModelStore();var vm:RallyViewModel?=null
  try {
   inst.runOnMainSync {vm=ViewModelProvider(store,object:ViewModelProvider.Factory {override fun<T:androidx.lifecycle.ViewModel>create(c:Class<T>):T {@Suppress("UNCHECKED_CAST")return RallyViewModel(app,RallyApi(app,client,credentials),pending) as T}})[RallyViewModel::class.java]}
   val deadline=System.currentTimeMillis()+5000;while(vm!!.me==null&&System.currentTimeMillis()<deadline)Thread.sleep(30)
   assertNotNull(vm!!.me);val before=reads
   runBlocking(Dispatchers.Main){vm!!.saveProfile(JSONObject().put("name","typed"))}
   assertEquals("Canonical Name",vm!!.me!!.string("name"));assertEquals("canonical",vm!!.me!!.string("handle"));assertEquals(before,reads);assertEquals(1,posts)
   reject=true
   try {runBlocking(Dispatchers.Main){vm!!.saveProfile(JSONObject().put("handle","rally"))};fail("Expected error")}catch(e:ApiFailure){assertTrue(e.message.orEmpty().contains("taken"))}
   assertEquals("canonical",vm!!.me!!.string("handle"))
  } finally {inst.runOnMainSync{store.clear()};credentials.clear();pending.clear();client.dispatcher.executorService.shutdown()}
 }
 @Test fun editorKeepsDraftOnFailureAndSavesFromKeyboard() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst)
  val me=JSONObject().put("id","qa-editor").put("name","Original Name").put("handle","original").put("bio","")
  var calls=0;var result:JSONObject?=null;val complete=mutableStateOf(false)
  ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity {activity->activity.setContent {RallyTheme(false){if(complete.value)Box(Modifier.padding(48.dp)){Text("Profile saved in QA")} else ProfileEditor(me,{fields,_->calls++;if(calls==1)throw IllegalStateException("That username is taken");result=fields},{complete.value=true},{complete.value=true})}}}
   assertTrue(device.wait(Until.hasObject(By.text("Edit profile")),5000))
   val fields=device.findObjects(By.clazz("android.widget.EditText"));assertEquals(3,fields.size)
   fields[0].click();fields[0].text="Edited Name";fields[1].click();fields[1].text="edited_user"
   device.takeScreenshot(java.io.File(inst.targetContext.getExternalFilesDir(null),"profile-editor-keyboard.png"))
   device.findObject(By.text("Save")).click()
   assertTrue(device.wait(Until.hasObject(By.text("That username is taken")),5000))
   assertNotNull(device.findObject(By.text("Edited Name")))
   device.takeScreenshot(java.io.File(inst.targetContext.getExternalFilesDir(null),"profile-editor-error.png"))
   device.findObject(By.text("Save")).click()
   assertTrue(device.wait(Until.hasObject(By.text("Profile saved in QA")),5000));assertEquals(2,calls);assertEquals("Edited Name",result!!.string("name"));assertEquals("edited_user",result!!.string("handle"))
  }
 }
}
