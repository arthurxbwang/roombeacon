package com.roombeacon.shell

import java.net.URI

class OriginPolicy(origin: String, debug: Boolean = false) {
    val origin: String
    private val base: URI
    init {
        val parsed = URI(origin.trim())
        require(parsed.scheme == "https" || (debug && parsed.scheme == "http" &&
            parsed.host in setOf("127.0.0.1", "localhost"))) { "正式服务器必须使用 HTTPS" }
        require(!parsed.host.isNullOrBlank() && parsed.rawUserInfo == null &&
            parsed.rawQuery == null && parsed.rawFragment == null &&
            parsed.rawPath in listOf("", "/") && parsed.port in -1..65535 && parsed.port != 0) {
            "请输入服务器地址，不含路径、凭证、查询或片段"
        }
        base = parsed
        this.origin = "${parsed.scheme}://${parsed.rawAuthority}".trimEnd('/')
    }
    fun allows(url: String): Boolean = try {
        val candidate = URI(url)
        candidate.rawUserInfo == null && candidate.scheme == base.scheme &&
            candidate.host.equals(base.host, ignoreCase = true) && port(candidate) == port(base)
    } catch (_: Exception) { false }
    private fun port(uri: URI) = if (uri.port >= 0) uri.port else if (uri.scheme == "https") 443 else 80
}
