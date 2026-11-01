import Flutter
import Security
import UIKit
import UserNotifications
import WebKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
    // нажатое уведомление ловим с самого запуска (Apple: делегат — до конца запуска)
    UNUserNotificationCenter.current().delegate = PushPlugin.shared
    return super.application(application, didFinishLaunchingWithOptions: launchOptions)
  }

  func didInitializeImplicitFlutterEngine(_ engineBridge: FlutterImplicitEngineBridge) {
    GeneratedPluginRegistrant.register(with: engineBridge.pluginRegistry)
    // явный Optional: собирается, вернёт ли SDK registrar с ! или без
    let registrar: FlutterPluginRegistrar? = engineBridge.pluginRegistry.registrar(forPlugin: "AppIconPlugin")
    if let registrar = registrar {
      AppIconPlugin.register(with: registrar)
    }
    // вход в СДО страницей (5.93.2): кука MoodleSession из WKWebView
    let cookies: FlutterPluginRegistrar? = engineBridge.pluginRegistry.registrar(forPlugin: "CookiesPlugin")
    if let cookies = cookies {
      CookiesPlugin.register(with: cookies)
    }
    // пуши приложения с шифрованием (PushPlugin ниже, lib/app_push.dart)
    let push: FlutterPluginRegistrar? = engineBridge.pluginRegistry.registrar(forPlugin: "PushPlugin")
    if let push = push {
      PushPlugin.register(with: push)
    }
    // виджеты рабочего стола (WidgetBridge.swift)
    let widgets: FlutterPluginRegistrar? = engineBridge.pluginRegistry.registrar(forPlugin: "WidgetBridge")
    if let widgets = widgets {
      WidgetBridge.register(with: widgets)
    }
  }
}

/// Иконка на выбор (5.79): альтернативные иконки — Icon<Имя>.appiconset в
/// Assets.xcassets (ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES в проекте).
/// Из Dart приходит имя AppIcon (depth, sunset…), nil или "classic" — основная.
class AppIconPlugin: NSObject, FlutterPlugin {
  // Какие есть — из Info.plist: его CFBundleAlternateIcons собирает Xcode из
  // ASSETCATALOG_COMPILER_ALTERNATE_APPICON_NAMES (tools/app_icons.py), так что
  // новые иконки-картинки (5.84) не надо перечислять ещё и здесь.
  static let assets: Set<String> = {
    let icons = Bundle.main.object(forInfoDictionaryKey: "CFBundleIcons") as? [String: Any]
    let alt = icons?["CFBundleAlternateIcons"] as? [String: Any]
    return Set(alt?.keys.map { $0 } ?? [])
  }()

  static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(name: "uiboshki/icon", binaryMessenger: registrar.messenger())
    registrar.addMethodCallDelegate(AppIconPlugin(), channel: channel)
  }

  private static func assetName(_ name: String) -> String {
    return "Icon" + name.prefix(1).uppercased() + String(name.dropFirst())
  }

  func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    let app = UIApplication.shared
    switch call.method {
    case "supported":
      result(app.supportsAlternateIcons)
    case "getIcon":
      let current = app.alternateIconName
      // "IconKremlin" → "kremlin", как AppIcon.name в Dart
      result(current.map { name -> String in
        let rest = name.dropFirst(4)
        return rest.prefix(1).lowercased() + rest.dropFirst()
      })
    case "setIcon":
      let name = call.arguments as? String
      var target: String? = nil
      if let name = name, name != "classic" {
        guard AppIconPlugin.assets.contains(AppIconPlugin.assetName(name)) else {
          result(FlutterError(code: "unknown", message: "Нет такой иконки: \(name)", details: nil))
          return
        }
        target = AppIconPlugin.assetName(name)
      }
      guard app.supportsAlternateIcons else {
        result(nil)
        return
      }
      if app.alternateIconName == target {
        result(nil)
        return
      }
      app.setAlternateIconName(target) { error in
        // ответ во Flutter — только с главного потока
        DispatchQueue.main.async {
          if let error = error {
            result(FlutterError(code: "failed", message: error.localizedDescription, details: nil))
          } else {
            result(nil)
          }
        }
      }
    default:
      result(FlutterMethodNotImplemented)
    }
  }
}

/// Кука из WKWebView (общее хранилище, как у webview_flutter): MoodleSession —
/// HttpOnly, со страницы её не прочитать. get {url, name} → значение или nil.
class CookiesPlugin: NSObject, FlutterPlugin {
  static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(name: "uiboshki/cookies", binaryMessenger: registrar.messenger())
    registrar.addMethodCallDelegate(CookiesPlugin(), channel: channel)
  }

  func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    // «header» (01.11, вход в Пульс на сервере): все куки сайта строкой Cookie
    if call.method == "header",
       let args = call.arguments as? [String: Any],
       let url = args["url"] as? String,
       let host = URL(string: url)?.host {
      DispatchQueue.main.async {
        WKWebsiteDataStore.default().httpCookieStore.getAllCookies { all in
          let pairs = all.filter { c in
            let domain = c.domain.hasPrefix(".") ? String(c.domain.dropFirst()) : c.domain
            return host == domain || host.hasSuffix("." + domain)
          }.map { "\($0.name)=\($0.value)" }
          result(pairs.joined(separator: "; "))
        }
      }
      return
    }
    guard call.method == "get",
          let args = call.arguments as? [String: Any],
          let url = args["url"] as? String,
          let name = args["name"] as? String,
          let host = URL(string: url)?.host else {
      result(FlutterMethodNotImplemented)
      return
    }
    DispatchQueue.main.async {
      WKWebsiteDataStore.default().httpCookieStore.getAllCookies { all in
        let cookie = all.first { c in
          let domain = c.domain.hasPrefix(".") ? String(c.domain.dropFirst()) : c.domain
          return c.name == name && (host == domain || host.hasSuffix("." + domain))
        }
        result(cookie?.value)
      }
    }
  }
}

/// Пуши приложения (канал uiboshki/push, lib/app_push.dart): разрешение,
/// токен APNs, ключ расшифровки — в связку ключей с группой приложения, где
/// его найдёт Notification Service Extension (ios/KapibaraNotify). Нажатое
/// уведомление — вкладка из userInfo["tab"], её кладёт расширение.
/// Токен APNs выдаётся только с правом aps-environment (подпись для App Store,
/// docs/app-push.md); без него — ошибка, и тумблер просто не включится.
class PushPlugin: NSObject, FlutterPlugin, UNUserNotificationCenterDelegate {
  static let shared = PushPlugin()
  private var channel: FlutterMethodChannel?
  private var pendingToken: FlutterResult?
  private var pendingTab: String?

  static func register(with registrar: FlutterPluginRegistrar) {
    let channel = FlutterMethodChannel(name: "uiboshki/push", binaryMessenger: registrar.messenger())
    shared.channel = channel
    registrar.addMethodCallDelegate(shared, channel: channel)
    registrar.addApplicationDelegate(shared)
  }

  func handle(_ call: FlutterMethodCall, result: @escaping FlutterResult) {
    let args = call.arguments as? [String: Any]
    switch call.method {
    case "available":
      result(["apns": true, "fcm": false, "rustore": false])
    case "granted":
      UNUserNotificationCenter.current().getNotificationSettings { settings in
        DispatchQueue.main.async { result(settings.authorizationStatus == .authorized) }
      }
    case "permission":
      UNUserNotificationCenter.current().requestAuthorization(options: [.alert, .sound, .badge]) { ok, _ in
        DispatchQueue.main.async { result(ok) }
      }
    case "token":
      pendingToken?(FlutterError(code: "again", message: "Запрос токена повторили", details: nil))
      pendingToken = result
      UIApplication.shared.registerForRemoteNotifications()
    case "setKey":
      PushKeys.save(args?["key"] as? String)
      result(nil)
    case "clear":
      PushKeys.save(nil)
      UIApplication.shared.unregisterForRemoteNotifications()
      result(nil)
    case "takeTab":
      result(pendingTab)
      pendingTab = nil
    default:
      result(FlutterMethodNotImplemented)
    }
  }

  func application(_ application: UIApplication, didRegisterForRemoteNotificationsWithDeviceToken deviceToken: Data) {
    let hex = deviceToken.map { String(format: "%02x", $0) }.joined()
    if let pending = pendingToken {
      pendingToken = nil
      pending(hex)
    } else {
      channel?.invokeMethod("token", arguments: ["platform": "apns", "token": hex])
    }
  }

  func application(_ application: UIApplication, didFailToRegisterForRemoteNotificationsWithError error: Error) {
    pendingToken?(FlutterError(code: "apns", message: error.localizedDescription, details: nil))
    pendingToken = nil
  }

  // приложение открыто — уведомление всё равно показать
  func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    willPresent notification: UNNotification,
    withCompletionHandler completionHandler: @escaping (UNNotificationPresentationOptions) -> Void
  ) {
    completionHandler([.banner, .list, .sound])
  }

  func userNotificationCenter(
    _ center: UNUserNotificationCenter,
    didReceive response: UNNotificationResponse,
    withCompletionHandler completionHandler: @escaping () -> Void
  ) {
    let tab = response.notification.request.content.userInfo["tab"] as? String ?? ""
    // и запомнить: при холодном запуске Dart ещё не слушает — заберёт takeTab
    pendingTab = tab
    channel?.invokeMethod("tab", arguments: tab)
    completionHandler()
  }
}

/// Ключ расшифровки пушей: связка ключей с группой приложения (её же читает
/// расширение); не вышло — настройки группы. nil — стереть.
enum PushKeys {
  static let service = "ru.uiboshki.app.push"

  static func groups() -> [String] {
    let app = Bundle.main.bundleIdentifier ?? "ru.uiboshki.app"
    return ["group.\(app)", "group.ru.uiboshki.app"]
  }

  static func save(_ key: String?) {
    for group in groups() {
      let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: service,
        kSecAttrAccount as String: "key",
        kSecAttrAccessGroup as String: group,
      ]
      SecItemDelete(query as CFDictionary)
      UserDefaults(suiteName: group)?.removeObject(forKey: "push_key")
    }
    guard let key = key else { return }
    for group in groups() {
      var add: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: service,
        kSecAttrAccount as String: "key",
        kSecAttrAccessGroup as String: group,
        kSecAttrAccessible as String: kSecAttrAccessibleAfterFirstUnlockThisDeviceOnly,
      ]
      add[kSecValueData as String] = Data(key.utf8)
      if SecItemAdd(add as CFDictionary, nil) == errSecSuccess { return }
    }
    // связка ключей с группой недоступна (подпись без группы) — хотя бы настройки группы
    for group in groups() {
      if let defaults = UserDefaults(suiteName: group),
         FileManager.default.containerURL(forSecurityApplicationGroupIdentifier: group) != nil {
        defaults.set(key, forKey: "push_key")
        return
      }
    }
  }
}

