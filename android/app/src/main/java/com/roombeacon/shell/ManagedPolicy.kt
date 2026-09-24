package com.roombeacon.shell

/** Validate server-driven navigation before writing any cookie or opening a page. */
object ManagedPolicy {
    fun validMac(value: String): Boolean = value.matches(Regex("(?i)[0-9a-f]{2}(:[0-9a-f]{2}){5}")) &&
        value.lowercase() !in setOf("02:00:00:00:00:00", "00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff")
    fun displayPath(version: String, theme: String, language: String): String {
        require(version in setOf("v4", "v5", "v6")) { "不支持的页面版本" }
        require(theme in setOf("auto", "light", "dark")) { "不支持的昼夜模式" }
        require(language in setOf("zh-CN", "en")) { "不支持的门牌语言" }
        return "/?version=$version&managed=1&theme=$theme&lang=$language"
    }
    // Model matching and overrides belong to the management console.
    fun wiring(red: Int, green: Int, blue: Int, activeLevel: Int): RoomLight.Profile {
        require(activeLevel in 0..1) { "不支持的点亮电平" }
        return RoomLight.Profile(red,green,1-activeLevel,blue)
    }
    fun lightProfile(profile: String, model: String, firmware: String): RoomLight.Profile? = when (profile) {
        "auto" -> RoomLight.profileFor(model, firmware) // Legacy configurations keep auto detection.
        "generic" -> null
        "bx68" -> RoomLight.Profile.BX68
        "rk3568_r" -> RoomLight.Profile.RK3568_R
        else -> throw IllegalArgumentException("未知型号配置")
    }
    fun validate(version: String, node: String, revision: Int, identity: String, session: String) {
        require(version in setOf("v4", "v5", "v6")) { "不支持的页面版本" }
        require(node == "central") { "尚未支持该服务节点" }
        require(revision > 0 && identity.matches(Regex("[a-f0-9]{32}"))) { "无效设备配置" }
        require(session.matches(Regex("v6w:$identity:$revision:[0-9]{1,12}:[a-f0-9]{64}"))) { "网页会话与设备配置不匹配" }
    }
}
