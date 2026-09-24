package com.roombeacon.shell

import java.io.File

/** Only the three physically tested RGB pins. No relay, shell command or caller-supplied path. */
class RoomLight(
    private val write: (Int, Int) -> Unit,
    private val read: (Int) -> Int,
    private val report: (String) -> Unit,
    private val profile: Profile = Profile.RK3568_R,
) {
    data class Profile(val redPin: Int, val greenPin: Int, val off: Int, val bluePin: Int = 147) {
        init {
            require(setOf(redPin,greenPin,bluePin) == setOf(147,148,154)) { "不支持的 RGB GPIO" }
            require(off in 0..1) { "不支持的点亮电平" }
        }
        companion object {
            val RK3568_R = Profile(154,148,0)
            val BX68 = Profile(148,154,1)
        }
    }
    private var last: List<Int>? = null
    private var errorReported = false

    fun apply(state: String) {
        val enabled = when (state) {
            "busy" -> setOf(profile.redPin)
            "free" -> setOf(profile.greenPin)
            "soon" -> setOf(profile.redPin, profile.greenPin)
            else -> emptySet()
        }
        val values = pins.map { if (it in enabled) 1 - profile.off else profile.off }
        try {
            if (last == values && pins.map(read) == values) return
            // Turn channels off before enabling a new color, avoiding a transient green.
            pins.forEach { write(it, profile.off) }
            pins.zip(values).filter { it.second != profile.off }.forEach { (pin, value) -> write(pin, value) }
            check(pins.map(read) == values) { "readback mismatch" }
            last = values
            errorReported = false
        } catch (error: Exception) {
            last = null
            pins.forEach { pin -> try { write(pin, profile.off) } catch (_: Exception) { /* Report below. */ } }
            if (!errorReported) report("灯控失败，已尝试熄灯：${error.javaClass.simpleName}")
            errorReported = true
        }
    }

    companion object {
        private val pins = listOf(154, 148, 147)

        // Exact firmware matches only; the model alone does not identify the wiring.
        fun profileFor(model: String, display: String): Profile? = when {
            model == "rk3568_r" && display == "rk3568-11.0-20230426.150223" -> Profile.RK3568_R
            model == "RK3568" && display == "RK3568_BX68_Android 11_64-20260331.094925_ZX-keys" -> Profile.BX68
            else -> null
        }

        fun supports(model: String, display: String) = profileFor(model, display) != null

        fun forSample(model: String, display: String, report: (String) -> Unit): RoomLight {
            return forProfile(requireNotNull(profileFor(model, display)) { "Unsupported light wiring" }, report)
        }

        fun forProfile(profile: Profile, report: (String) -> Unit): RoomLight {
            pins.forEach { pin ->
                check(File("/sys/class/gpio/gpio$pin/direction").readText().trim() == "out")
            }
            return RoomLight(
                { pin, value -> File("/sys/class/gpio/gpio$pin/value").writeText("$value\n") },
                { pin -> File("/sys/class/gpio/gpio$pin/value").readText().trim().toInt() }, report, profile,
            )
        }
    }
}
