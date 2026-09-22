package com.roombeacon.shell

import org.junit.Assert.assertThrows
import org.junit.Test

class ManagedPolicyTest {
    private val id = "a".repeat(32)
    private val session = "v6w:$id:2:1900000000:${"b".repeat(64)}"
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
