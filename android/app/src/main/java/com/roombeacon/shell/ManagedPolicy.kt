package com.roombeacon.shell

/** Validate server-driven navigation before writing any cookie or opening a page. */
object ManagedPolicy {
    fun validMac(value: String): Boolean = value.matches(Regex("(?i)[0-9a-f]{2}(:[0-9a-f]{2}){5}")) &&
        value.lowercase() !in setOf("02:00:00:00:00:00", "00:00:00:00:00:00", "ff:ff:ff:ff:ff:ff")
    fun validate(version: String, node: String, revision: Int, identity: String, session: String) {
        require(version in setOf("v4", "v5", "v6")) { "不支持的页面版本" }
        require(node == "central") { "尚未支持该服务节点" }
        require(revision > 0 && identity.matches(Regex("[a-f0-9]{32}"))) { "无效设备配置" }
        require(session.matches(Regex("v6w:$identity:$revision:[0-9]{1,12}:[a-f0-9]{64}"))) { "网页会话与设备配置不匹配" }
    }
}
