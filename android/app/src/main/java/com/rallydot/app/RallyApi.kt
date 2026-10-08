package com.rallydot.app

import android.content.Context
import android.net.Uri
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlinx.coroutines.withContext
import okhttp3.*
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.RequestBody.Companion.asRequestBody
import org.json.JSONObject
import java.io.IOException
import java.security.KeyStore
import java.util.concurrent.TimeUnit
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import okio.Buffer
import kotlin.coroutines.resume
import kotlin.coroutines.resumeWithException

/** Only the app session is persisted. No wallet key, credential, quote or pending transaction. */
class CredentialStore(context: Context) {
    private val preferences=context.getSharedPreferences("native-session", Context.MODE_PRIVATE)
    private fun key(): SecretKey {
        val ks=KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        return (ks.getKey("rally-session",null) as? SecretKey) ?: KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES,"AndroidKeyStore").apply {
            init(KeyGenParameterSpec.Builder("rally-session",KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT).setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        }.generateKey()
    }
    fun load(): String? = try {
        preferences.getString("session",null)?.let { value -> val fields=value.split(':'); val c=Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.DECRYPT_MODE,key(),GCMParameterSpec(128,Base64.decode(fields[0],Base64.NO_WRAP))); String(c.doFinal(Base64.decode(fields[1],Base64.NO_WRAP)),Charsets.UTF_8) }
    } catch (_: Exception) { clear(); null }
    fun save(value: String) { val c=Cipher.getInstance("AES/GCM/NoPadding"); c.init(Cipher.ENCRYPT_MODE,key()); preferences.edit().putString("session",Base64.encodeToString(c.iv,Base64.NO_WRAP)+":"+Base64.encodeToString(c.doFinal(value.toByteArray(Charsets.UTF_8)),Base64.NO_WRAP)).apply() }
    fun clear() { preferences.edit().remove("session").apply() }
}
class ApiFailure(val status: Int, message: String): IOException(message)
class RallyApi(private val context: Context) {
    private val store=CredentialStore(context)
    @Volatile private var session: String?=store.load()
    @Volatile private var generation=0
    private val client=OkHttpClient.Builder().connectTimeout(8,TimeUnit.SECONDS).readTimeout(12,TimeUnit.SECONDS).callTimeout(18,TimeUnit.SECONDS).followRedirects(false).retryOnConnectionFailure(false).build()
    private val cache=LinkedHashMap<String, Pair<Long,JSONObject>>()
    fun signIn(token: String) { require(Regex("[A-Za-z0-9_-]{40,100}").matches(token));generation++;session=token; store.save(token); clearCache() }
    fun signOut() { generation++;session=null;store.clear();clearCache() }
    fun clearCache() = synchronized(cache) { cache.clear() }
    suspend fun get(path: String, force: Boolean=false): JSONObject {
        synchronized(cache) { cache[path]?.takeIf { !force && System.currentTimeMillis()-it.first < 20000 }?.let { return it.second } }
        val data=request(path,null)
        synchronized(cache) { cache[path]=System.currentTimeMillis() to data;while(cache.size>50)cache.remove(cache.keys.first()) }
        return data
    }
    suspend fun post(path: String, body: JSONObject, key: String?=null): JSONObject = request(path,body,key)
    private suspend fun request(path: String, body: JSONObject?, key: String?=null): JSONObject {
        val requestGeneration=generation
        require(path.startsWith("/api/") && !path.contains("\\") && !path.contains(".."))
        val builder=Request.Builder().url(ORIGIN+path).header("Accept","application/json").header("X-Rally-Request","1")
        key?.let { builder.header("Idempotency-Key",it) }
        session?.let { builder.header("Cookie","rally_session=$it") }
        if(body!=null)builder.post(body.toString().toRequestBody("application/json".toMediaType()))
        val call=client.newCall(builder.build())
        val response=suspendCancellableCoroutine<Response> { continuation ->
            continuation.invokeOnCancellation { call.cancel() }
            call.enqueue(object: Callback {
                override fun onFailure(call: Call, e: IOException) { if(continuation.isActive)continuation.resumeWithException(e) }
                override fun onResponse(call: Call,response: Response) { if(continuation.isActive)continuation.resume(response) else response.close() }
            })
        }
        return withContext(Dispatchers.IO) { response.use {
            val input=it.body ?: throw IOException("Empty response")
            // Keep decompressed catalog bodies bounded, including a hostile upstream response.
            if(input.contentLength()>4_000_000)throw IOException("Response too large")
            val source=input.source(); val buffer=Buffer()
            while(buffer.size <= 4_000_000 && source.read(buffer, (4_000_001-buffer.size).coerceAtMost(8192)) != -1L) { }
            val bytes=buffer.readByteArray()
            if(bytes.size>4_000_000)throw IOException("Response too large")
            val data=JSONObject(String(bytes,Charsets.UTF_8))
            if(!it.isSuccessful)throw ApiFailure(it.code,data.string("message","Could not load this screen"))
            if(requestGeneration!=generation)throw kotlinx.coroutines.CancellationException("Account changed")
            data
        } }
    }
    suspend fun upload(uri: Uri): JSONObject = withContext(Dispatchers.IO) {
        val requestGeneration=generation
        val mime=context.contentResolver.getType(uri) ?: throw IOException("Unsupported file")
        require(mime in setOf("image/jpeg","image/png","image/webp","video/mp4","video/webm")) { "Choose a photo or an MP4 / WebM video" }
        val file=java.io.File.createTempFile("rally-upload-",null,context.cacheDir)
        try {
            context.contentResolver.openInputStream(uri)?.use { input -> file.outputStream().use { output -> val bytes=ByteArray(8192);var total=0L;while(true) { val n=input.read(bytes);if(n<0)break;total+=n;if(total>25*1024*1024)throw IOException("Choose a file under 25 MB");output.write(bytes,0,n) } } } ?: throw IOException("Choose this file again")
            val builder=Request.Builder().url(ORIGIN+"/api/media").header("X-Rally-Request","1").put(file.asRequestBody(mime.toMediaType()))
            session?.let { builder.header("Cookie","rally_session=$it") }
            val call=client.newBuilder().callTimeout(0,TimeUnit.SECONDS).writeTimeout(30,TimeUnit.SECONDS).readTimeout(60,TimeUnit.SECONDS).build().newCall(builder.build())
            val response=suspendCancellableCoroutine<Response> { continuation -> continuation.invokeOnCancellation { call.cancel() };call.enqueue(object:Callback {
                override fun onFailure(call:Call,e:IOException) { if(continuation.isActive)continuation.resumeWithException(e) }
                override fun onResponse(call:Call,response:Response) { if(continuation.isActive)continuation.resume(response) else response.close() }
            }) }
            response.use { val source=it.body?.source() ?: throw IOException("Upload has no response");val buffer=Buffer();while(buffer.size<=65536 && source.read(buffer,(65537-buffer.size).coerceAtMost(8192))!=-1L){};if(buffer.size>65536)throw IOException("Upload response too large");val data=JSONObject(buffer.readUtf8());if(!it.isSuccessful)throw ApiFailure(it.code,data.string("message","Could not upload"));if(requestGeneration!=generation)throw kotlinx.coroutines.CancellationException("Account changed");data }
        } finally { file.delete() }
    }
}
