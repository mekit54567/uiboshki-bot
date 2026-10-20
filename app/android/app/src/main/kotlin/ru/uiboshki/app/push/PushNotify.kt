package ru.uiboshki.app.push

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import android.util.Base64
import android.util.Log
import org.json.JSONObject
import ru.uiboshki.app.MainActivity
import ru.uiboshki.app.R

/**
 * Пуш пришёл (FCM или RuStore, data-сообщение {v, e}) — расшифровать своим
 * ключом и показать уведомление. Нажатие открывает приложение на вкладке из
 * пуша (как `?tab=` у веб-пуша). Ключ — в личном хранилище приложения
 * (setKey из Dart, app_push.dart); его нет — пуш молча пропускаем.
 */
object PushNotify {
    const val CHANNEL = "kapibara"
    const val EXTRA_TAB = "uib_push_tab"
    private const val PREFS = "kapibara_push"
    private const val TAG = "KapibaraPush"

    private fun prefs(ctx: Context) = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

    fun key(ctx: Context): String? = prefs(ctx).getString("key", null)

    fun setKey(ctx: Context, key: String?) {
        prefs(ctx).edit().apply { if (key == null) remove("key") else putString("key", key) }.apply()
    }

    fun handle(ctx: Context, data: Map<String, String>) {
        if (data["v"] != "1") return
        val e = data["e"] ?: return
        val key = key(ctx) ?: return
        val json = try {
            JSONObject(String(PushCrypto.open(Base64.decode(e, Base64.DEFAULT), Base64.decode(key, Base64.DEFAULT)), Charsets.UTF_8))
        } catch (ex: Exception) {
            Log.i(TAG, "не расшифровался: ${ex.javaClass.simpleName}") // старый ключ — ждём новую регистрацию
            return
        }
        show(ctx, json.optString("title", "Капибара"), json.optString("body"), json.optString("tab"), json.optString("tag"))
    }

    private fun show(ctx: Context, title: String, body: String, tab: String, tag: String) {
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        if (!nm.areNotificationsEnabled()) return
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O && nm.getNotificationChannel(CHANNEL) == null) {
            nm.createNotificationChannel(NotificationChannel(CHANNEL, "Уведомления", NotificationManager.IMPORTANCE_HIGH))
        }
        val open = Intent(ctx, MainActivity::class.java).apply {
            flags = Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_SINGLE_TOP or Intent.FLAG_ACTIVITY_CLEAR_TOP
            putExtra(EXTRA_TAB, tab)
        }
        val pending = PendingIntent.getActivity(
            ctx, (tag.ifEmpty { title }).hashCode(), open,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE,
        )
        val builder = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            Notification.Builder(ctx, CHANNEL)
        } else {
            @Suppress("DEPRECATION")
            Notification.Builder(ctx).setPriority(Notification.PRIORITY_HIGH)
        }
        val n = builder
            .setSmallIcon(R.drawable.ic_stat_kapibara)
            .setContentTitle(title)
            .setContentText(body)
            .setStyle(Notification.BigTextStyle().bigText(body))
            .setAutoCancel(true)
            .setContentIntent(pending)
            .build()
        // тот же вид (tag) заменяет прошлое уведомление — как у веб-пуша
        nm.notify(tag.ifEmpty { null }, 1, n)
    }
}
