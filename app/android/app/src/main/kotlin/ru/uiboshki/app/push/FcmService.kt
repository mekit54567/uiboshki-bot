package ru.uiboshki.app.push

import com.google.firebase.messaging.FirebaseMessagingService
import com.google.firebase.messaging.RemoteMessage

/**
 * Пуши через Google (FCM). Сервер шлёт только data-сообщение {v, e} —
 * без notification, поэтому Android сам ничего не показывает: расшифровка и
 * уведомление — PushNotify (и когда приложение закрыто).
 */
class FcmService : FirebaseMessagingService() {
    override fun onMessageReceived(message: RemoteMessage) {
        PushNotify.handle(this, message.data)
    }

    override fun onNewToken(token: String) {
        PushBridge.newToken("fcm", token)
    }
}
