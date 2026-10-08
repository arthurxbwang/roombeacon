package com.roombeacon.shell

/** Monotonic, generation-bound runtime evidence, separate from configuration acknowledgements. */
class RuntimeHealth(private val elapsedMillis: () -> Long = { System.nanoTime() / 1_000_000 }) {
    data class Probe(val generation: Long, val requestedAtMillis: Long)
    data class Snapshot(
        val pageState: String, val pageError: String, val pageAgeSeconds: Int?,
        val pageRelease: String, val terminalState: String, val webview: String, val lightState: String,
    ) {
        fun fields(): Map<String, Any?> = mapOf(
            "protocol" to 1, "page_state" to pageState, "page_error" to pageError,
            "page_age_seconds" to pageAgeSeconds, "page_release" to pageRelease,
            "terminal_state" to terminalState, "webview" to webview, "light_state" to lightState,
        )
    }

    private var generation = 0L
    private var state = "waiting"
    private var error = ""
    private var sampledAt: Long? = null
    private var release = ""
    private var terminal = "unknown"
    private var webview = ""
    private var light = "disabled"
    private val safeVersion = Regex("[A-Za-z0-9._-]{1,100}")

    @Synchronized fun waiting() {
        generation++; state = "waiting"; error = ""; sampledAt = null; release = ""; terminal = "unknown"
    }

    @Synchronized fun loading(): Probe {
        generation++; state = "loading"; error = ""; sampledAt = null; release = ""; terminal = "unknown"
        return probe()
    }

    @Synchronized fun currentGeneration(): Long = generation

    @Synchronized fun probe(): Probe = Probe(generation, elapsedMillis())

    @Synchronized fun accepts(current: Long): Boolean = current == generation && state in setOf("loading", "ready")

    @Synchronized fun fresh(probe: Probe): Boolean = accepts(probe.generation) &&
        elapsedMillis() - probe.requestedAtMillis in 0..20_000

    /** A complete WebView navigation alone is not evidence of a responsive H5. */
    @Synchronized fun sample(probe: Probe, ready: Boolean, observedTerminal: String, observedRelease: String): Boolean {
        if (!fresh(probe) || !ready) return false
        // Request time is conservative: a delayed callback cannot reset the sample age to zero.
        state = "ready"; error = ""; sampledAt = probe.requestedAtMillis
        terminal = observedTerminal.takeIf { it in setOf("free", "busy", "soon") } ?: "unknown"
        release = observedRelease.takeIf { safeVersion.matches(it) } ?: ""
        return true
    }

    @Synchronized fun terminalUnknown() { terminal = "unknown" }

    @Synchronized fun fail(reason: String) {
        require(reason in setOf("network", "http", "tls", "renderer", "timeout", "unresponsive", "initialization", "blocked"))
        generation++; state = "failed"; error = reason; terminal = "unknown"
    }

    @Synchronized fun pause() { generation++; state = "paused"; error = ""; terminal = "unknown" }

    @Synchronized fun light(state: String) {
        require(state in setOf("disabled", "unknown", "ok", "failed"))
        light = state
    }

    @Synchronized fun webview(version: String) { webview = version.takeIf { safeVersion.matches(it) } ?: "" }

    @Synchronized fun snapshot(): Snapshot {
        val ageMillis = sampledAt?.let { (elapsedMillis() - it).coerceAtLeast(0) }
        // Polling is every 15 s and the JS watchdog is 20 s. Expired evidence never reports healthy/free.
        val stale = state == "ready" && (ageMillis == null || ageMillis > 35_000)
        return Snapshot(if (stale) "failed" else state, if (stale) "unresponsive" else error,
            ageMillis?.let { (it / 1000).coerceAtMost(86_400).toInt() }, release,
            if (stale) "unknown" else terminal, webview, light)
    }
}
