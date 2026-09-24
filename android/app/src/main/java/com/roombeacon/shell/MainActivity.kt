package com.roombeacon.shell

import android.app.Activity
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Intent
import android.content.IntentFilter
import android.content.pm.ActivityInfo
import android.graphics.Color
import android.os.Build
import android.os.Bundle
import android.util.Log
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.WebView
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import org.json.JSONObject

/** V6: native enrollment and remote configuration; no local password or server entry. */
class MainActivity : Activity() {
    private var agent: DeviceAgent? = null
    private var shell: WebShell? = null
    private var resumed = false
    private var configuredRevision = 0
    private var waiting: TextView? = null
    private var applying = false
    private var currentCode = ""
    private val prefs by lazy { getSharedPreferences("managed_state", MODE_PRIVATE) }
    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (!BuildConfig.DEBUG) window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        currentCode = prefs.getString("code", "") ?: ""
        showWaiting(JSONObject(), "正在连接管理服务器")
        try {
            val identity = DeviceIdentity(this)
            identity.token // Resolve once on startup; do not silently replace unreadable identity.
            agent = DeviceAgent(this, identity) { value, metadata, error -> accept(value, metadata, error) }
        } catch (error: Exception) {
            Log.e("RoomBeacon", "identity_failed:${error.javaClass.simpleName}")
            showWaiting(JSONObject(), "设备身份不可用，请联系管理员恢复")
        }
        val manager = getSystemService(DevicePolicyManager::class.java)
        if (manager.isDeviceOwnerApp(packageName)) {
            val admin = ComponentName(this, KioskAdminReceiver::class.java)
            val filter = IntentFilter(Intent.ACTION_MAIN).apply {
                addCategory(Intent.CATEGORY_HOME); addCategory(Intent.CATEGORY_DEFAULT)
            }
            manager.addPersistentPreferredActivity(admin, filter, ComponentName(this, "com.roombeacon.shell.HomeActivity"))
            manager.setLockTaskPackages(admin, arrayOf(packageName))
            if (manager.isLockTaskPermitted(packageName)) startLockTask()
        }
    }
    @Suppress("DEPRECATION")
    private fun immersive() {
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or
            View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_LAYOUT_STABLE
    }
    private fun text(value: String, size: Float, color: Int = Color.WHITE) = TextView(this).apply {
        text = value; textSize = size; setTextColor(color); gravity = Gravity.CENTER; setPadding(20, 8, 20, 8)
    }
    private fun showWaiting(metadata: JSONObject, message: String) {
        if (shell != null) { shell?.destroy(); shell = null; configuredRevision = 0 }
        requestedOrientation = ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
        val layout = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; gravity = Gravity.CENTER; setBackgroundColor(0xff0c172b.toInt())
            setPadding(32, 20, 32, 20)
        }
        layout.addView(text("RoomBeacon  V6", 20f, 0xff8fa8d6.toInt()))
        layout.addView(text("等待后台部署", 32f))
        val code = if (currentCode.length == 6) currentCode.chunked(3).joinToString(" ") else "正在获取唯一码"
        layout.addView(text(code, 54f, 0xff88aeff.toInt()))
        layout.addView(text("请在管理后台核对唯一码并分配会议室", 18f, 0xff9baecb.toInt()))
        val serial = metadata.optString("serial").ifEmpty { "系统未提供" }
        val model = metadata.optString("model").ifEmpty { Build.MODEL }
        val interfaces = metadata.optJSONArray("interfaces")
        val addresses = mutableListOf<String>()
        if (interfaces != null) for (i in 0 until interfaces.length()) {
            val nic = interfaces.getJSONObject(i)
            val mac = nic.optString("mac")
            if (mac.isNotEmpty()) addresses.add("${nic.optString("name")}  $mac")
        }
        layout.addView(text("$model  ·  SN $serial\nMAC ${addresses.take(3).joinToString("  /  ").ifEmpty { "系统未提供" }}", 16f, 0xff9baecb.toInt()))
        val network = when (metadata.optString("network")) { "wifi" -> "Wi-Fi"; "ethernet" -> "有线 / PoE"; else -> "网络待连接" }
        waiting = text("$network  ·  $message", 17f, 0xffb7c9e9.toInt())
        layout.addView(waiting)
        setContentView(layout); immersive()
    }
    private fun accept(value: JSONObject?, metadata: JSONObject, error: String?) {
        if (!resumed) return
        if (value == null) {
            if (shell == null) showWaiting(metadata, error ?: "等待连接")
            // Existing H5 independently fails closed on expired data and web-session expiry.
            return
        }
        currentCode = value.getString("code")
        if (value.getString("status") != "active") {
            CookieManager.getInstance().setCookie(DeviceAgent.ORIGIN,
                "__Host-rb_device=; Path=/; Max-Age=0; Secure; HttpOnly; SameSite=Strict")
            showWaiting(metadata, if (value.getString("status") == "revoked") "设备已撤销，请联系管理员" else "已连接，等待管理员分配")
            agent?.appliedRevision = value.getInt("revision")
            agent?.applyError = ""
            return
        }
        if (applying) return
        val revision = value.getInt("revision")
        val config = value.getJSONObject("config")
        val session = value.getString("web_session")
        try { ManagedPolicy.validate(config.getString("version"), config.getString("node_id"), revision,
            value.getString("id"), session)
            lightProfile(config)
        }
        catch (_: IllegalArgumentException) {
            agent?.applyError = "服务器配置校验失败"
            showWaiting(metadata, "配置内容不支持，请联系管理员")
            return
        }
        applying = true
        CookieManager.getInstance().setAcceptCookie(true)
        CookieManager.getInstance().setCookie(DeviceAgent.ORIGIN,
            "__Host-rb_device=$session; Path=/; Max-Age=300; Secure; HttpOnly; SameSite=Strict") { accepted ->
            applying = false
            if (!resumed) return@setCookie
            if (!accepted) { agent?.applyError = "网页会话写入失败"; return@setCookie }
            if (revision != configuredRevision || shell == null) {
                try { showDisplay(config, revision) }
                catch (failure: Exception) {
                    Log.e("RoomBeacon", "configuration_failed:${failure.javaClass.simpleName}")
                    agent?.applyError = "设备配置应用失败"
                    showWaiting(metadata, "配置应用失败，正在重试")
                }
            }
        }
    }
    private fun showDisplay(config: JSONObject, revision: Int) {
        shell?.destroy(); shell = null
        requestedOrientation = if (config.getBoolean("portrait")) ActivityInfo.SCREEN_ORIENTATION_PORTRAIT else ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
        val root = FrameLayout(this)
        val container = FrameLayout(this)
        val overlay = text("正在加载会议室…", 25f).apply { setBackgroundColor(0xff0c172b.toInt()) }
        root.addView(container, FrameLayout.LayoutParams(-1, -1)); root.addView(overlay, FrameLayout.LayoutParams(-1, -1))
        setContentView(root); immersive()
        val wantsLight = config.getBoolean("room_light")
        val profile = lightProfile(config)
        agent?.applyError = if (wantsLight && profile == null) "当前配置未识别侧边灯接线" else ""
        val light = if (wantsLight && profile != null) try {
            RoomLight.forProfile(profile) { Log.e("RoomBeacon", it); agent?.applyError = "灯控操作失败" }
        } catch (failure: Exception) {
            Log.e("RoomBeacon", "light_setup_failed:${failure.javaClass.simpleName}")
            agent?.applyError = "模板灯控暂不可用，显示配置已应用"
            null
        } else null
        configuredRevision = revision
        shell = WebShell(this, container, OriginPolicy(DeviceAgent.ORIGIN, false), light,
            entryPath = ManagedPolicy.displayPath(config.getString("version"), config.optString("theme_mode", "auto"),
                config.optString("language", "zh-CN"))) { message ->
            overlay.text = message ?: ""; overlay.visibility = if (message == null) View.GONE else View.VISIBLE
            if (message == null) {
                agent?.appliedRevision = revision
                shell?.reportViewport { agent?.viewport = it }
            }
        }
        if (resumed) shell?.resume()
    }
    override fun onResume() { super.onResume(); resumed = true; immersive(); agent?.start(); shell?.resume() }
    private fun lightProfile(config: JSONObject): RoomLight.Profile? {
        val wiring = config.optJSONObject("light_wiring")
        if (wiring != null) {
            require(RoomLight.supports(Build.MODEL,Build.DISPLAY)) { "设备未支持灯控驱动" }
            val pins = wiring.getJSONObject("pins")
            return ManagedPolicy.wiring(pins.getInt("red"),pins.getInt("green"),pins.getInt("blue"),wiring.getInt("active_level"))
        }
        return ManagedPolicy.lightProfile(config.optString("device_profile","auto"),Build.MODEL,Build.DISPLAY)
    }
    override fun onPause() { resumed = false; agent?.stop(); shell?.pause(); super.onPause() }
    override fun onDestroy() { agent?.stop(); shell?.destroy(); super.onDestroy() }
    @Deprecated("Dedicated display does not navigate backwards")
    override fun onBackPressed() { immersive() }
}
