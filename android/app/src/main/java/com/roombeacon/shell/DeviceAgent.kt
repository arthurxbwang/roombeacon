package com.roombeacon.shell

import android.content.Context
import android.os.Handler
import android.os.Looper
import android.util.Log
import org.json.JSONObject
import java.net.URL
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import javax.net.ssl.HttpsURLConnection

/** Native control channel; the tablet opens outbound HTTPS only. */
class DeviceAgent(private val context: Context, private val identity: DeviceIdentity,
    private val result: (JSONObject?, JSONObject, String?) -> Unit) {
    companion object { const val ORIGIN = "https://roombeacon.thundersoft.com" }
    private val handler = Handler(Looper.getMainLooper())
    private val prefs = context.getSharedPreferences("managed_state", Context.MODE_PRIVATE)
    private var executor: ScheduledExecutorService? = null
    @Volatile private var active = false
    @Volatile private var connection: HttpsURLConnection? = null
    @Volatile var appliedRevision = 0
    @Volatile var applyError = ""
    private var enrolled = prefs.getBoolean("enrolled", false)
    private var generation = 0

    private fun request(path: String, body: JSONObject): JSONObject {
        val conn = URL(ORIGIN + path).openConnection() as HttpsURLConnection
        connection = conn
        try {
            conn.requestMethod = "POST"; conn.instanceFollowRedirects = false
            conn.connectTimeout = 10000; conn.readTimeout = 10000; conn.doOutput = true
            conn.setRequestProperty("Authorization", "Bearer ${identity.token}")
            conn.setRequestProperty("Content-Type", "application/json")
            conn.outputStream.use { it.write(body.toString().toByteArray(Charsets.UTF_8)) }
            if (conn.responseCode != 200) throw DeviceHttpError(conn.responseCode)
            val text = conn.inputStream.bufferedReader().use { it.readText() }
            return JSONObject(text).getJSONObject("data")
        } finally { conn.disconnect(); connection = null }
    }
    fun start() {
        if (active) return
        active = true
        val current = ++generation
        executor = Executors.newSingleThreadScheduledExecutor().also { service ->
            service.scheduleWithFixedDelay({
                if (!active) return@scheduleWithFixedDelay
                var metadata = JSONObject()
                try {
                    metadata = DeviceMetadata.collect(context)
                    val body = JSONObject().put("protocol", 1).put("metadata", metadata)
                        .put("reported_revision", appliedRevision).put("error", applyError.take(160))
                    if (!enrolled) {
                        val registration = request("/api/v6/device/enroll", body)
                        prefs.edit().putBoolean("enrolled", true).putString("code", registration.getString("code")).apply()
                        enrolled = true
                    }
                    val value = request("/api/v6/device/sync", body)
                    prefs.edit().putString("code", value.getString("code")).apply()
                    handler.post { if (active && current == generation) result(value, metadata, null) }
                } catch (error: Exception) {
                    Log.w("RoomBeacon", "management_sync_failed:${error.javaClass.simpleName}")
                    val message = when ((error as? DeviceHttpError)?.status) {
                        401 -> "设备身份已失效，请联系管理员"
                        429 -> "正在等待注册，请稍候"
                        else -> if (metadata.optString("network") == "offline") "等待网络连接" else "暂时无法连接管理服务器，正在重试"
                    }
                    handler.post { if (active && current == generation) result(null, metadata, message) }
                }
            }, 0, 15, TimeUnit.SECONDS)
        }
    }
    fun stop() {
        active = false; generation++
        connection?.disconnect(); executor?.shutdownNow(); executor = null
        handler.removeCallbacksAndMessages(null)
    }
    private class DeviceHttpError(val status: Int): Exception("HTTP $status")
}
