package com.roombeacon.shell

import org.junit.Assert.assertThrows
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
