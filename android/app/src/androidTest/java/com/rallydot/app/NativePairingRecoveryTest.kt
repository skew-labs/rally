package com.rallydot.app
import android.app.Application
import androidx.lifecycle.ViewModelStore
import androidx.lifecycle.ViewModelProvider
import androidx.test.platform.app.InstrumentationRegistry
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.ResponseBody.Companion.toResponseBody
import org.json.JSONObject
import org.junit.Test
import org.junit.Assert.*
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicInteger
class NativePairingRecoveryTest {
 @Test fun restoredProofAdoptsSessionAndOldAnonymousBootstrapCannotUndoIt() {
  val inst=InstrumentationRegistry.getInstrumentation();val app=inst.targetContext.applicationContext as Application
  val credentials=CredentialStore(app,"qa-pairing-session",true);val proof=DurablePairing(app,"qa-pairing-request")
  val pending=NativePairing("a".repeat(32),"b".repeat(43),"0123",System.currentTimeMillis()/1000+600)
  credentials.clear();proof.clear();proof.save(pending)
  val token="c".repeat(43);val polls=AtomicInteger();val stale=CountDownLatch(1);val releaseStale=CountDownLatch(1)
  val client=OkHttpClient.Builder().addInterceptor { chain->
   val r=chain.request();val path=r.url.encodedPath
   val body=when(path) {
    "/api/native/poll" -> { assertEquals(pending.id,JSONObject(r.body!!.let { body->val b=okio.Buffer();body.writeTo(b);b.readUtf8() }).string("id"));if(polls.incrementAndGet()==1)throw java.io.IOException("QA lost exchange response");JSONObject().put("state","approved").put("session",token).toString() }
    "/api/bootstrap" -> if(r.header("Cookie")=="rally_session=$token")JSONObject().put("me",JSONObject().put("id","qa-native")).put("wallet","").toString() else { stale.countDown();releaseStale.await(10,TimeUnit.SECONDS);JSONObject().put("me",JSONObject.NULL).put("wallet","").toString() }
    "/api/auth/config" -> JSONObject().put("privy",JSONObject().put("enabled",false)).toString()
    else->throw AssertionError("Unexpected request $path")
   }
   Response.Builder().request(r).protocol(Protocol.HTTP_1_1).code(200).message("QA").body(body.toResponseBody("application/json".toMediaType())).build()
  }.build()
  val api=RallyApi(app,client,credentials);val store=ViewModelStore();var model: RallyViewModel?=null
  try {
   inst.runOnMainSync { model=ViewModelProvider(store,object:ViewModelProvider.Factory { override fun <T:androidx.lifecycle.ViewModel> create(modelClass:Class<T>):T { @Suppress("UNCHECKED_CAST") return RallyViewModel(app,api,proof) as T } })[RallyViewModel::class.java] }
   assertTrue(stale.await(5,TimeUnit.SECONDS))
   inst.runOnMainSync { model!!.returnedToApp("rallyconnect://account?nativeRequest="+pending.id) }
   val until=System.currentTimeMillis()+15000
   while(model!!.state.value.boot?.optJSONObject("me")?.string("id")!="qa-native" && System.currentTimeMillis()<until)Thread.sleep(50)
   assertEquals("qa-native",model!!.state.value.boot?.optJSONObject("me")?.string("id"));assertEquals(token,credentials.load());assertNull(proof.read())
   releaseStale.countDown();Thread.sleep(500)
   assertEquals("qa-native",model!!.state.value.boot?.optJSONObject("me")?.string("id"))
   val restored=RallyApi(app,client,CredentialStore(app,"qa-pairing-session",true))
   kotlinx.coroutines.runBlocking { assertEquals("qa-native",restored.get("/api/bootstrap?markets=0",true).getJSONObject("me").string("id")) }
   assertEquals(2,polls.get())
  } finally { releaseStale.countDown();inst.runOnMainSync { store.clear() };credentials.clear();proof.clear();client.dispatcher.executorService.shutdown() }
 }
}
