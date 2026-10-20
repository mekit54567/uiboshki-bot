package ru.uiboshki.app.push

import java.util.Base64
import org.junit.Assert.assertEquals
import org.junit.Assert.assertThrows
import org.junit.Test

/** Пример сделан сервером (tests/test_app_push.py, SAMPLE) — формат должен совпадать. */
class PushCryptoTest {
    private val key = "AAECAwQFBgcICQoLDA0ODxAREhMUFRYXGBkaGxwdHh8="
    private val sample = "AAECAwQFBgcICQoLPCCicrGJpzm3Y0cqYVOo01JWV4rQq+CsiLZlVa1LLJBjf8qFjfswSNN0yjwIV53oWXlRvXoGHwqHR5fImzJ3zhK8" +
        "UloDQfbczOR61T833l8YWn2yxrPuuEAsFR390pWvv5k7xJ5jvHX6fUeQZFdVHt1FWImPoFbpIpF1sKuQD+QrU20Q6Omf1PvrKtA="

    @Test
    fun opensServerSample() {
        val plain = PushCrypto.open(Base64.getDecoder().decode(sample), Base64.getDecoder().decode(key))
        assertEquals(
            "{\"title\":\"Скоро пара\",\"body\":\"Через 10 минут — Анализ данных\",\"tab\":\"today\",\"tag\":\"lesson\"}",
            String(plain, Charsets.UTF_8),
        )
    }

    @Test
    fun wrongKeyFails() {
        val other = ByteArray(32) { 7 }
        assertThrows(Exception::class.java) { PushCrypto.open(Base64.getDecoder().decode(sample), other) }
    }
}
