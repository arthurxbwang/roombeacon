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
import org.json.JSONObject
import org.json.JSONTokener
import java.io.ByteArrayInputStream

/** Owns all WebView timers and recovery; business/API failures belong to the H5. */
class WebShell(
    private val context: Context,
    private val container: FrameLayout,
    private val policy: OriginPolicy,
    private val light: RoomLight? = null,
    private val entryPath: String = "/",
    private val runtime: RuntimeHealth,
    private val status: (String?) -> Unit,
) {
    private val handler = Handler(Looper.getMainLooper())
    private val retries = RetryPolicy()
    private var web: WebView? = null
    private var active = false
    private var failed = false
    private var loading = false
    private var readyReported = false
    private var probeRequest = 0L
    private val timeout = Runnable { fail("页面加载超时", "timeout") }
    private val recovery = Runnable { load() }
    private val heartbeat = Runnable { probe() }

    fun reportViewport(report: (String) -> Unit) {
        val view = web ?: return
        val current = runtime.currentGeneration()
        if (!active || !runtime.accepts(current) || !policy.allows(view.url ?: "")) return
        view.evaluateJavascript("JSON.stringify({viewport_width:innerWidth,viewport_height:innerHeight,dpr:devicePixelRatio})") { result ->
            if (view !== web || !active || !runtime.accepts(current) || !policy.allows(view.url ?: "")) return@evaluateJavascript
            try {
                val value = JSONTokener(result).nextValue()
                if (value is String) report(value)
            } catch (_: Exception) { Log.w("RoomBeacon", "viewport_response_invalid") }
        }
    }

    private fun applyLight(state: String) {
        val driver = light ?: return
        runtime.light(if (driver.apply(state)) "ok" else "failed")
    }

    private fun stopLight() { probeRequest++; runtime.terminalUnknown(); applyLight("unknown") }

    private fun validProbe(view: WebView, current: RuntimeHealth.Probe, request: Long): Boolean =
        view === web && active && !failed && !loading && request == probeRequest &&
            runtime.accepts(current.generation) && policy.allows(view.url ?: "")

    private fun probe() {
        val view = web ?: return
        if (!active || loading || failed) return
        if (!policy.allows(view.url ?: "")) { fail("已拦截非授权页面", "blocked"); return }
        val current = runtime.probe()
        val request = ++probeRequest
        val watchdog = Runnable {
            if (validProbe(view, current, request)) fail("页面无响应", "unresponsive", rebuild = true)
        }
        val lightDeadline = Runnable {
            if (validProbe(view, current, request)) { runtime.terminalUnknown(); applyLight("unknown") }
        }
        handler.postDelayed(watchdog, 20000)
        handler.postDelayed(lightDeadline, 3000)
        // Read a bounded main-document contract. No JS bridge, URL, cookies, business text, or web requests.
        view.evaluateJavascript("""
            (() => {
              const app = document.getElementById('app');
              const terminal = document.querySelector('main[data-terminal-protocol="1"]');
              const release = document.querySelector('meta[name="roombeacon-release"]');
              return JSON.stringify({
                ready: document.readyState === 'complete' && document.visibilityState === 'visible' && !!app && app.children.length > 0 && !!terminal,
                terminal_state: terminal ? terminal.dataset.terminalState : 'unknown',
                page_release: release ? release.content : ''
              });
            })()
        """.trimIndent()) { result ->
            if (!validProbe(view, current, request)) return@evaluateJavascript
            handler.removeCallbacks(watchdog); handler.removeCallbacks(lightDeadline)
            if (!runtime.fresh(current)) {
                fail("页面无响应", "unresponsive", rebuild = true)
                return@evaluateJavascript
            }
            val sample = try {
                val value = JSONTokener(result).nextValue()
                if (value is String && value.length <= 512) JSONObject(value) else null
            } catch (_: Exception) { null }
            if (sample == null || !runtime.sample(current, sample.optBoolean("ready"),
                    sample.optString("terminal_state"), sample.optString("page_release"))) {
                fail("页面尚未就绪", "initialization")
                return@evaluateJavascript
            }
            retries.reset()
            applyLight(runtime.snapshot().terminalState)
            if (!readyReported) { readyReported = true; Log.i("RoomBeacon", "page_ready"); status(null) }
            handler.postDelayed(heartbeat, if (light == null) 15000 else 1000)
        }
    }

    private fun currentView(view: WebView, url: String? = null): Boolean =
        view === web && active && !failed && (url == null || view.url == null || view.url == url)

    @SuppressLint("SetJavaScriptEnabled")
    private fun create() {
        val view = WebView(context)
        web = view
        runtime.webview(WebView.getCurrentWebViewPackage()?.versionName ?: "")
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
            override fun shouldOverrideUrlLoading(view: WebView, request: WebResourceRequest): Boolean {
                val blocked = !policy.allows(request.url.toString())
                if (blocked && request.isForMainFrame && currentView(view)) fail("已拦截非授权页面", "blocked")
                return blocked
            }

            override fun shouldInterceptRequest(view: WebView, request: WebResourceRequest): WebResourceResponse? {
                val url = request.url.toString()
                if (policy.allows(url) || (!request.isForMainFrame &&
                        (url.startsWith("data:") || url.startsWith("blob:${policy.origin}/")))) return null
                return WebResourceResponse("text/plain", "utf-8", 403, "Blocked", emptyMap(),
                    ByteArrayInputStream(ByteArray(0)))
            }

            override fun onPageStarted(view: WebView, url: String, favicon: Bitmap?) {
                // An explicit retry alone clears failure; a late callback cannot claim recovery.
                if (!currentView(view)) return
                if (!policy.allows(url)) { view.stopLoading(); fail("已拦截非授权页面", "blocked"); return }
                stopLight(); runtime.loading(); loading = true; readyReported = false
                handler.removeCallbacksAndMessages(null)
                status("正在连接门牌服务…")
                handler.postDelayed(timeout, 30000)
            }

            override fun onPageFinished(view: WebView, url: String) {
                if (!currentView(view, url) || !loading || !policy.allows(url)) return
                handler.removeCallbacks(timeout)
                loading = false
                handler.removeCallbacks(heartbeat)
                handler.post(heartbeat)
            }

            override fun onReceivedError(view: WebView, request: WebResourceRequest, error: WebResourceError) {
                if (request.isForMainFrame && currentView(view, request.url.toString()))
                    fail("连接失败（${error.errorCode}）", "network")
            }

            override fun onReceivedHttpError(view: WebView, request: WebResourceRequest, response: WebResourceResponse) {
                if (request.isForMainFrame && currentView(view, request.url.toString()))
                    fail("页面服务异常（${response.statusCode}）", "http")
            }

            override fun onReceivedSslError(view: WebView, sslHandler: SslErrorHandler, error: SslError) {
                sslHandler.cancel()
                if (currentView(view)) fail("证书验证失败，请检查服务器证书与设备时间", "tls")
            }

            override fun onRenderProcessGone(view: WebView, detail: RenderProcessGoneDetail): Boolean {
                if (view === web) { destroyView(); fail("显示进程已退出，正在恢复", "renderer") }
                return true
            }
        }
        view.webChromeClient = object : WebChromeClient() {
            override fun onPermissionRequest(request: PermissionRequest) { request.deny() }
        }
        container.addView(view, FrameLayout.LayoutParams(-1, -1))
    }

    private fun fail(message: String, reason: String, rebuild: Boolean = false) {
        if (!active || failed) return
        Log.w("RoomBeacon", message)
        failed = true; runtime.fail(reason); stopLight(); loading = false; readyReported = false
        handler.removeCallbacksAndMessages(null)
        web?.stopLoading()
        if (rebuild) destroyView()
        val delay = retries.nextDelayMillis()
        status("$message\n当前会议状态不可确认 · ${delay / 1000} 秒后重试")
        handler.postDelayed(recovery, delay)
    }

    fun resume() {
        if (active) return
        active = true
        web?.onResume()
        load()
    }

    fun load() {
        if (!active) return
        stopLight(); runtime.loading(); failed = false; loading = true; readyReported = false
        handler.removeCallbacksAndMessages(null)
        if (web == null) {
            try { create() }
            catch (error: RuntimeException) {
                Log.e("RoomBeacon", "WebView init failed: ${error.javaClass.simpleName}")
                destroyView()
                fail("WebView 无法启动，请检查系统组件", "initialization")
                return
            }
        }
        status("正在连接门牌服务…")
        handler.postDelayed(timeout, 30000)
        web?.loadUrl("${policy.origin}$entryPath")
    }

    fun networkAvailable() { if (active && failed) load() }

    fun pause() {
        active = false; stopLight(); runtime.pause(); readyReported = false
        handler.removeCallbacksAndMessages(null)
        web?.stopLoading()
        web?.onPause()
    }

    private fun destroyView() {
        probeRequest++
        web?.let { container.removeView(it); it.destroy() }
        web = null
    }

    fun destroy() { pause(); destroyView() }
}
