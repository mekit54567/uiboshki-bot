package ru.uiboshki.app

import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.webkit.CookieManager
import io.flutter.embedding.android.FlutterActivity
import io.flutter.embedding.engine.FlutterEngine
import io.flutter.plugin.common.MethodChannel
import ru.uiboshki.app.push.PushBridge
import ru.uiboshki.app.widget.WidgetBridge

class MainActivity : FlutterActivity() {
    // Иконка на выбор (5.79): у каждой — свой activity-alias в AndroidManifest.xml
    // (.IconClassic, .IconDepth…, с 5.84 и картинки .IconKremlin/.IconKremlinDark —
    // их пишет tools/app_icons.py), включён ровно один. Список — из манифеста,
    // имена — AppIcon.name в Dart (тёмная картинка — «kremlinDark»).
    private val icons: List<String> by lazy {
        val prefix = "$packageName.Icon"
        @Suppress("DEPRECATION")
        val info = packageManager.getPackageInfo(
            packageName,
            PackageManager.GET_ACTIVITIES or PackageManager.MATCH_DISABLED_COMPONENTS,
        )
        info.activities.orEmpty()
            .map { it.name }
            .filter { it.startsWith(prefix) }
            .map { it.removePrefix(prefix).replaceFirstChar { c -> c.lowercase() } }
    }

    private fun alias(name: String) =
        ComponentName(this, "ru.uiboshki.app.Icon" + name.replaceFirstChar { it.uppercase() })

    private fun enabled(name: String): Boolean =
        when (packageManager.getComponentEnabledSetting(alias(name))) {
            PackageManager.COMPONENT_ENABLED_STATE_ENABLED -> true
            PackageManager.COMPONENT_ENABLED_STATE_DEFAULT -> name == "classic" // как в манифесте
            else -> false
        }

    private fun current(): String = icons.firstOrNull { enabled(it) } ?: "classic"

    private fun switchTo(name: String) {
        if (current() == name) return
        val pm = packageManager
        // сначала включить новую, потом выключить остальные — без иконки не остаться
        pm.setComponentEnabledSetting(
            alias(name),
            PackageManager.COMPONENT_ENABLED_STATE_ENABLED,
            PackageManager.DONT_KILL_APP,
        )
        for (other in icons) {
            if (other == name) continue
            pm.setComponentEnabledSetting(
                alias(other),
                PackageManager.COMPONENT_ENABLED_STATE_DISABLED,
                PackageManager.DONT_KILL_APP,
            )
        }
    }

    override fun configureFlutterEngine(flutterEngine: FlutterEngine) {
        super.configureFlutterEngine(flutterEngine)
        // виджеты рабочего стола: снимок дня из приложения (widget/WidgetBridge.kt)
        WidgetBridge.attach(this, flutterEngine)
        // пуши приложения с шифрованием (push/, lib/app_push.dart); открыли нажатием — вкладка
        PushBridge.attach(this, flutterEngine)
        PushBridge.fromIntent(intent, running = false)
        // вход в СДО страницей (5.93.2): кука MoodleSession — HttpOnly, из Dart её не видно
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "uiboshki/cookies").setMethodCallHandler { call, result ->
            if (call.method == "header") {   // все куки сайта строкой Cookie (вход в Пульс на сервере)
                return@setMethodCallHandler result.success(CookieManager.getInstance().getCookie(call.argument<String>("url") ?: "").orEmpty())
            }
            if (call.method != "get") return@setMethodCallHandler result.notImplemented()
            val url = call.argument<String>("url") ?: ""
            val name = call.argument<String>("name") ?: ""
            val value = CookieManager.getInstance().getCookie(url).orEmpty()
                .split(";")
                .map { it.trim() }
                .firstOrNull { it.startsWith("$name=") }
                ?.substringAfter("=")
            result.success(value)
        }
        MethodChannel(flutterEngine.dartExecutor.binaryMessenger, "uiboshki/icon").setMethodCallHandler { call, result ->
            when (call.method) {
                "supported" -> result.success(true)
                "getIcon" -> result.success(current().takeIf { it != "classic" })
                "setIcon" -> {
                    val name = (call.arguments as? String) ?: "classic"
                    if (name !in icons) {
                        result.error("unknown", "Нет такой иконки: $name", null)
                    } else {
                        try {
                            switchTo(name)
                            result.success(null)
                        } catch (e: Exception) {
                            result.error("failed", e.message, null)
                        }
                    }
                }
                else -> result.notImplemented()
            }
        }
    }

    override fun onNewIntent(intent: Intent) {
        super.onNewIntent(intent)
        PushBridge.fromIntent(intent, running = true)
    }

    override fun onRequestPermissionsResult(requestCode: Int, permissions: Array<String>, grantResults: IntArray) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        PushBridge.onPermissionResult(this, requestCode)
    }

    override fun cleanUpFlutterEngine(flutterEngine: FlutterEngine) {
        PushBridge.detach()
        super.cleanUpFlutterEngine(flutterEngine)
    }
}
