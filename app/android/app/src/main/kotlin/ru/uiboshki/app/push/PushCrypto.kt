package ru.uiboshki.app.push

import javax.crypto.Cipher
import javax.crypto.spec.GCMParameterSpec
import javax.crypto.spec.SecretKeySpec

/**
 * Расшифровка пуша (сервер — app_push.py): поле `e` = nonce (12 байт) |
 * шифротекст | тег GCM (16 байт), ключ — 32 байта AES-256 этого телефона.
 * Без android.* — проверяется обычным JVM-тестом (src/test).
 */
object PushCrypto {
    fun open(raw: ByteArray, key: ByteArray): ByteArray {
        require(key.size == 32) { "ключ — 32 байта" }
        require(raw.size > 12 + 16) { "слишком коротко" }
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.DECRYPT_MODE, SecretKeySpec(key, "AES"), GCMParameterSpec(128, raw, 0, 12))
        return cipher.doFinal(raw, 12, raw.size - 12)
    }
}
