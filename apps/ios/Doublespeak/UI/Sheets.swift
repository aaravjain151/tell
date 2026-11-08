import SwiftUI

struct AlertTakeover: View {
    var v: VerdictView
    var topPad: CGFloat = 0
    @EnvironmentObject var c: ListenController
    var body: some View {
        ZStack {
            Theme.alertBg.ignoresSafeArea()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    Image(systemName: "exclamationmark.triangle").font(.system(size: 52, weight: .regular)).accessibilityHidden(true)
                    Text("This looks like a scam")
                        .font(.ds(40, .light, relativeTo: .largeTitle)).lineSpacing(-8).padding(.top, 16)
                        .accessibilityAddTraits(.isHeader)
                    Text("Hang up. Do not send money, cards, or codes.")
                        .font(.ds(21, .regular, relativeTo: .title3)).padding(.top, 16)
                    VStack(alignment: .leading, spacing: 8) {
                        ForEach(v.reasons, id: \.self) { r in
                            HStack(alignment: .firstTextBaseline, spacing: 10) {
                                Rectangle().frame(width: 6, height: 6).accessibilityHidden(true)
                                Text(r).font(.ds(16, .regular, relativeTo: .body))
                            }
                        }
                    }.padding(.top, 20).opacity(0.92)
                    Button("Dismiss") { c.dismissAlert() }
                        .buttonStyle(DSButtonStyle(kind: .alert, height: 64)).padding(.top, 28)
                    Text("Dismiss clears this alert. Doublespeak keeps listening and will warn again if there is new evidence.")
                        .font(.ds(14, .regular, relativeTo: .footnote)).opacity(0.85).multilineTextAlignment(.center).padding(.top, 14)
                }
                .foregroundStyle(Theme.alertFg)
                .padding(24).padding(.top, topPad).frame(maxWidth: 480).frame(maxWidth: .infinity)
                .frame(minHeight: UIScreen.main.bounds.height * 0.8)
            }
            .ignoresSafeArea(.container, edges: .top)
        }
        .accessibilityAddTraits(.isModal)
        .accessibilityElement(children: .contain)
    }
}

struct SheetFrame<Content: View>: View {
    var title: String
    @ViewBuilder var content: Content
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text(title).font(.ds(26, .light, relativeTo: .title)).foregroundStyle(Theme.ink)
                    .accessibilityAddTraits(.isHeader)
                content
            }
            .padding(.horizontal, 20).padding(.top, 28).padding(.bottom, 24)
        }
        .background(Theme.bg.ignoresSafeArea())
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
    }
}

struct ConsentSheet: View {
    @EnvironmentObject var c: ListenController
    var body: some View {
        SheetFrame(title: "Before you listen") {
            Text(ListenController.consentText).font(.ds(17, .regular, relativeTo: .body)).foregroundStyle(Theme.ink).padding(.top, 12)
            Text("This works in speaker mode only: the call has to play out loud near this phone, from another device.")
                .font(.ds(14, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted).padding(.top, 12)
            VStack(spacing: 10) {
                Button("I understand, continue") { c.consentGiven() }.buttonStyle(DSButtonStyle(kind: .primary, height: 64))
                Button("Not now") { c.consentDeclined() }.buttonStyle(DSButtonStyle(kind: .ghost, height: 52))
            }.padding(.top, 22)
        }
    }
}

struct SpeakerSheet: View {
    @EnvironmentObject var c: ListenController
    var body: some View {
        SheetFrame(title: "How speaker mode works") {
            Text("iPhone does not give apps the audio of a phone call, and it does not let apps use the microphone during one. So Doublespeak listens the way you do: through the microphone, to a call playing out loud near this phone.")
                .font(.ds(17, .regular, relativeTo: .body)).foregroundStyle(Theme.ink).padding(.top, 12)
            VStack(alignment: .leading, spacing: 12) {
                fact("It hears", " a call playing from another device's speaker, or a recording played near the phone, plus your voice and the room.")
                fact("It cannot listen to a call on this iPhone.", " While a call is active iOS keeps the microphone from apps. For calls on this iPhone, use the Mac route (Calls on Other Devices).")
                fact("It does not hear", " a call held to your ear, on Bluetooth, or on headphones.")
                fact("Accuracy is lower", " than with clean audio, so the engine caps how sure it says it is.")
                fact("It is not on-device.", " The analysis runs on your computer; the phone only listens and shows the answer.")
            }.padding(.top, 16)
            Button("Got it") { c.sheet = nil }.buttonStyle(DSButtonStyle(kind: .primary, height: 56)).padding(.top, 22)
        }
    }
    private func fact(_ b: String, _ rest: String) -> some View {
        (Text(b).font(.ds(15, .medium, relativeTo: .subheadline)) + Text(rest).font(.ds(15, .regular, relativeTo: .subheadline)))
            .foregroundStyle(Theme.ink).fixedSize(horizontal: false, vertical: true)
    }
}

struct ConnectSheet: View {
    @EnvironmentObject var c: ListenController
    var body: some View {
        SheetFrame(title: c.mode == .offline ? "Connect to your computer" : "Connected to your computer") {
            ConnectCard(full: false).padding(.top, 12)
            Button("Close") { c.sheet = nil }.buttonStyle(DSButtonStyle(kind: .ghost, height: 52)).padding(.top, 22)
        }
    }
}

struct ConnectCard: View {
    var full: Bool
    @EnvironmentObject var c: ListenController
    @State private var copied = false

    private var command: String { "python3 tools/ios/bridge.py --token \(PairingToken.display(c.token))" }
    private var up: Bool { c.mode != .offline }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            if full { Text("Connect to your computer").font(.ds(20, .regular, relativeTo: .title3)).foregroundStyle(Theme.ink) }
            Text(up ? "The bridge is connected over the USB cable. Audio goes only there."
                    : "Doublespeak runs on your computer. The phone only listens and sends the audio over the USB cable. Nothing goes over Wi-Fi or the internet.")
                .font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted)
            VStack(alignment: .leading, spacing: 4) {
                Text("Pairing code").font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted)
                Text(PairingToken.display(c.token)).font(.system(size: 30, weight: .medium, design: .monospaced)).foregroundStyle(Theme.ink)
                    .minimumScaleFactor(0.6).lineLimit(1)
                    .accessibilityLabel("Pairing code \(PairingToken.display(c.token).map { String($0) }.joined(separator: " "))")
            }
            if !up {
                Text("On your computer, in the Doublespeak folder, with the phone plugged in and unlocked:").font(.ds(14, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted)
                HStack(spacing: 8) {
                    Text(command).font(.system(size: 12.5, weight: .medium, design: .monospaced)).foregroundStyle(Theme.ink)
                        .textSelection(.enabled).frame(maxWidth: .infinity, alignment: .leading)
                    Button(copied ? "Copied" : "Copy") {
                        UIPasteboard.general.string = command; copied = true
                        DispatchQueue.main.asyncAfter(deadline: .now() + 2) { copied = false }
                    }
                    .font(.ds(14, .regular, relativeTo: .footnote)).foregroundStyle(Theme.ink)
                    .frame(minWidth: 64, minHeight: 44).background(Theme.plane2, in: RoundedRectangle(cornerRadius: 10))
                }
                .padding(.leading, 14).padding(.trailing, 6).padding(.vertical, 6)
                .background(Theme.bg, in: RoundedRectangle(cornerRadius: 14))
                .overlay(RoundedRectangle(cornerRadius: 14).stroke(Theme.line, lineWidth: 1))
            }
            VStack(alignment: .leading, spacing: 10) {
                check(up, "Bridge", up ? "Connected" : "Waiting for the command above")
                check(c.engine == .up, "Engine on your computer", c.engine == .up ? "Answering" : (up ? "Checked when you start listening" : "Start it with make api"))
            }
            Button("How speaker mode works") { c.sheet = .speaker }
                .font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted).underline().frame(minHeight: 44)
        }
        .card()
    }

    private func check(_ ok: Bool, _ t: String, _ s: String) -> some View {
        HStack(alignment: .top, spacing: 10) {
            Circle().fill(ok ? Theme.teal : Color.clear).overlay(Circle().stroke(ok ? Theme.teal : Theme.unsure, lineWidth: 2))
                .frame(width: 20, height: 20).padding(.top, 1).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 0) {
                Text(t).font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.ink)
                Text(s).font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted)
            }
        }
        .accessibilityElement(children: .combine)
    }
}
