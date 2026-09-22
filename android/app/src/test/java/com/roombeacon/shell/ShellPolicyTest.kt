package com.roombeacon.shell

import org.junit.Assert.*
import org.junit.Test

class ShellPolicyTest {
    @Test fun originRejectsEscapeAndCredentials() {
        val policy = OriginPolicy("https://rooms.example.com/")
        assertTrue(policy.allows("https://rooms.example.com:443/?version=v3"))
        for (url in listOf("http://rooms.example.com", "https://rooms.example.com.evil.test/",
            "https://rooms.example.com:444/", "https://rooms.example.com@evil.test/",
            "https://user@rooms.example.com/", "file:///etc/passwd", "javascript:alert(1)", "intent://settings")) {
            assertFalse(url, policy.allows(url))
        }
    }
    @Test fun configurationRejectsInsecureAndNonOriginUrls() {
        for (url in listOf("http://10.0.69.167", "https://user:pass@example.com", "https://example.com/path",
            "https://example.com?token=secret", "https://example.com#secret", "https://example.com:0")) {
            assertThrows(Exception::class.java) { OriginPolicy(url) }
        }
        assertThrows(Exception::class.java) { OriginPolicy("http://127.0.0.1:8765") }
        assertThrows(Exception::class.java) { OriginPolicy("http://10.0.69.167", true) }
        assertTrue(OriginPolicy("http://127.0.0.1:8765", true).allows("http://127.0.0.1:8765/"))
    }
    @Test fun retriesAreBoundedAndResettable() {
        val retry = RetryPolicy()
        assertEquals(listOf(2000L, 4000L, 8000L, 16000L, 32000L, 60000L, 60000L),
            (1..7).map { retry.nextDelayMillis() })
        repeat(100) { assertEquals(60000L, retry.nextDelayMillis()) }
        retry.reset(); assertEquals(2000L, retry.nextDelayMillis())
    }
    @Test fun debugLanServerIsExactAndReleaseStillRequiresTls() {
        val policy = OriginPolicy("http://10.0.24.208", true)
        assertTrue(policy.allows("http://10.0.24.208/api/meeting-rooms/usage"))
        for (url in listOf("http://10.0.24.209", "http://10.0.24.208.evil.test",
            "http://10.0.24.208:8080", "http://10.0.24.208@evil.test")) {
            assertThrows(Exception::class.java) { OriginPolicy(url, true) }
            assertFalse(policy.allows(url))
        }
        assertThrows(Exception::class.java) { OriginPolicy("http://10.0.24.208") }
    }
    @Test fun passwordIsSaltedAndWrongPasswordFailsClosed() {
        val first = PinHash.create("test-pass-123")
        assertNotEquals(first, PinHash.create("test-pass-123"))
        assertTrue(PinHash.verify("test-pass-123", first))
        assertFalse(PinHash.verify("wrong-password", first))
        assertFalse(PinHash.verify("test-pass-123", "invalid"))
        assertFalse(PinHash.verify("test-pass-123", "!:!"))
    }
}
