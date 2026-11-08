import SwiftUI

struct MenuBarIcon: View {
    @ObservedObject var model: AppModel
    var body: some View {
        let s = model.display
        Image(systemName: s.symbol)
            .symbolRenderingMode(s.tint == nil ? .monochrome : .palette)
            .foregroundStyle(s.tint ?? .primary, .primary)
            .accessibilityLabel(s.accessibilityName)
    }
}

struct MenuView: View {
    @ObservedObject var model: AppModel
    let windows: WindowPresenter

    var body: some View {
        let s = model.display
        VStack(alignment: .leading, spacing: 0) {
            header(s)
            if let line = model.verdictLine { verdict(line, s) }
            Divider().padding(.vertical, 6)
            actions(s)
            Divider().padding(.vertical, 6)
            Toggle(isOn: Binding(get: { model.loginItemOn }, set: { model.setLaunchAtLogin($0) })) {
                Text("Launch at login")
            }
            .toggleStyle(.switch).controlSize(.small)
            .padding(.horizontal, 10).frame(height: 30)
            if let note = model.loginItemNote {
                Text(note).font(.caption).foregroundStyle(.secondary).padding(.horizontal, 10)
            }
            footerNotes
            Divider().padding(.vertical, 6)
            MenuRow(title: "Settings", systemImage: "gearshape") { windows.showSettings() }
            MenuRow(title: "Quit Doublespeak", systemImage: "xmark.circle") { model.quit() }
        }
        .padding(8)
        .frame(width: 312)
    }

    private func header(_ s: DisplayState) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Image(systemName: s.symbol)
                .font(.system(size: 26, weight: .regular))
                .symbolRenderingMode(s.tint == nil ? .monochrome : .palette)
                .foregroundStyle(s.tint ?? .secondary, .primary)
                .frame(width: 34)
            VStack(alignment: .leading, spacing: 3) {
                Text(model.title).font(.system(size: 15, weight: .semibold))
                Text(model.detail).font(.system(size: 12)).foregroundStyle(.secondary)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 10).padding(.top, 6)
        .accessibilityElement(children: .combine)
    }

    private func verdict(_ line: String, _ s: DisplayState) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text("Last verdict").font(.caption).foregroundStyle(.secondary)
            Text(line).font(.system(size: 13)).fixedSize(horizontal: false, vertical: true)
        }
        .padding(10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 8, style: .continuous).fill((s.tint ?? Color.primary).opacity(0.10)))
        .padding(.horizontal, 6).padding(.top, 8)
    }

    @ViewBuilder private func actions(_ s: DisplayState) -> some View {
        if model.needsOnboarding {
            MenuRow(title: "Finish setup", systemImage: "checkmark.circle") { windows.showWelcome() }
        } else {
            MenuRow(title: "Open Doublespeak", systemImage: "safari") { model.openDoublespeak() }
            if s == .paused {
                MenuRow(title: "Resume", systemImage: "play.circle") { model.resume() }
            } else if model.enabled {
                MenuRow(title: "Pause for 1 hour", systemImage: "pause.circle") { model.pauseForOneHour() }
            }
            if s == .engineProblem { MenuRow(title: "Restart", systemImage: "arrow.clockwise") { model.restartAll() } }
            MenuRow(title: model.enabled ? "Turn off" : "Turn on", systemImage: "power") { model.setEnabled(!model.enabled) }
        }
    }

    private var footerNotes: some View {
        VStack(alignment: .leading, spacing: 8) {
            Label(model.privacyRow, systemImage: "lock.fill")
                .font(.system(size: 12)).foregroundStyle(.secondary)
            Text(Wording.limits).font(.system(size: 11)).foregroundStyle(.secondary)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 10).padding(.top, 6)
    }
}
