package com.roombeacon.shell

/** Configuration/session errors must survive an unrelated hardware recovery. */
class ApplyFaults {
    enum class Source { CONFIGURATION, SESSION, LIGHT }
    private val faults = mutableMapOf<Source, String>()

    @Synchronized fun set(source: Source, message: String) {
        if (message.isEmpty()) faults.remove(source) else faults[source] = message.take(160)
    }

    @Synchronized fun clear() { faults.clear() }

    @Synchronized fun error(): String = Source.entries.firstNotNullOfOrNull { faults[it] } ?: ""
}
