package com.roombeacon.shell

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import java.security.SecureRandom
import java.util.UUID
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/** Management credentials never enter WebView, URLs, logs, or backups. */
class DeviceIdentity(context: Context) {
    private val prefs = context.getSharedPreferences("managed_identity", Context.MODE_PRIVATE)
    private val alias = "roombeacon-device-v6"
    private fun key(): SecretKey {
        val store = KeyStore.getInstance("AndroidKeyStore").apply { load(null) }
        if (store.containsAlias(alias)) return store.getKey(alias, null) as SecretKey
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, "AndroidKeyStore")
        generator.init(KeyGenParameterSpec.Builder(alias, KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT)
            .setBlockModes(KeyProperties.BLOCK_MODE_GCM).setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE).build())
        return generator.generateKey()
    }
    val token: String by lazy {
        val encrypted = prefs.getString("credential", null)
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        if (encrypted != null) {
            val parts = encrypted.split(":")
            require(parts.size == 2) { "设备身份格式错误" }
            cipher.init(Cipher.DECRYPT_MODE, key(), GCMParameterSpec(128, Base64.decode(parts[0], Base64.NO_WRAP)))
            String(cipher.doFinal(Base64.decode(parts[1], Base64.NO_WRAP)), Charsets.UTF_8)
        } else {
            val random = ByteArray(32).also { SecureRandom().nextBytes(it) }
            val secret = Base64.encodeToString(random, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING)
            val value = "v6d:${UUID.randomUUID().toString().replace("-", "")}:$secret"
            cipher.init(Cipher.ENCRYPT_MODE, key())
            val stored = Base64.encodeToString(cipher.iv, Base64.NO_WRAP) + ":" +
                Base64.encodeToString(cipher.doFinal(value.toByteArray()), Base64.NO_WRAP)
            check(prefs.edit().putString("credential", stored).commit()) { "设备身份保存失败" }
            value
        }
    }
}
