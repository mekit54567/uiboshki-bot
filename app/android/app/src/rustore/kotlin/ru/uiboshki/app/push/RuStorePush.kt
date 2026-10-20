package ru.uiboshki.app.push

import android.content.Context
import ru.rustore.sdk.core.feature.model.FeatureAvailabilityResult
import ru.rustore.sdk.pushclient.RuStorePushClient
import ru.rustore.sdk.pushclient.messaging.exception.RuStorePushClientException
import ru.rustore.sdk.pushclient.messaging.model.RemoteMessage
import ru.rustore.sdk.pushclient.messaging.service.RuStoreMessagingService

/**
 * RuStore Push — для телефонов без сервисов Google. SDK сам запускается по
 * meta-data ru.rustore.sdk.pushclient.project_id (AndroidManifest.xml,
 * значение — RUSTORE_PROJECT_ID при сборке). Свой сервис, а не плагин
 * flutter_rustore_push: плагин отдаёт data-сообщения только в открытое
 * приложение, а нам надо расшифровать и показать и когда оно закрыто.
 * Вызовы SDK — как в плагине RuStore 7.2.0 (FlutterRustorePushClient.kt).
 */
object RuStorePush {
    @Suppress("UNUSED_PARAMETER")
    fun available(ctx: Context, done: (Boolean) -> Unit) {
        try {
            RuStorePushClient.checkPushAvailability()
                .addOnSuccessListener { done(it is FeatureAvailabilityResult.Available) }
                .addOnFailureListener { done(false) }
        } catch (e: Exception) {
            done(false)
        }
    }

    fun token(done: (String?, String?) -> Unit) {
        RuStorePushClient.getToken()
            .addOnSuccessListener { done(it, null) }
            .addOnFailureListener { done(null, it.message ?: "RuStore не выдал токен") }
    }

    fun delete() {
        try {
            RuStorePushClient.deleteToken()
        } catch (_: Exception) {
        }
    }
}

class RuStoreService : RuStoreMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        PushNotify.handle(this, message.data)
    }

    override fun onNewToken(token: String) {
        PushBridge.newToken("rustore", token)
    }

    override fun onError(errors: List<RuStorePushClientException>) {}
}
