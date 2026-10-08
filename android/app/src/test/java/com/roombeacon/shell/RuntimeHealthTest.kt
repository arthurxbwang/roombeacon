package com.roombeacon.shell

import org.junit.Assert.*
import org.junit.Test

class RuntimeHealthTest {
    @Test fun navigationCompletionCannotClaimReadyWithoutCurrentJavascriptEvidence() {
        val runtime = RuntimeHealth { 1000L }
        val current = runtime.loading()
        assertEquals("loading", runtime.snapshot().pageState)
        assertNull(runtime.snapshot().pageAgeSeconds)
        assertFalse(runtime.sample(current, false, "free", "858038c"))
        assertEquals("loading", runtime.snapshot().pageState)
        assertEquals("unknown", runtime.snapshot().terminalState)
        assertTrue(runtime.sample(current, true, "busy", "858038c"))
        assertEquals("ready", runtime.snapshot().pageState)
        assertEquals(0, runtime.snapshot().pageAgeSeconds)
        assertEquals("busy", runtime.snapshot().terminalState)
    }

    @Test fun failureRequiresNewNavigationAndIgnoresLateSuccess() {
        val runtime = RuntimeHealth { 1000L }
        val failedRequest = runtime.loading()
        assertTrue(runtime.sample(failedRequest, true, "free", "first"))
        runtime.fail("network")
        assertFalse(runtime.sample(failedRequest, true, "free", "late"))
        assertEquals("failed", runtime.snapshot().pageState)
        assertEquals("network", runtime.snapshot().pageError)
        assertEquals("unknown", runtime.snapshot().terminalState)
        val retry = runtime.loading()
        assertFalse(runtime.sample(failedRequest, true, "free", "late"))
        assertTrue(runtime.sample(retry, true, "soon", "second"))
        assertEquals("ready", runtime.snapshot().pageState)
        assertEquals("", runtime.snapshot().pageError)
        assertEquals("second", runtime.snapshot().pageRelease)
    }

    @Test fun pausedDestroyedOrUnboundPagesCannotBeRevivedByOldCallbacks() {
        val runtime = RuntimeHealth { 1000L }
        val beforePause = runtime.loading()
        runtime.sample(beforePause, true, "free", "first")
        runtime.pause()
        assertFalse(runtime.sample(beforePause, true, "free", "late"))
        assertEquals("paused", runtime.snapshot().pageState)
        assertEquals("unknown", runtime.snapshot().terminalState)
        val resumed = runtime.loading()
        assertNull(runtime.snapshot().pageAgeSeconds)
        assertFalse(runtime.sample(beforePause, true, "free", "late"))
        assertTrue(runtime.sample(resumed, true, "busy", "second"))
        runtime.waiting()
        assertFalse(runtime.sample(resumed, true, "free", "late"))
        assertEquals("waiting", runtime.snapshot().pageState)
        assertEquals("", runtime.snapshot().pageRelease)
        assertNull(runtime.snapshot().pageAgeSeconds)
    }

    @Test fun monotonicSampleAgeExpiresAndIsBoundedWithoutWallClockDependence() {
        var elapsed = 123_000L
        val runtime = RuntimeHealth { elapsed }
        val current = runtime.loading()
        runtime.sample(current, true, "free", "858038c")
        elapsed += 35_000
        assertEquals("ready", runtime.snapshot().pageState)
        assertEquals(35, runtime.snapshot().pageAgeSeconds)
        elapsed++
        assertEquals("failed", runtime.snapshot().pageState)
        assertEquals("unresponsive", runtime.snapshot().pageError)
        assertEquals("unknown", runtime.snapshot().terminalState)
        elapsed += 200_000_000L
        assertEquals(86_400, runtime.snapshot().pageAgeSeconds)
        assertTrue(runtime.sample(runtime.probe(), true, "busy", "new"))
        assertEquals(0, runtime.snapshot().pageAgeSeconds)
        assertEquals("ready", runtime.snapshot().pageState)
    }

    @Test fun stalledCallbackCannotTurnAnOldJavascriptResultIntoFreshHealth() {
        var elapsed = 1000L
        val runtime = RuntimeHealth { elapsed }
        val delayed = runtime.loading()
        elapsed += 20_001
        assertFalse(runtime.fresh(delayed))
        assertFalse(runtime.sample(delayed, true, "free", "old"))
        assertEquals("loading", runtime.snapshot().pageState)
        assertNull(runtime.snapshot().pageAgeSeconds)
        assertTrue(runtime.sample(runtime.probe(), true, "unknown", "new"))
        assertEquals("ready", runtime.snapshot().pageState)
    }

    @Test fun aResponsiveButDelayedProbeRetainsItsConservativeMonotonicAge() {
        var elapsed = 1000L
        val runtime = RuntimeHealth { elapsed }
        val pending = runtime.loading()
        elapsed += 12_000
        assertTrue(runtime.sample(pending, true, "unknown", "release"))
        assertEquals(12, runtime.snapshot().pageAgeSeconds)
        elapsed += 24_000
        assertEquals("failed", runtime.snapshot().pageState)
        assertEquals("unresponsive", runtime.snapshot().pageError)
    }

    @Test fun unknownBusinessDataDoesNotBecomeAPageFailureOrSuccessfulSignup() {
        val runtime = RuntimeHealth { 1000L }
        assertTrue(runtime.sample(runtime.loading(), true, "unknown", "release-0.7.1"))
        assertEquals("ready", runtime.snapshot().pageState)
        assertEquals("unknown", runtime.snapshot().terminalState)
        assertEquals("", runtime.snapshot().pageError)
        runtime.terminalUnknown()
        assertEquals("unknown", runtime.snapshot().terminalState)
    }

    @Test fun metadataHasOnlyBoundedContractValues() {
        val runtime = RuntimeHealth { 1000L }
        val current = runtime.loading()
        runtime.webview("120.0.6099.144")
        runtime.sample(current, true, "free", "good_0.7.1-dev")
        assertEquals("120.0.6099.144", runtime.snapshot().webview)
        assertEquals("good_0.7.1-dev", runtime.snapshot().pageRelease)
        for (unsafe in listOf("https://server?token=secret", "secret\nheader", "x".repeat(101))) {
            runtime.webview(unsafe)
            runtime.sample(current, true, unsafe, unsafe)
            assertEquals("", runtime.snapshot().webview)
            assertEquals("", runtime.snapshot().pageRelease)
            assertEquals("unknown", runtime.snapshot().terminalState)
        }
        assertEquals(setOf("protocol", "page_state", "page_error", "page_age_seconds", "page_release",
            "terminal_state", "webview", "light_state"), runtime.snapshot().fields().keys)
        assertThrows(IllegalArgumentException::class.java) { runtime.fail("business text") }
    }

    @Test fun pageRecoveryDoesNotClearAFailedLightOrEnableADisabledOne() {
        val runtime = RuntimeHealth { 1000L }
        runtime.light("failed")
        runtime.fail("http")
        runtime.sample(runtime.loading(), true, "unknown", "release")
        assertEquals("ready", runtime.snapshot().pageState)
        assertEquals("failed", runtime.snapshot().lightState)
        runtime.light("disabled")
        runtime.pause()
        assertEquals("disabled", runtime.snapshot().lightState)
        assertThrows(IllegalArgumentException::class.java) { runtime.light("pretend") }
    }
}
