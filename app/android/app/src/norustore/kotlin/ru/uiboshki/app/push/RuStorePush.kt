package ru.uiboshki.app.push

import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.IBinder

/**
 * Сборка без RuStore Push (по умолчанию: SDK RuStore — из их репозитория,
 * а он не всегда доступен сборке; включается RUSTORE_PROJECT_ID при сборке,
 * см. app/build.gradle.kts и docs/app-push.md). Здесь — заглушки.
 */
object RuStorePush {
    @Suppress("UNUSED_PARAMETER")
    fun available(ctx: Context, done: (Boolean) -> Unit) = done(false)

    fun token(done: (String?, String?) -> Unit) = done(null, "RuStore Push не встроен в эту сборку")

    fun delete() {}
}

/** Выключен в манифесте (rustoreEnabled = false). */
class RuStoreService : Service() {
    override fun onBind(intent: Intent?): IBinder? = null
}
