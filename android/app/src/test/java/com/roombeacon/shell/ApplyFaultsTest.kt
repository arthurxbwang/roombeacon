package com.roombeacon.shell

import org.junit.Assert.*
import org.junit.Test

class ApplyFaultsTest {
    @Test fun recoveredHardwareClearsOnlyItsOwnFaultAfterSuccessfulReadback() {
        val faults = ApplyFaults()
        faults.set(ApplyFaults.Source.CONFIGURATION, "配置错误")
        faults.set(ApplyFaults.Source.SESSION, "会话错误")
        val values = mutableMapOf(154 to 0, 148 to 0, 147 to 0)
        var readbackBroken = true
        val light = RoomLight({ pin, value -> values[pin] = value },
            { if (readbackBroken) 1 else values.getValue(it) },
            { faults.set(ApplyFaults.Source.LIGHT, it) })
        assertFalse(light.apply("free"))
        assertEquals("配置错误", faults.error())
        faults.set(ApplyFaults.Source.CONFIGURATION, "")
        assertEquals("会话错误", faults.error())
        readbackBroken = false
        assertTrue(light.apply("free"))
        assertEquals("会话错误", faults.error())
        faults.set(ApplyFaults.Source.SESSION, "")
        assertEquals("", faults.error())
        readbackBroken = true
        assertFalse(light.apply("free"))
        assertTrue(faults.error().isNotEmpty())
    }

    @Test fun independentlyFixedSessionCannotEraseAnotherConfigurationOrLightFailure() {
        val faults = ApplyFaults()
        faults.set(ApplyFaults.Source.LIGHT, "灯故障")
        faults.set(ApplyFaults.Source.SESSION, "会话故障")
        faults.set(ApplyFaults.Source.CONFIGURATION, "配置故障")
        faults.set(ApplyFaults.Source.SESSION, "")
        assertEquals("配置故障", faults.error())
        faults.set(ApplyFaults.Source.CONFIGURATION, "")
        assertEquals("灯故障", faults.error())
        faults.clear()
        assertEquals("", faults.error())
    }
}
