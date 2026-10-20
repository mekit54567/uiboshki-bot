// Notification Service Extension: пуш APNs приходит с заглушкой «Капибара /
// Новое уведомление» и шифротекстом e (сервер — app_push.py). Здесь —
// расшифровка AES-256-GCM ключом этого телефона (его кладёт приложение,
// PushPlugin в AppDelegate.swift) и настоящие заголовок и текст. Не вышло
// (нет ключа, старый ключ, истекло время) — остаётся заглушка.
// Как подключить target в Xcode — docs/app-push.md.
import CryptoKit
import Foundation
import Security
import UserNotifications

class NotificationService: UNNotificationServiceExtension {
  private var handler: ((UNNotificationContent) -> Void)?
  private var content: UNMutableNotificationContent?

  override func didReceive(
    _ request: UNNotificationRequest,
    withContentHandler contentHandler: @escaping (UNNotificationContent) -> Void
  ) {
    handler = contentHandler
    guard let content = request.content.mutableCopy() as? UNMutableNotificationContent else {
      contentHandler(request.content)
      return
    }
    self.content = content
    if let data = PushOpen.payload(content.userInfo) {
      if let title = data["title"], !title.isEmpty { content.title = title }
      content.body = data["body"] ?? ""
      var info = content.userInfo
      info["tab"] = data["tab"] ?? ""
      info.removeValue(forKey: "e") // шифротекст больше не нужен
      content.userInfo = info
      if let tag = data["tag"], !tag.isEmpty { content.threadIdentifier = tag }
    }
    contentHandler(content)
  }

  override func serviceExtensionTimeWillExpire() {
    if let handler = handler, let content = content { handler(content) }
  }
}

enum PushOpen {
  static let service = "ru.uiboshki.app.push"

  /// {"v":1,"e":base64(nonce | шифротекст | тег)} → {"title","body","tab","tag"}.
  static func payload(_ info: [AnyHashable: Any]) -> [String: String]? {
    guard (info["v"] as? Int) == 1 || (info["v"] as? String) == "1",
          let e = info["e"] as? String,
          let raw = Data(base64Encoded: e), raw.count > 28,
          let key = loadKey() else { return nil }
    do {
      let box = try AES.GCM.SealedBox(combined: raw)
      let plain = try AES.GCM.open(box, using: SymmetricKey(data: key))
      let obj = try JSONSerialization.jsonObject(with: plain) as? [String: Any]
      return obj?.compactMapValues { $0 as? String }
    } catch {
      return nil
    }
  }

  /// Группа приложения: от id приложения (AltStore дописывает Team ID), иначе — как в проекте.
  static func groups() -> [String] {
    var parts = (Bundle.main.bundleIdentifier ?? "").split(separator: ".").map(String.init)
    if parts.last == "KapibaraNotify" { parts.removeLast() }
    let app = parts.isEmpty ? "ru.uiboshki.app" : parts.joined(separator: ".")
    return ["group.\(app)", "group.ru.uiboshki.app"]
  }

  /// Ключ: связка ключей с общей группой; запасной путь — настройки группы.
  static func loadKey() -> Data? {
    for group in groups() {
      let query: [String: Any] = [
        kSecClass as String: kSecClassGenericPassword,
        kSecAttrService as String: service,
        kSecAttrAccount as String: "key",
        kSecAttrAccessGroup as String: group,
        kSecReturnData as String: true,
      ]
      var item: CFTypeRef?
      if SecItemCopyMatching(query as CFDictionary, &item) == errSecSuccess,
         let data = item as? Data, let b64 = String(data: data, encoding: .utf8),
         let key = Data(base64Encoded: b64), key.count == 32 {
        return key
      }
      if let b64 = UserDefaults(suiteName: group)?.string(forKey: "push_key"),
         let key = Data(base64Encoded: b64), key.count == 32 {
        return key
      }
    }
    return nil
  }
}
