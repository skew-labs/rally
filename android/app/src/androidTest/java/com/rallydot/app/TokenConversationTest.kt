package com.rallydot.app

import android.app.Application
import androidx.activity.compose.setContent
import androidx.compose.foundation.*
import androidx.compose.foundation.layout.*
import androidx.compose.material3.*
import androidx.compose.runtime.*
import androidx.compose.ui.Modifier
import androidx.compose.ui.unit.dp
import androidx.lifecycle.ViewModelStore
import androidx.test.core.app.ActivityScenario
import androidx.test.platform.app.InstrumentationRegistry
import androidx.test.uiautomator.*
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import okio.Buffer
import org.json.*
import org.junit.Assert.*
import org.junit.Test
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

class TokenConversationTest {
 @Test fun commentsRepliesAndSavedFeedStayInsideTheApp() {
  val inst=InstrumentationRegistry.getInstrumentation();val device=UiDevice.getInstance(inst);val app=inst.targetContext.applicationContext as Application;val store=ViewModelStore()
  val credentials=CredentialStore(app,"qa-token-discussion",true).apply{clear()}
  val person=JSONObject().put("id","qa-reader").put("name","QA reader").put("handle","qa_reader").put("kind","person")
  val address="0x"+"a".repeat(40);val token=JSONObject().put("id",address).put("symbol","QA").put("name","QA token")
  val feed=JSONObject().put("id","qa-free").put("name","QA signals").put("owner","qa-reader").put("access",true).put("priceRaw","0")
  val posts=CopyOnWriteArrayList<JSONObject>();val writes=CopyOnWriteArrayList<JSONObject>();var active="latest"
  posts.add(JSONObject().put("id","qa-root").put("author",person).put("asset",address).put("assetInfo",token).put("text","QA conversation").put("created",System.currentTimeMillis()/1000))
  val client=OkHttpClient.Builder().addInterceptor { chain->val r=chain.request();val body=r.body?.let{val b=Buffer();it.writeTo(b);JSONObject(b.readUtf8())}
   val response=when(r.url.encodedPath){
    "/api/bootstrap"->JSONObject().put("me",person).put("wallet","").put("activeFeed",active).put("feeds",JSONArray().put(feed)).put("people",JSONArray().put(person)).put("communities",JSONArray())
    "/api/auth/config"->JSONObject("""{"privy":{"enabled":false}}""")
    "/api/posts"->if(body==null)JSONObject().put("posts",JSONArray(posts)) else {
      assertEquals(address,body.string("asset"));assertNotNull(r.header("Idempotency-Key"));writes.add(body)
      JSONObject().put("id","qa-comment-"+writes.size).put("author",person).put("asset",address).put("text",body.string("text")).put("parent",body.opt("parent")).put("created",System.currentTimeMillis()/1000).also { posts.add(0,it) }
    }
    "/api/feeds/use"->{assertEquals("qa-free",body?.string("id"));active="qa-free";feed.put("subscribed",true).put("subscriptionSaved",true);JSONObject().put("ok",true)}
    else->{assertEquals("GET",r.method);JSONObject()}
   };Response.Builder().request(r).protocol(Protocol.HTTP_1_1).code(200).message("QA").body(response.toString().toResponseBody("application/json".toMediaType())).build()
  }.build()
  try { ActivityScenario.launch(RallyActivity::class.java).use { scenario->
   scenario.onActivity { activity->val vm=RallyViewModel(app,RallyApi(app,client,credentials),DurablePairing(app,"qa-token-discussion"));store.put("vm",vm);activity.setContent{val state by vm.state.collectAsState();RallyTheme(false){Column(Modifier.fillMaxSize().verticalScroll(rememberScrollState()).padding(16.dp)){TextButton(onClick={vm.useFeed("qa-free")}){Text("Subscribe free")};Text("Active: "+state.boot?.string("activeFeed"));TokenConversation(vm,Asset.parse(token))}}} }
   assertTrue(device.wait(Until.hasObject(By.text("QA conversation")),10000))
   device.findObject(By.clazz("android.widget.EditText")).text="QA new comment"
   device.wait(Until.findObject(By.desc("Post comment").enabled(true)),5000).click();assertTrue(device.wait(Until.hasObject(By.text("QA new comment")),10000));assertEquals(1,writes.size)
   assertTrue(device.wait(Until.hasObject(By.textContains("Reply")),5000));device.findObjects(By.textContains("Reply")).first().click();assertTrue(device.wait(Until.hasObject(By.text("Replying to @qa_reader")),5000))
   device.findObject(By.clazz("android.widget.EditText")).text="QA reply";device.wait(Until.findObject(By.desc("Post comment").enabled(true)),5000).click()
   val replyVisible=device.wait(Until.hasObject(By.text("QA reply")),10000)
   if(!replyVisible){device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"reply-failure.png"));device.dumpWindowHierarchy(File(inst.targetContext.getExternalFilesDir(null),"reply-failure.xml"))}
   assertTrue("Reply missing; submitted="+writes.map{it.toString()},replyVisible);assertEquals("qa-comment-1",writes[1].string("parent"))
   scenario.onActivity { activity->(activity.getSystemService(android.content.Context.INPUT_METHOD_SERVICE) as android.view.inputmethod.InputMethodManager).hideSoftInputFromWindow(activity.window.decorView.windowToken,0) };device.swipe(device.displayWidth/2,250,device.displayWidth/2,device.displayHeight-150,20)
   assertTrue(device.wait(Until.hasObject(By.text("Subscribe free")),5000));device.findObject(By.text("Subscribe free")).click();assertTrue(device.wait(Until.hasObject(By.text("Active: qa-free")),10000))
   device.takeScreenshot(File(inst.targetContext.getExternalFilesDir(null),"token-conversation.png"))
  } } finally {inst.runOnMainSync{store.clear()};credentials.clear();client.dispatcher.executorService.shutdown()}
 }
}
