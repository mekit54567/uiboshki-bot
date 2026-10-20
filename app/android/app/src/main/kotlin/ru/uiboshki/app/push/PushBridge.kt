package ru.uiboshki.app.push

import android.Manifest
import android.app.Activity
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import com.google.firebase.FirebaseApp
import com.google.firebase.messaging.FirebaseMessaging
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel

/**
 * Канал uiboshki/push (lib/app_push.dart): какие сервисы есть, разрешение,
 * токен, ключ, нажатое уведомление. FCM работает, только если сборка с
 * google-services.json (иначе FirebaseApp нет — и пуши через Google выключены);
 * RuStore — только в сборке с RUSTORE_PROJECT_ID (RuStorePush.kt).
 */
object PushBridge {
    private const val REQUEST = 4710
    private var channel: MethodChannel? = null
    private var pendingPermission: MethodChannel.Result? = null
    private var pendingTab: String? = null
    private val main = Handler(Looper.getMainLooper())

    fun attach(activity: Activity, engine: FlutterEngine) {
        val ch = MethodChannel(engine.dartExecutor.binaryMessenger, "uiboshki/push")
        channel = ch
        ch.setMethodCallHandler { call, result ->
            val ctx = activity.applicationContext
            when (call.method) {
                "available" -> RuStorePush.available(ctx) { rustore ->
                    main.post { result.success(mapOf("fcm" to fcmReady(ctx), "rustore" to rustore, "apns" to false)) }
                }
                "granted" -> result.success(granted(ctx))
                "permission" -> askPermission(activity, result)
                "token" -> token(ctx, call.argument<String>("platform") ?: "", result)
                "setKey" -> {
                    PushNotify.setKey(ctx, call.argument<String>("key"))
                    result.success(null)
                }
                "clear" -> {
                    PushNotify.setKey(ctx, null)
                    when (call.argument<String>("platform")) {
                        "fcm" -> if (fcmReady(ctx)) FirebaseMessaging.getInstance().deleteToken()
                        "rustore" -> RuStorePush.delete()
                    }
                    result.success(null)
                }
                "takeTab" -> {
                    result.success(pendingTab)
                    pendingTab = null
                }
                else -> result.notImplemented()
            }
        }
    }

    fun detach() {
        channel = null
    }

    /** Приложение открыли нажатием на уведомление (onCreate или onNewIntent). */
    fun fromIntent(intent: Intent?, running: Boolean) {
        val tab = intent?.getStringExtra(PushNotify.EXTRA_TAB) ?: return
        intent.removeExtra(PushNotify.EXTRA_TAB)
        val ch = channel
        if (running && ch != null) ch.invokeMethod("tab", tab) else pendingTab = tab
    }

    /** Сервис выдал новый токен — приложение перерегистрируется, если открыто. */
    fun newToken(platform: String, token: String) {
        main.post { channel?.invokeMethod("token", mapOf("platform" to platform, "token" to token)) }
    }

    private fun fcmReady(ctx: Context): Boolean = try {
        FirebaseApp.getApps(ctx).isNotEmpty()
    } catch (e: Exception) {
        false
    }

    private fun granted(ctx: Context): Boolean {
        val nm = ctx.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
        return nm.areNotificationsEnabled()
    }

    private fun askPermission(activity: Activity, result: MethodChannel.Result) {
        if (Build.VERSION.SDK_INT < 33 ||
            activity.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED
        ) {
            result.success(granted(activity))
            return
        }
        pendingPermission?.success(false)
        pendingPermission = result
        activity.requestPermissions(arrayOf(Manifest.permission.POST_NOTIFICATIONS), REQUEST)
    }

    fun onPermissionResult(activity: Activity, requestCode: Int) {
        if (requestCode != REQUEST) return
        pendingPermission?.success(granted(activity))
        pendingPermission = null
    }

    private fun token(ctx: Context, platform: String, result: MethodChannel.Result) {
        when (platform) {
            "fcm" -> {
                if (!fcmReady(ctx)) return result.error("off", "Пуши через Google не настроены в этой сборке", null)
                FirebaseMessaging.getInstance().token.addOnCompleteListener { t ->
                    main.post {
                        if (t.isSuccessful) result.success(t.result)
                        else result.error("fcm", t.exception?.message ?: "Google не выдал токен", null)
                    }
                }
            }
            "rustore" -> RuStorePush.token { token, error ->
                main.post { if (token != null) result.success(token) else result.error("rustore", error, null) }
            }
            else -> result.error("off", "Нет такого сервиса: $platform", null)
        }
    }
}
