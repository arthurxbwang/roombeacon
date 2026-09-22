package com.roombeacon.shell

import android.app.Activity
import android.app.AlertDialog
import android.app.admin.DevicePolicyManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.ActivityInfo
import android.content.pm.PackageManager
import android.net.ConnectivityManager
import android.net.Network
import android.os.Bundle
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.provider.Settings
import android.util.Log
import android.text.InputType
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.webkit.CookieManager
import android.webkit.WebStorage
import android.webkit.WebView
import android.widget.*

class MainActivity : Activity() {
    private val prefs by lazy { getSharedPreferences("shell", Context.MODE_PRIVATE) }
    private val handler = Handler(Looper.getMainLooper())
    private lateinit var root: FrameLayout
    private lateinit var webContainer: FrameLayout
    private lateinit var overlay: TextView
    private var shell: WebShell? = null
    private var maintenance = false
    private var resumed = false
    private var authDialog: AlertDialog? = null
    private val exitMaintenance = Runnable { showDisplay() }
    private val connectivity by lazy { getSystemService(ConnectivityManager::class.java) }
    private val networkCallback = object : ConnectivityManager.NetworkCallback() {
        override fun onAvailable(network: Network) {
            handler.post { if (resumed && !maintenance) shell?.networkAvailable() }
        }
    }

    override fun onCreate(state: Bundle?) {
        super.onCreate(state)
        window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
        if (!BuildConfig.DEBUG) window.addFlags(WindowManager.LayoutParams.FLAG_SECURE)
        WebView.setWebContentsDebuggingEnabled(BuildConfig.DEBUG)
        connectivity.registerDefaultNetworkCallback(networkCallback)
        if (prefs.getString("origin", null) == null) showSettings(first = true) else showDisplay()
    }

    @Suppress("DEPRECATION")
    private fun immersive() {
        window.decorView.systemUiVisibility = View.SYSTEM_UI_FLAG_FULLSCREEN or
            View.SYSTEM_UI_FLAG_HIDE_NAVIGATION or View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY or
            View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN or View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION or
            View.SYSTEM_UI_FLAG_LAYOUT_STABLE
    }

    private fun label(text: String, size: Float = 20f) = TextView(this).apply {
        this.text = text; textSize = size; setTextColor(0xffe2e8f0.toInt())
        setPadding(16, 10, 16, 10)
    }

    private fun showDisplay() {
        handler.removeCallbacks(exitMaintenance)
        authDialog?.dismiss(); authDialog = null
        val origin = prefs.getString("origin", null) ?: return showSettings(true)
        maintenance = false
        requestedOrientation = if (prefs.getBoolean("portrait", false))
            ActivityInfo.SCREEN_ORIENTATION_PORTRAIT else ActivityInfo.SCREEN_ORIENTATION_LANDSCAPE
        shell?.destroy()
        root = FrameLayout(this).apply { setBackgroundColor(0xff0b0f19.toInt()) }
        webContainer = FrameLayout(this)
        root.addView(webContainer, FrameLayout.LayoutParams(-1, -1))
        overlay = label("正在连接门牌服务…", 26f).apply {
            gravity = Gravity.CENTER
            setBackgroundColor(0xff0b0f19.toInt())
        }
        root.addView(overlay, FrameLayout.LayoutParams(-1, -1))
        // Native maintenance target remains usable even when the renderer is unresponsive.
        val maintenanceTarget = label("·", 18f).apply {
            gravity = Gravity.CENTER
            contentDescription = "长按打开维护验证"
            setOnLongClickListener { authenticate(); true }
        }
        root.addView(maintenanceTarget, FrameLayout.LayoutParams(64, 64, Gravity.TOP or Gravity.END))
        setContentView(root)
        immersive()
        val light = if (prefs.getBoolean("roomLight", false) && sampleLightSupported()) {
            try { RoomLight.forSample(Build.MODEL, Build.DISPLAY) { Log.e("RoomBeacon", it) } }
            catch (error: Exception) {
                Log.e("RoomBeacon", "灯控初始化失败：${error.javaClass.simpleName}")
                Toast.makeText(this, "灯控不可用，请检查设备接口", Toast.LENGTH_LONG).show()
                null
            }
        } else null
        shell = WebShell(this, webContainer, OriginPolicy(origin, BuildConfig.DEBUG), light) { message ->
            overlay.text = message ?: ""
            overlay.visibility = if (message == null) View.GONE else View.VISIBLE
        }
        if (resumed) shell?.resume()
        val manager = getSystemService(DevicePolicyManager::class.java)
        if (prefs.getBoolean("kiosk", false) && manager.isLockTaskPermitted(packageName)) startLockTask()
    }

    private fun sampleLightSupported() = RoomLight.supports(Build.MODEL, Build.DISPLAY)

    private fun authenticate() {
        if (authDialog != null || maintenance) return
        if (System.currentTimeMillis() < prefs.getLong("blockedUntil", 0)) {
            Toast.makeText(this, "尝试过多，请稍后重试", Toast.LENGTH_LONG).show(); return
        }
        val pin = EditText(this).apply {
            hint = "维护密码"; inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
        }
        val dialog = AlertDialog.Builder(this).setTitle("设备维护").setView(pin)
            .setNegativeButton("取消", null).setPositiveButton("验证", null).create()
        authDialog = dialog
        dialog.setOnDismissListener { authDialog = null }
        dialog.setOnShowListener {
            dialog.getButton(AlertDialog.BUTTON_POSITIVE).setOnClickListener {
                if (PinHash.verify(pin.text.toString(), prefs.getString("pin", "") ?: "")) {
                    prefs.edit().remove("attempts").remove("blockedUntil").apply()
                    dialog.dismiss(); showSettings(false)
                } else {
                    val count = prefs.getInt("attempts", 0) + 1
                    prefs.edit().putInt("attempts", count).apply()
                    pin.text.clear(); pin.error = "密码错误"
                    if (count >= 5) {
                        prefs.edit().putInt("attempts", 0)
                            .putLong("blockedUntil", System.currentTimeMillis() + 30000).apply()
                        dialog.dismiss()
                    }
                }
            }
        }
        dialog.show()
    }

    private fun showSettings(first: Boolean) {
        maintenance = true
        shell?.pause()
        val form = LinearLayout(this).apply {
            orientation = LinearLayout.VERTICAL; setPadding(40, 20, 40, 20)
            setBackgroundColor(0xff0b0f19.toInt())
        }
        form.addView(label(if (first) "RoomBeacon · 首次配置" else "RoomBeacon · 设备维护", 28f))
        val version = WebView.getCurrentWebViewPackage()?.versionName ?: "不可用"
        form.addView(label("APK ${BuildConfig.VERSION_NAME} · WebView $version\n" +
            if (BuildConfig.DEBUG) "调试版：允许本机及指定局域网测试服务器 HTTP；正式接入使用 HTTPS" else "正式版：使用 HTTPS 服务", 16f))
        val address = EditText(this).apply {
            hint = "服务器地址，例如 https://rooms.example.com"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_URI
            setSingleLine(); setText(prefs.getString("origin", ""))
            contentDescription = "服务器地址"
        }
        val pin = EditText(this).apply {
            hint = if (first) "设置维护密码（6—64 位）" else "新维护密码（留空保持）"
            inputType = InputType.TYPE_CLASS_TEXT or InputType.TYPE_TEXT_VARIATION_PASSWORD
            contentDescription = "维护密码"
        }
        val portrait = CheckBox(this).apply { text = "使用竖屏"; isChecked = prefs.getBoolean("portrait", false) }
        val roomLight = CheckBox(this).apply {
            setText(R.string.room_light)
            contentDescription = "同步侧边灯"
            isEnabled = sampleLightSupported()
            isChecked = isEnabled && prefs.getBoolean("roomLight", false)
        }
        val message = label("更换服务器会清除原有网页绑定；设备凭证在网页中录入。", 16f)
        form.addView(address); form.addView(pin); form.addView(portrait); form.addView(roomLight); form.addView(message)
        fun button(text: String, action: () -> Unit) {
            form.addView(Button(this).apply { this.text = text; setOnClickListener { action() } })
        }
        button("保存并打开门牌") {
            try {
                val policy = OriginPolicy(address.text.toString(), BuildConfig.DEBUG)
                val password = pin.text.toString()
                require((!first && password.isEmpty()) || password.length in 6..64) { "维护密码须为 6—64 位" }
                val previous = prefs.getString("origin", null)
                fun save() {
                    val edit = prefs.edit().putString("origin", policy.origin).putBoolean("portrait", portrait.isChecked)
                        .putBoolean("roomLight", roomLight.isChecked)
                    if (password.isNotEmpty()) edit.putString("pin", PinHash.create(password))
                    edit.apply(); showDisplay()
                }
                if (previous != null && previous != policy.origin) {
                    AlertDialog.Builder(this).setTitle("更换服务器并清除旧绑定？")
                        .setNegativeButton("取消", null).setPositiveButton("确认") { _, _ ->
                            shell?.destroy(); shell = null
                            WebStorage.getInstance().deleteAllData()
                            CookieManager.getInstance().removeAllCookies { save() }
                        }.show()
                } else save()
            } catch (error: IllegalArgumentException) { message.text = error.message }
            catch (_: java.net.URISyntaxException) { message.text = "服务器地址格式错误" }
        }
        if (!first) {
            button("返回门牌 / 重新加载") { showDisplay() }
            button("启用桌面入口并打开默认桌面设置") {
                packageManager.setComponentEnabledSetting(ComponentName(this, "com.roombeacon.shell.HomeActivity"),
                    PackageManager.COMPONENT_ENABLED_STATE_ENABLED, PackageManager.DONT_KILL_APP)
                startActivity(Intent(Settings.ACTION_HOME_SETTINGS))
            }
            button("启用专用设备锁定（需 Device Owner）") {
                val manager = getSystemService(DevicePolicyManager::class.java)
                if (manager.isDeviceOwnerApp(packageName)) {
                    manager.setLockTaskPackages(ComponentName(this, KioskAdminReceiver::class.java), arrayOf(packageName))
                    prefs.edit().putBoolean("kiosk", true).apply(); showDisplay()
                } else message.setText(R.string.owner_required)
            }
            button("退出专用设备锁定") {
                stopLockTask(); prefs.edit().putBoolean("kiosk", false).apply()
                message.text = "已退出本应用的锁定模式"
            }
            handler.postDelayed(exitMaintenance, 120000)
        }
        setContentView(ScrollView(this).apply { addView(form) })
    }

    override fun onResume() { super.onResume(); resumed = true; immersive(); if (!maintenance) shell?.resume() }
    override fun onPause() {
        resumed = false; shell?.pause(); authDialog?.dismiss()
        super.onPause()
    }
    @Deprecated("Back remains inside the kiosk; maintenance requires authentication")
    override fun onBackPressed() { if (maintenance && prefs.contains("origin")) showDisplay() }
    override fun onDestroy() {
        connectivity.unregisterNetworkCallback(networkCallback)
        handler.removeCallbacksAndMessages(null); shell?.destroy(); super.onDestroy()
    }
}
