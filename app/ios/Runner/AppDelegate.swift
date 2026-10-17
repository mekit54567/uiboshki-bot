import Flutter
import UIKit
import WebKit

@main
@objc class AppDelegate: FlutterAppDelegate, FlutterImplicitEngineDelegate {
  override func application(
    _ application: UIApplication,
    didFinishLaunchingWithOptions launchOptions: [UIApplication.LaunchOptionsKey: Any]?
  ) -> Bool {
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
