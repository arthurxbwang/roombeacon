package com.roombeacon.shell

class RetryPolicy {
    var failures = 0
        private set
    fun nextDelayMillis(): Long {
        failures = (failures + 1).coerceAtMost(6)
        return (2000L shl (failures - 1)).coerceAtMost(60000L)
    }
    fun reset() { failures = 0 }
}
