package com.roombeacon.shell

import org.junit.Assert.*
import org.junit.Test

class RoomLightTest {
    @org.junit.Test fun customWiringRejectsUnsupportedPinsAndPolarity() {
        for (values in listOf(listOf(116,148,147,0),listOf(148,148,147,0),listOf(148,154,147,2))) {
            try { ManagedPolicy.wiring(values[0],values[1],values[2],values[3]); org.junit.Assert.fail("invalid wiring accepted") }
            catch (_: IllegalArgumentException) { }
        }
    }

    @org.junit.Test fun customWiringUsesSelectedChannelsAndOffLevel() {
        val values = mutableMapOf(147 to 1,148 to 1,154 to 1)
        val light = RoomLight({pin,value->values[pin]=value},{pin->values.getValue(pin)},
            {org.junit.Assert.fail(it)},ManagedPolicy.wiring(147,148,154,0))
        light.apply("busy")
        org.junit.Assert.assertEquals(mapOf(147 to 0,148 to 1,154 to 1),values)
        light.apply("unknown")
        org.junit.Assert.assertTrue(values.values.all { it==1 })
    }
    private fun bx68() = requireNotNull(RoomLight.profileFor(
        "RK3568", "RK3568_BX68_Android 11_64-20260331.094925_ZX-keys",
    ))

    @Test fun forcedTemplateUsesSelectedWiringInsteadOfDetectedModel() {
        val profile = requireNotNull(ManagedPolicy.lightProfile("bx68", "rk3568_r", "rk3568-11.0-20230426.150223"))
        val values = mutableMapOf(154 to 0, 148 to 0, 147 to 0)
        val light = RoomLight({ p, v -> values[p] = v }, { values.getValue(it) }, { fail(it) }, profile)
        light.apply("free")
        assertEquals(listOf(0, 1, 1), values.values.toList())
        light.apply("unknown")
        assertEquals(listOf(1, 1, 1), values.values.toList())
    }

    @Test fun bx68UsesActiveLowGreenRedBlueAndTurnsOffBetweenColors() {
        val values = mutableMapOf(154 to 1, 148 to 1, 147 to 1)
        val writes = mutableListOf<Pair<Int, Int>>()
        val light = RoomLight({ p, v -> values[p] = v; writes.add(p to v) },
            { values.getValue(it) }, { fail(it) }, bx68())
        for ((state, expected) in listOf(
            "busy" to listOf(1, 0, 1), "free" to listOf(0, 1, 1),
            "soon" to listOf(0, 0, 1), "unknown" to listOf(1, 1, 1),
            "disabled" to listOf(1, 1, 1), "../gpio116" to listOf(1, 1, 1),
        )) {
            writes.clear()
            light.apply(state)
            assertEquals(state, expected, values.values.toList())
            if (writes.isNotEmpty()) assertEquals(
                listOf(154 to 1, 148 to 1, 147 to 1), writes.take(3),
            )
        }
        values[147] = 0
        light.apply("unknown")
        assertEquals(listOf(1, 1, 1), values.values.toList())
        assertEquals(setOf(154, 148, 147), values.keys)
    }

    @Test fun bx68WriteFailureAndReadbackMismatchAttemptHighLevelOff() {
        for (readbackFailure in listOf(false, true)) {
            val values = mutableMapOf(154 to 1, 148 to 1, 147 to 1)
            val writes = mutableListOf<Pair<Int, Int>>()
            val errors = mutableListOf<String>()
            var broken = true
            val light = RoomLight({ p, v ->
                writes.add(p to v)
                if (broken && !readbackFailure && p == 148) throw java.io.IOException()
                values[p] = v
            }, { if (broken && readbackFailure) 0 else values.getValue(it) }, { errors.add(it) }, bx68())
            light.apply("busy"); light.apply("free")
            assertEquals(listOf(154 to 1, 148 to 1, 147 to 1), writes.takeLast(3))
            assertEquals(1, errors.size)
            broken = false
            light.apply("free")
            assertEquals(listOf(0, 1, 1), values.values.toList())
            assertEquals(setOf(154, 148, 147), writes.map { it.first }.toSet())
        }
    }

    @Test fun onlyExactSampleFirmwareAllowsLightControl() {
        val old = "rk3568-11.0-20230426.150223"
        val bx68 = "RK3568_BX68_Android 11_64-20260331.094925_ZX-keys"
        assertTrue(RoomLight.supports("rk3568_r", old))
        assertTrue(RoomLight.supports("RK3568", bx68))
        assertFalse(RoomLight.supports("RK3568", old))
        assertFalse(RoomLight.supports("rk3568_r", bx68))
        assertFalse(RoomLight.supports("RK3568", "$bx68-new"))
        assertFalse(RoomLight.supports("unknown", bx68))
        assertFalse(RoomLight.supports("", ""))
    }

    @Test fun colorsUnknownAndExternalChanges() {
        val values = mutableMapOf(154 to 1, 148 to 1, 147 to 1)
        val light = RoomLight({ pin, value -> values[pin] = value }, { values.getValue(it) }, { fail(it) })
        light.apply("busy"); assertEquals(listOf(1, 0, 0), values.values.toList())
        light.apply("free"); assertEquals(listOf(0, 1, 0), values.values.toList())
        values[154] = 1
        light.apply("free"); assertEquals(listOf(0, 1, 0), values.values.toList())
        light.apply("soon"); assertEquals(listOf(1, 1, 0), values.values.toList())
        for (state in listOf("unknown", "disabled", "", "FREE", "../gpio137")) {
            light.apply(state); assertEquals(listOf(0, 0, 0), values.values.toList())
        }
        assertEquals(setOf(154, 148, 147), values.keys)
    }

    @Test fun partialFailureAttemptsEveryOffAndReportsOnceThenRecovers() {
        val values = mutableMapOf(154 to 0, 148 to 0, 147 to 0)
        var broken = true
        val errors = mutableListOf<String>()
        val light = RoomLight({ pin, value ->
            if (pin == 148 && broken) throw java.io.IOException()
            values[pin] = value
        }, { values.getValue(it) }, { errors.add(it) })
        light.apply("soon"); light.apply("free")
        assertEquals(listOf(0, 0, 0), values.values.toList())
        assertEquals(1, errors.size)
        broken = false
        light.apply("free"); assertEquals(listOf(0, 1, 0), values.values.toList())
    }

    @Test fun unsuccessfulReadbackFailsClosed() {
        val writes = mutableListOf<Pair<Int, Int>>()
        val errors = mutableListOf<String>()
        val light = RoomLight({ p, v -> writes.add(p to v) }, { 1 }, { errors.add(it) })
        light.apply("free")
        assertEquals(listOf(154 to 0, 148 to 0, 147 to 0), writes.takeLast(3))
        assertEquals(1, errors.size)
    }
}
