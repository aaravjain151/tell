import Foundation
import ServiceManagement
import UserNotifications
import AppKit

/// Notifications: only for an alert that CHANGED to amber or red; fixed wording; sound is opt-in.
final class Notifier {
    enum Permission: Equatable { case unknown, allowed, denied }

    func current() async -> Permission {
        let s = await UNUserNotificationCenter.current().notificationSettings()
        switch s.authorizationStatus {
        case .authorized, .provisional, .ephemeral: return .allowed
        case .denied: return .denied
        default: return .unknown
        }
    }

    func request() async -> Permission {
        _ = try? await UNUserNotificationCenter.current().requestAuthorization(options: [.alert])
        return await current()
    }

    func post(_ level: AlertLevel, sound: Bool) {
        guard let text = Wording.notification(for: level) else { return }
        let c = UNMutableNotificationContent()
        c.title = "Doublespeak"
        c.body = text
        c.sound = sound ? .default : nil
        c.interruptionLevel = level == .red ? .timeSensitive : .active
        let req = UNNotificationRequest(identifier: "alert-\(level.rawValue)", content: c, trigger: nil)
        UNUserNotificationCenter.current().add(req)
    }
}

/// Launch at login through SMAppService only. OFF until the user flips the switch. No plist is written by us.
enum LoginItem {
    static var status: SMAppService.Status { SMAppService.mainApp.status }
    static var isOn: Bool { status == .enabled }
    static var needsApproval: Bool { status == .requiresApproval }

    @discardableResult
    static func set(_ on: Bool) -> String? {
        do {
            if on { try SMAppService.mainApp.register() } else { try SMAppService.mainApp.unregister() }
            return nil
        } catch {
            return error.localizedDescription
        }
    }
    static func openSystemSettings() { SMAppService.openSystemSettingsLoginItems() }
}

enum SystemLinks {
    static let audioCapture = URL(string: "x-apple.systempreferences:com.apple.preference.security?Privacy_AudioCapture")!
    static let notifications = URL(string: "x-apple.systempreferences:com.apple.Notifications-Settings.extension")!
    static func open(_ u: URL) { NSWorkspace.shared.open(u) }
}

/// User-editable settings. Plain UserDefaults; nothing secret is stored.
struct Prefs {
    private let d = UserDefaults.standard
    var repoPath: String {
        get { d.string(forKey: "repoPath") ?? LaunchPlan.defaultRepo }
        nonmutating set { d.set(newValue, forKey: "repoPath") }
    }
    var port: Int {
        get { let p = d.integer(forKey: "port"); return p == 0 ? 8000 : p }
        nonmutating set { d.set(newValue, forKey: "port") }
    }
    var consentGiven: Bool {
        get { d.bool(forKey: "consentGiven") }
        nonmutating set { d.set(newValue, forKey: "consentGiven") }
    }
    var enabled: Bool {
        get { d.object(forKey: "enabled") as? Bool ?? true }
        nonmutating set { d.set(newValue, forKey: "enabled") }
    }
    var sound: Bool {
        get { d.bool(forKey: "sound") }
        nonmutating set { d.set(newValue, forKey: "sound") }
    }
}
