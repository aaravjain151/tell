import SwiftUI
import AppKit

/// Plain NSWindows with hosted SwiftUI: reliable for a menu-bar-only app (no Dock icon, no scene juggling).
@MainActor
final class WindowPresenter {
    let model: AppModel
    private var welcome: NSWindow?
    private var settings: NSWindow?

    init(model: AppModel) { self.model = model }

    func showWelcome() {
        show(&welcome, title: "Welcome to Doublespeak", size: NSSize(width: 460, height: 520)) {
            WelcomeView(model: model, close: { [weak self] in self?.welcome?.close() })
        }
    }

    func showSettings() {
        show(&settings, title: "Doublespeak Settings", size: NSSize(width: 480, height: 460)) {
            SettingsView(model: model)
        }
    }

    private func show<V: View>(_ slot: inout NSWindow?, title: String, size: NSSize, @ViewBuilder _ content: () -> V) {
        if slot == nil {
            let w = NSWindow(contentRect: NSRect(origin: .zero, size: size),
                             styleMask: [.titled, .closable], backing: .buffered, defer: false)
            w.title = title
            w.isReleasedWhenClosed = false
            w.contentViewController = NSHostingController(rootView: content())
            w.center()
            slot = w
        }
        NSApp.activate(ignoringOtherApps: true)
        slot?.makeKeyAndOrderFront(nil)
    }
}

struct WelcomeView: View {
    @ObservedObject var model: AppModel
    let close: () -> Void
    @State private var step = 0

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            switch step {
            case 0: privacy
            case 1: permissions
            default: ready
            }
            Spacer(minLength: 0)
        }
        .padding(28)
        .frame(width: 460, height: 520, alignment: .topLeading)
    }

    private var privacy: some View {
        VStack(alignment: .leading, spacing: 14) {
            Image(systemName: "ear").font(.system(size: 34)).foregroundStyle(Palette.teal)
            Text("Before it listens").font(.system(size: 24, weight: .semibold))
            Text(Wording.consent).font(.system(size: 15)).fixedSize(horizontal: false, vertical: true)
            Text("It only listens, never talks to the caller, and works on calls played on this Mac.")
                .foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Spacer().frame(height: 6)
            HStack {
                Spacer()
                Button("I understand, continue") { model.acceptConsent(); step = 1 }
                    .keyboardShortcut(.defaultAction).controlSize(.large)
            }
        }
    }

    private var permissions: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Two macOS permissions").font(.system(size: 24, weight: .semibold))
            permissionBlock(
                icon: "waveform", title: "Audio capture",
                body: "The first time a call plays, macOS asks to let Doublespeak capture audio from other apps. The prompt shows this sentence: \u{201C}\(Bundle.main.object(forInfoDictionaryKey: "NSAudioCaptureUsageDescription") as? String ?? "")\u{201D} Choose Allow. If you choose Don't Allow, macOS hands it silence and it hears nothing. Fix it later in System Settings, Privacy & Security, Screen & System Audio Recording.",
                button: "Open audio settings") { SystemLinks.open(SystemLinks.audioCapture) }
            permissionBlock(
                icon: "bell", title: "Notifications",
                body: model.notifications == .allowed ? "Allowed. You get one notice when a call turns amber or red, with fixed wording and no sound."
                    : model.notifications == .denied ? "Denied. The menu bar icon still changes colour and shape, but no notice appears. Turn it on in System Settings, Notifications."
                    : "macOS asks \u{201C}Doublespeak would like to send you notifications\u{201D}. Choose Allow to get one notice when a call turns amber or red.",
                button: model.notifications == .unknown ? "Ask now" : "Open notification settings") {
                    if model.notifications == .unknown { model.requestNotifications() } else { SystemLinks.open(SystemLinks.notifications) }
                }
            Spacer().frame(height: 4)
            HStack { Spacer(); Button("Continue") { step = 2 }.keyboardShortcut(.defaultAction).controlSize(.large) }
        }
    }

    private func permissionBlock(icon: String, title: String, body: String, button: String, action: @escaping () -> Void) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: icon).font(.system(size: 18)).frame(width: 26).foregroundStyle(Palette.teal)
            VStack(alignment: .leading, spacing: 6) {
                Text(title).font(.system(size: 15, weight: .semibold))
                Text(body).font(.system(size: 13)).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
                Button(button, action: action).controlSize(.small)
            }
        }
    }

    private var ready: some View {
        VStack(alignment: .leading, spacing: 14) {
            Image(systemName: "checkmark.circle").font(.system(size: 34)).foregroundStyle(Palette.teal)
            Text("Doublespeak is on").font(.system(size: 24, weight: .semibold))
            Text("Look for the ear in your menu bar. It turns into a waveform while a call is being listened to, and that icon stays visible for the whole call.")
                .fixedSize(horizontal: false, vertical: true)
            Text(Wording.limits).foregroundStyle(.secondary).fixedSize(horizontal: false, vertical: true)
            Spacer().frame(height: 6)
            HStack { Spacer(); Button("Done") { close() }.keyboardShortcut(.defaultAction).controlSize(.large) }
        }
    }
}

struct SettingsView: View {
    @ObservedObject var model: AppModel
    @State private var repo = ""
    @State private var port = ""

    var body: some View {
        Form {
            Section("Where Doublespeak lives") {
                HStack {
                    TextField("Folder", text: $repo).textFieldStyle(.roundedBorder)
                    Button("Choose") { choose() }
                }
                TextField("Engine port", text: $port).textFieldStyle(.roundedBorder).frame(width: 120)
                Button("Apply and restart") {
                    model.repoPath = repo.trimmingCharacters(in: .whitespaces)
                    model.port = Int(port) ?? 8000
                    model.restartAll()
                }
                Text("Needs the .venv, the engine and the built audio tap in that folder. Nothing in .env is read by this app.")
                    .font(.caption).foregroundStyle(.secondary)
            }
            Section("Alerts") {
                LabeledContent("Sensitivity", value: "Balanced (set by the engine, not adjustable here)")
                Toggle("Play a sound with alerts", isOn: $model.sound)
                LabeledContent("Notifications", value: model.notifications == .allowed ? "Allowed" : model.notifications == .denied ? "Denied" : "Not asked yet")
                if model.notifications != .allowed {
                    Button(model.notifications == .unknown ? "Ask now" : "Open notification settings") {
                        if model.notifications == .unknown { model.requestNotifications() } else { SystemLinks.open(SystemLinks.notifications) }
                    }
                }
            }
            Section("Permissions") {
                Button("Open audio capture settings") { SystemLinks.open(SystemLinks.audioCapture) }
                if LoginItem.needsApproval { Button("Open Login Items settings") { LoginItem.openSystemSettings() } }
            }
        }
        .formStyle(.grouped)
        .onAppear { repo = model.repoPath; port = String(model.port) }
    }

    private func choose() {
        let p = NSOpenPanel()
        p.canChooseDirectories = true; p.canChooseFiles = false; p.allowsMultipleSelection = false
        if p.runModal() == .OK, let u = p.url { repo = u.path }
    }
}
