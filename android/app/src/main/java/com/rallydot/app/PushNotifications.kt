package com.rallydot.app

import android.Manifest
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Build
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import com.google.firebase.FirebaseApp
import com.google.firebase.FirebaseOptions
import com.google.firebase.messaging.FirebaseMessaging
import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage
import kotlinx.coroutines.*
import org.json.JSONObject
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Public Firebase configuration only; credentials and wallet authority are never stored here. */
object RallyPush {
    const val CHANNEL="rally_activity"
    private fun prefs(context: Context)=context.getSharedPreferences("rally-push",Context.MODE_PRIVATE)
    fun enabledFor(context: Context,owner: String): Boolean = prefs(context).let { it.getBoolean("enabled",false) && it.getString("owner",null)==owner }
    fun route(raw: String?): Uri? = try {
        val url=Uri.parse(raw ?: "");val full=if(url.scheme==null && raw?.startsWith("/?")==true)Uri.parse(ORIGIN+raw) else url
        if(full.scheme=="https" && full.host=="rallydot.com" && full.port in listOf(-1,443) && full.userInfo==null && full.path=="/" && full.fragment==null)full else null
    } catch (_:Exception) { null }
    fun channel(context: Context) { context.getSystemService(NotificationManager::class.java).createNotificationChannel(NotificationChannel(CHANNEL,"Rally activity",NotificationManager.IMPORTANCE_DEFAULT).apply { description="Subscribed posts, watched-token prices and DEX migrations";lockscreenVisibility=android.app.Notification.VISIBILITY_PRIVATE }) }
    fun restore(context: Context) { val saved=prefs(context);if(saved.getBoolean("enabled",false))saved.getString("config",null)?.let { runCatching { initialize(context,JSONObject(it)) } };channel(context) }
    private fun initialize(context: Context,cfg: JSONObject) {
        if(FirebaseApp.getApps(context).isEmpty())FirebaseApp.initializeApp(context,FirebaseOptions.Builder().setProjectId(cfg.getString("projectId")).setApplicationId(cfg.getString("applicationId")).setApiKey(cfg.getString("apiKey")).setGcmSenderId(cfg.getString("senderId")).build())
    }
    suspend fun enable(context: Context,api: RallyApi,owner: String,cfg: JSONObject) {
        require(cfg.optBoolean("android")) { "Android push is awaiting Firebase configuration" }
        if(Build.VERSION.SDK_INT>=33)require(ContextCompat.checkSelfPermission(context,Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED) { "Allow notifications in Android settings" }
        initialize(context,cfg.getJSONObject("firebase"));channel(context)
        val messaging=FirebaseMessaging.getInstance();messaging.isAutoInitEnabled=true
        val token=suspendCancellableCoroutine<String> { c->messaging.token.addOnSuccessListener { if(c.isActive)c.resume(it) }.addOnFailureListener { if(c.isActive)c.resumeWithException(it) } }
        require(api.get("/api/bootstrap?markets=0",true).optJSONObject("me")?.string("id")==owner) { "The signed-in account changed. Enable notifications again." }
        val device=api.post("/api/push/register",JSONObject().put("kind","android").put("token",token))
        api.post("/api/push/settings",JSONObject().put("enabled",true))
        prefs(context).edit().putString("owner",owner).putString("device",device.getString("id")).putString("config",cfg.getJSONObject("firebase").toString()).putBoolean("enabled",true).apply()
    }
    suspend fun disable(context: Context,api: RallyApi,global: Boolean=false) {
        val saved=prefs(context);val device=saved.getString("device",null)
        try { if(device!=null)api.post("/api/push/remove",JSONObject().put("id",device));if(global)api.post("/api/push/settings",JSONObject().put("enabled",false)) }
        finally { saved.edit().clear().apply();context.getSystemService(NotificationManager::class.java).cancelAll();if(FirebaseApp.getApps(context).isNotEmpty()){FirebaseMessaging.getInstance().isAutoInitEnabled=false;FirebaseMessaging.getInstance().deleteToken()} }
    }
    fun incoming(intent: Intent?): Uri? = route(intent?.data?.toString()) ?: route(intent?.getStringExtra("url"))
    fun show(context: Context,data: Map<String,String>) {
        if(!prefs(context).getBoolean("enabled",false))return
        if(Build.VERSION.SDK_INT>=33 && ContextCompat.checkSelfPermission(context,Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)return
        channel(context);val url=route(data["url"]) ?: Uri.parse("$ORIGIN/?view=notifications");val tag=data["tag"].orEmpty().take(100)
        val intent=Intent(context,RallyActivity::class.java).setData(url).addFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP or Intent.FLAG_ACTIVITY_SINGLE_TOP)
        val pending=PendingIntent.getActivity(context,tag.hashCode(),intent,PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE)
        val notice=NotificationCompat.Builder(context,CHANNEL).setSmallIcon(R.drawable.ic_notification).setContentTitle("Rally").setContentText("New activity in Rally").setContentIntent(pending).setAutoCancel(true).setVisibility(NotificationCompat.VISIBILITY_PRIVATE).setOnlyAlertOnce(true).build()
        context.getSystemService(NotificationManager::class.java).notify(tag,tag.hashCode(),notice)
    }
}
class RallyMessagingService: FirebaseMessagingService() {
    private val scope=CoroutineScope(SupervisorJob()+Dispatchers.IO)
    override fun onMessageReceived(message: RemoteMessage) { RallyPush.show(this,message.data) }
    override fun onNewToken(token: String) {
        val saved=getSharedPreferences("rally-push",Context.MODE_PRIVATE);val owner=saved.getString("owner",null) ?: return
        if(!saved.getBoolean("enabled",false))return
        scope.launch { try { val api=RallyApi(applicationContext);val me=api.get("/api/bootstrap?markets=0",true).optJSONObject("me");if(me?.string("id")==owner && RallyPush.enabledFor(applicationContext,owner)){val previous=saved.getString("device",null);val d=api.post("/api/push/register",JSONObject().put("kind","android").put("token",token));if(previous!=null&&previous!=d.string("id"))api.post("/api/push/remove",JSONObject().put("id",previous));saved.edit().putString("device",d.string("id")).apply()} } catch (_:Exception) { } }
    }
    override fun onDestroy() { scope.cancel();super.onDestroy() }
}
