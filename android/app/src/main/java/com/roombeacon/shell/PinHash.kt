package com.roombeacon.shell

import java.security.MessageDigest
import java.security.SecureRandom
import java.util.Base64
import javax.crypto.SecretKeyFactory
import javax.crypto.spec.PBEKeySpec

object PinHash {
    fun create(pin: String): String {
        require(pin.length in 6..64)
        val salt = ByteArray(16).also { SecureRandom().nextBytes(it) }
        return Base64.getEncoder().encodeToString(salt) + ":" +
            Base64.getEncoder().encodeToString(derive(pin, salt))
    }
    fun verify(pin: String, stored: String): Boolean = try {
        val parts = stored.split(':')
        parts.size == 2 && pin.length in 6..64 && MessageDigest.isEqual(
            derive(pin, Base64.getDecoder().decode(parts[0])), Base64.getDecoder().decode(parts[1]))
    } catch (_: IllegalArgumentException) { false }
    private fun derive(pin: String, salt: ByteArray): ByteArray {
        val spec = PBEKeySpec(pin.toCharArray(), salt, 120000, 256)
        return try { SecretKeyFactory.getInstance("PBKDF2WithHmacSHA256").generateSecret(spec).encoded }
        finally { spec.clearPassword() }
    }
}
