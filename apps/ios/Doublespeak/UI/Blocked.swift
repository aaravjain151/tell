import SwiftUI

/// Main-screen entry to the block list.
struct BlockedCard: View {
    @EnvironmentObject var c: ListenController
    @EnvironmentObject var b: BlockController
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("Blocked numbers").font(.ds(20, .regular, relativeTo: .title3)).foregroundStyle(Theme.ink)
                .accessibilityAddTraits(.isHeader)
            Text(b.entries.isEmpty ? "Numbers you block never ring. The list stays on this phone."
                                   : "\(b.entries.count) blocked. The list stays on this phone.")
                .font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted)
            Button("Manage blocked numbers") { c.sheet = .blocked }
                .buttonStyle(DSButtonStyle(kind: .ghost, height: 48)).padding(.top, 4)
        }
        .card()
    }
}

struct BlockedSheet: View {
    @EnvironmentObject var c: ListenController
    @EnvironmentObject var b: BlockController
    @State private var number = ""
    @State private var label = ""
    @FocusState private var focus: Bool

    var body: some View {
        SheetFrame(title: "Blocked numbers") {
            enableCard.padding(.top, 14)

            VStack(alignment: .leading, spacing: 10) {
                Text("Block a number").font(.ds(17, .medium, relativeTo: .headline)).foregroundStyle(Theme.ink)
                TextField("+1 415 555 0123", text: $number)
                    .keyboardType(.phonePad).textContentType(.telephoneNumber).focused($focus)
                    .font(.ds(17, .regular, relativeTo: .body)).padding(12).frame(minHeight: 48)
                    .background(Theme.plane, in: RoundedRectangle(cornerRadius: 12))
                    .accessibilityLabel("Phone number to block")
                TextField("Note (optional)", text: $label)
                    .font(.ds(17, .regular, relativeTo: .body)).padding(12).frame(minHeight: 48)
                    .background(Theme.plane, in: RoundedRectangle(cornerRadius: 12))
                    .submitLabel(.done)
                Button("Block") {
                    if b.add(number: number, label: label) { number = ""; label = ""; focus = false }
                }
                .buttonStyle(DSButtonStyle(kind: .primary, height: 52))
                .disabled(number.trimmingCharacters(in: .whitespaces).isEmpty)
                if let m = b.message {
                    Text(m).font(.ds(14, .regular, relativeTo: .footnote)).foregroundStyle(Theme.amber)
                }
            }.padding(.top, 22)

            VStack(alignment: .leading, spacing: 0) {
                Text("On the list").font(.ds(17, .medium, relativeTo: .headline)).foregroundStyle(Theme.ink).padding(.bottom, 8)
                if b.entries.isEmpty {
                    Text("Nothing blocked yet.").font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted)
                }
                ForEach(b.entries) { e in
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(e.number).font(.system(size: 16, weight: .medium, design: .monospaced)).foregroundStyle(Theme.ink)
                            if !e.label.isEmpty || e.reports > 1 {
                                Text([e.label, e.reports > 1 ? "blocked \(e.reports) times" : ""].filter { !$0.isEmpty }.joined(separator: " · "))
                                    .font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted)
                            }
                        }
                        Spacer()
                        Button("Remove") { b.remove(e) }
                            .font(.ds(14, .regular, relativeTo: .footnote)).foregroundStyle(Theme.ink)
                            .frame(minWidth: 72, minHeight: 44).background(Theme.plane2, in: Capsule())
                            .accessibilityLabel("Remove \(e.number)")
                    }
                    .padding(.vertical, 6)
                    .overlay(alignment: .bottom) { Rectangle().fill(Theme.line).frame(height: 1) }
                }
            }.padding(.top, 24)

            Text("Tell has no database of known spam numbers and sends nothing anywhere, so it can only block numbers you add. Calls from hidden numbers cannot be matched.")
                .font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted).padding(.top, 18)
            Button("Close") { c.sheet = nil }.buttonStyle(DSButtonStyle(kind: .ghost, height: 52)).padding(.top, 18)
        }
        .onAppear { b.refresh() }
    }

    private var enableCard: some View {
        VStack(alignment: .leading, spacing: 8) {
            if !b.sharedWithExtension {
                Text("Not connected to call blocking").font(.ds(17, .medium, relativeTo: .headline)).foregroundStyle(Theme.ink)
                Text("This build cannot share the list with the call blocker: it was signed without an App Group or Keychain Sharing, which iOS needs for that. The list is kept here, but calls are not blocked yet. See docs/BLOCK-SPAM.md.")
                    .font(.ds(14, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted)
            } else if b.enablement == .enabled {
                Text("Call blocking is on").font(.ds(17, .medium, relativeTo: .headline)).foregroundStyle(Theme.ink)
                Text("Numbers on this list will not ring.").font(.ds(14, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted)
            } else {
                Text("Turn on call blocking").font(.ds(17, .medium, relativeTo: .headline)).foregroundStyle(Theme.ink)
                Text("Open Settings > Phone > Call Blocking & Identification and switch on Tell Call Blocker. iOS only blocks once you do this, and only the app can ask.")
                    .font(.ds(14, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted)
                Button("Open Settings") { b.openSettings() }.buttonStyle(DSButtonStyle(kind: .ghost, height: 48)).padding(.top, 4)
            }
            if b.reloadFailed {
                Text("iOS did not accept the update yet. Check that the switch above is on.").font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.amber)
            }
        }
        .card(border: b.sharedWithExtension && b.enablement == .enabled ? nil : Theme.amber)
    }
}
