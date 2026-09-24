package com.roombeacon.shell

import org.junit.Assert.assertThrows
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Assert.assertFalse
import org.junit.Test

class ManagedPolicyTest {
    private val id = "a".repeat(32)
    private val session = "v6w:$id:2:1900000000:${"b".repeat(64)}"
    @Test fun onlyUsableMacAddressesAreReported() {
        assertTrue(ManagedPolicy.validMac("1c:54:e6:39:3e:f3"))
        assertTrue(ManagedPolicy.validMac("54:01:4A:A5:AA:53"))
        for (value in listOf("02:00:00:00:00:00", "00:00:00:00:00:00", "unknown", "../../secrets", "FF:FF:FF:FF:FF:FF"))
            assertFalse(ManagedPolicy.validMac(value))
    }
    @Test fun namedProfilesUseServerChoiceEvenOnDifferentModelOrFirmware() {
        assertEquals(RoomLight.Profile.BX68, ManagedPolicy.lightProfile("bx68", "special", "custom"))
        assertEquals(RoomLight.Profile.RK3568_R, ManagedPolicy.lightProfile("rk3568_r", "RK3568", "custom"))
        assertEquals(null, ManagedPolicy.lightProfile("generic", "unknown", "unknown"))
        assertEquals(null, ManagedPolicy.lightProfile("auto", "unknown", "unknown"))
        assertEquals(RoomLight.Profile.RK3568_R,
            ManagedPolicy.lightProfile("auto", "rk3568_r", "rk3568-11.0-20230426.150223"))
        assertThrows(IllegalArgumentException::class.java) {
            ManagedPolicy.lightProfile("invalid", "RK3568", "custom")
        }
    }
    @Test fun presentationPathAllowsDayNightAutoAndSupportedLanguages() {
        assertEquals("/?version=v6&managed=1&theme=light&lang=en", ManagedPolicy.displayPath("v6", "light", "en"))
        assertEquals("/?version=v6&managed=1&theme=dark&lang=en", ManagedPolicy.displayPath("v6", "dark", "en"))
        assertThrows(IllegalArgumentException::class.java) { ManagedPolicy.displayPath("v6", "dark&server=evil", "en") }
        assertThrows(IllegalArgumentException::class.java) { ManagedPolicy.displayPath("v6", "auto", "en&server=evil") }
    }
    @Test fun trustedBindingAccepted() {
        for (version in listOf("v4", "v5", "v6")) ManagedPolicy.validate(version, "central", 2, id, session)
    }
    @Test fun wrongBindingOrUnsafeNavigationRejected() {
        for ((version, node, revision, identity, token) in listOf(
            listOf("v6&server=evil", "central", "2", id, session),
            listOf("v6", "other", "2", id, session),
            listOf("v6", "central", "3", id, session),
            listOf("v6", "central", "2", "c".repeat(32), session),
            listOf("v6", "central", "2", id, "$session; Path=/")
        )) assertThrows(IllegalArgumentException::class.java) {
            ManagedPolicy.validate(version, node, revision.toInt(), identity, token)
        }
    }
}
