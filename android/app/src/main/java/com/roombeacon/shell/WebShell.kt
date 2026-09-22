package com.roombeacon.shell

import android.annotation.SuppressLint
import android.content.Context
import android.graphics.Bitmap
import android.net.http.SslError
import android.os.Handler
import android.os.Looper
import android.util.Log
import android.webkit.*
import android.widget.FrameLayout
import java.io.ByteArrayInputStream

/** Owns all WebView timers and recovery; business/API failures belong to the H5. */
class WebShell(
    private val context: Context,
    private val container: FrameLayout,
    private val policy: OriginPolicy,
    private val light: RoomLight? = null,
    private val entryPath: String = "/",
    private val status: (String?) -> Unit,
) {
    private val handler = Handler(Looper.getMainLooper())
    private val retries = RetryPolicy()
    private var web: WebView? = null
    private var active = false
    private var failed = false
    private var loading = false
    private var generation = 0
    private val lightHandler = Handler(Looper.getMainLooper())
    private var lightRequest = 0
    private val lightPoll = Runnable { pollLight() }

    private fun stopLight() {
        lightRequest++
        lightHandler.removeCallbacksAndMessages(null)
        light?.apply("unknown")
    }

    private fun pollLight() {
        val view = web ?: return
        if (light == null || !active || failed || loading) return
        if (!policy.allows(view.url ?: "")) { stopLight(); return }
        val request = ++lightRequest
        val deadline = Runnable {
            if (request == lightRequest) {
                lightRequest++
                light.apply("unknown")
                lightHandler.postDelayed(lightPoll, 1000)
            }
        }
        lightHandler.postDelayed(deadline, 3000)
        // Read a versioned main-frame contract; expose no JavaScript-to-native interface.
        view.evaluateJavascript("(() => { const e = document.querySelector('main[data-terminal-protocol=\"1\"]'); return document.visibilityState === 'visible' && e ? e.dataset.terminalState : 'unknown'; })()") { result ->
            if (request != lightRequest || !active || failed || loading) return@evaluateJavascript
            lightHandler.removeCallbacks(deadline)
            val state = when (result) {
                "\"free\"" -> "free"
                "\"busy\"" -> "busy"
                "\"soon\"" -> "soon"
                else -> "unknown"
            }
            light.apply(state)
            lightHandler.postDelayed(lightPoll, 1000)
        }
    }
    private val timeout = Runnable { fail("页面加载超时") }
    private val recovery = Runnable { load() }
    private val watchdog = Runnable { fail("页面无响应", rebuild = true) }
    private val heartbeat = object : Runnable {
        override fun run() {
            val view = web ?: return
            if (!active || loading || failed) return
            val current = generation
            handler.postDelayed(watchdog, 20000)
            view.evaluateJavascript("document.readyState === 'complete' && !!document.getElementById('app') && document.getElementById('app').children.length > 0") { result ->
                if (!active || current != generation) return@evaluateJavascript
                handler.removeCallbacks(watchdog)
                if (result == "true") {
                    retries.reset()
                    handler.postDelayed(this, 15000)
                } else fail("页面尚未就绪")
            }
        }
    }

    @SuppressLint("SetJavaScriptEnabled")
    private fun create() {
        val view = WebView(context)
        web = view
        view.setBackgroundColor(0xff0b0f19.toInt())
        view.settings.apply {
            javaScriptEnabled = true
            domStorageEnabled = true
            allowFileAccess = false
            allowContentAccess = false
            mixedContentMode = WebSettings.MIXED_CONTENT_NEVER_ALLOW
            javaScriptCanOpenWindowsAutomatically = false
            mediaPlaybackRequiresUserGesture = true
            cacheMode = WebSettings.LOAD_DEFAULT
            userAgentString += " RoomBeacon/${BuildConfig.VERSION_NAME}"
        }
        CookieManager.getInstance().setAcceptThirdPartyCookies(view, false)
        view.webViewClient = object : WebViewClient() {
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean =
                !policy.allows(request.url.toString())

            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val url = request.url.toString()
                if (policy.allows(url) || (!request.isForMainFrame &&
                        (url.startsWith("data:") || url.startsWith("blob:${policy.origin}/")))) return null
                return WebResourceResponse("text/plain", "utf-8", 403, "Blocked", emptyMap(),
                    ByteArrayInputStream(ByteArray(0)))
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                // Some WebView builds deliver HTTP errors before onPageStarted.
                // Only an explicit retry may clear that failure, never a late callback.
                if (!active || failed) return
                if (!policy.allows(url)) { view.stopLoading(); fail("已拦截非授权页面"); return }
                generation++
                stopLight()
                loading = true
                handler.removeCallbacksAndMessages(null)
                status("正在连接门牌服务…")
                handler.postDelayed(timeout, 30000)
            }

            override fun onPageFinished(view: WebView, url: String) {
                if (!active || failed || !policy.allows(url)) return
                handler.removeCallbacks(timeout)
                loading = false
                Log.i("RoomBeacon", "page_ready")
                status(null)
                stopLight()
                lightHandler.post(lightPoll)
                handler.removeCallbacks(heartbeat)
                handler.postDelayed(heartbeat, 5000)
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame) fail("连接失败（${error.errorCode}）")
            }

            override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: WebResourceResponse) {
                if (request.isForMainFrame) fail("页面服务异常（${response.statusCode}）")
            }

            override fun onReceivedSslError(view: WebView, sslHandler: SslErrorHandler, error: SslError) {
                sslHandler.cancel()
                fail("证书验证失败，请检查服务器证书与设备时间")
            }

            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                destroyView()
                fail("显示进程已退出，正在恢复")
                return true
            }
        }
        view.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) { request.deny() }
        }
        container.addView(view, FrameLayout.LayoutParams(-1, -1))
    }

    private fun fail(message: String, rebuild: Boolean = false) {
        if (!active) return
        Log.w("RoomBeacon", message)
        generation++
        failed = true
        stopLight()
        loading = false
        handler.removeCallbacksAndMessages(null)
        web?.stopLoading()
        if (rebuild) destroyView()
        val delay = retries.nextDelayMillis()
        status("$message\n当前会议状态不可确认 · ${delay / 1000} 秒后重试")
        handler.postDelayed(recovery, delay)
    }

    fun resume() {
        active = true
        web?.onResume()
        load()
    }

    fun load() {
        if (!active) return
        stopLight()
        handler.removeCallbacksAndMessages(null)
        if (web == null) {
            try { create() }
            catch (error: RuntimeException) {
                Log.e("RoomBeacon", "WebView init failed: ${error.javaClass.simpleName}")
                destroyView()
                fail("WebView 无法启动，请检查系统组件")
                return
            }
        }
        failed = false
        loading = true
        status("正在连接门牌服务…")
        handler.postDelayed(timeout, 30000)
        web?.loadUrl("${policy.origin}$entryPath")
    }

    fun networkAvailable() { if (active && failed) load() }

    fun pause() {
        active = false
        stopLight()
        generation++
        handler.removeCallbacksAndMessages(null)
        web?.stopLoading()
        web?.onPause()
    }

    private fun destroyView() {
        generation++
        web?.let { container.removeView(it); it.destroy() }
        web = null
    }

    fun destroy() { pause(); destroyView() }
}
