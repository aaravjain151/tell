import SwiftUI

struct ContentView: View {
    @EnvironmentObject var c: ListenController
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    private var hero: (word: String, sub: String, head: String, advice: String) {
        if let v = c.verdict {
            return (v.orbWord, v.isWarming ? "Gathering speech" : "", v.headline, v.advice)
        }
        switch c.mode {
        case .offline: return ("Offline", "", "Not connected to your computer", "Doublespeak runs on your computer. The app opens, but the bridge on your computer has not connected yet.")
        case .idle: return ("Ready", "", "Waiting for a call", "Put the call on speakerphone, then tap Start listening.")
        case .listening: return ("Listening", "Gathering speech", "Listening", "Gathering the first few seconds before judging.")
        case .ended: return ("Stopped", "", "Listening stopped", "No verdict was reached. Start again when the call is on speakerphone.")
        }
    }

    var body: some View {
        ZStack {
            Theme.bg.ignoresSafeArea()
            ScrollView {
                VStack(spacing: 0) {
                    Header()
                    if let v = c.verdict, v.alert == "amber" {
                        Text(v.reasons.first ?? "Part of this call sounds risky. Do not share money, codes or passwords.")
                            .font(.ds(15, .regular, relativeTo: .subheadline))
                            .padding(14).frame(maxWidth: .infinity, alignment: .leading)
                            .background(Theme.amber.opacity(0.16), in: RoundedRectangle(cornerRadius: 16))
                            .overlay(RoundedRectangle(cornerRadius: 16).stroke(Theme.amber, lineWidth: 1))
                            .padding(.top, 8)
                            .accessibilityAddTraits(.isStaticText)
                    }
                    let h = hero
                    OrbView(tier: c.verdict?.tier ?? "unsure", lit: c.verdict?.litTicks ?? 0, word: h.word, sub: h.sub,
                            mode: c.mode, offline: c.mode == .offline)
                        .frame(width: c.mode == .offline ? 132 : 232)
                        .padding(.top, 8).padding(.bottom, 8)
                    Text(h.head)
                        .font(.ds(c.mode == .offline && c.verdict == nil ? 24 : 28, .light, relativeTo: .title))
                        .lineSpacing(-4)
                        .multilineTextAlignment(.center)
                        .foregroundStyle(Theme.ink)
                        .padding(.top, 6)
                        .accessibilityAddTraits(.isHeader)
                    Text(h.advice)
                        .font(.ds(16, .regular, relativeTo: .body))
                        .foregroundStyle(Theme.muted)
                        .multilineTextAlignment(.center)
                        .padding(.top, 10).padding(.horizontal, 6)

                    if let n = c.notice { NoticeCard(notice: n).padding(.top, 20) }
                    if c.mic == .denied && (c.mode == .idle || c.mode == .ended) { MicDeniedCard().padding(.top, 20) }
                    if c.mode == .offline { ConnectCard(full: true).padding(.top, 20) }
                    if c.mode == .idle && c.verdict == nil && c.mic != .denied { StepsCard().padding(.top, 20) }
                    if let v = c.verdict, !v.isWarming { ReadingSection(v: v).padding(.top, 20) }
                    if let f = c.listenerFailed { NoticeCard(notice: Notice(title: "The phone-side listener could not start", body: f)).padding(.top, 20) }

                    Text("Doublespeak can be wrong. It never speaks to the caller and never records.")
                        .font(.ds(13, .regular, relativeTo: .footnote))
                        .foregroundStyle(Theme.muted)
                        .multilineTextAlignment(.center)
                        .padding(.top, 28)
                }
                .padding(.horizontal, 20)
                .frame(maxWidth: 560)
                .frame(maxWidth: .infinity)
            }
            .scrollIndicators(.hidden)
            .safeAreaInset(edge: .bottom, spacing: 0) { Dock().frame(maxWidth: 560) }

            if c.showAlert, let v = c.verdict { AlertTakeover(v: v).transition(.opacity).zIndex(10) }
        }
        .animation(reduceMotion ? nil : .easeOut(duration: 0.25), value: c.showAlert)
        .sheet(item: $c.sheet) { s in
            switch s {
            case .consent: ConsentSheet().interactiveDismissDisabled()
            case .speaker: SpeakerSheet()
            case .connect: ConnectSheet()
            }
        }
        .task { c.boot() }
        .onReceive(NotificationCenter.default.publisher(for: UIApplication.willEnterForegroundNotification)) { _ in c.recheckMic() }
    }
}

struct Header: View {
    @EnvironmentObject var c: ListenController
    var body: some View {
        HStack {
            HStack(spacing: 10) {
                Image("Mark").resizable().scaledToFit().frame(height: 24).accessibilityHidden(true)
                Text("Doublespeak").font(.ds(19, .light, relativeTo: .title3)).foregroundStyle(Theme.ink)
            }
            .accessibilityElement(children: .combine)
            Spacer()
            Button { c.sheet = .connect } label: {
                HStack(spacing: 8) {
                    Circle().fill(c.mode == .offline ? Theme.amber : Theme.teal).frame(width: 8, height: 8)
                    Text(c.mode == .offline ? "Not connected" : "Your computer").font(.ds(14, .regular, relativeTo: .footnote))
                }
                .foregroundStyle(Theme.ink)
                .padding(.horizontal, 14).frame(minHeight: 44)
                .background(Theme.plane, in: Capsule())
            }
            .accessibilityLabel(c.mode == .offline ? "Not connected to your computer" : "Connected to your computer")
            .accessibilityHint("Shows how to connect")
        }
        .frame(minHeight: 60)
    }
}

struct StepsCard: View {
    @EnvironmentObject var c: ListenController
    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            step(1, "Put the call on speakerphone.", "iPhone gives apps no call audio. The microphone hears the speaker.")
            step(2, "Tap Start listening.", "Audio goes only to your computer, over the USB cable.")
            step(3, "Keep Doublespeak open.", "It keeps listening with the screen locked, but a call can interrupt the microphone.")
            Button("How speaker mode works") { c.sheet = .speaker }
                .font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted).underline()
                .frame(minHeight: 44)
        }
        .card()
    }
    private func step(_ n: Int, _ t: String, _ s: String) -> some View {
        HStack(alignment: .top, spacing: 12) {
            Text("\(n)").font(.ds(14, .medium, relativeTo: .footnote)).foregroundStyle(Theme.ink)
                .frame(width: 28, height: 28).background(Theme.plane2, in: Circle()).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(t).font(.ds(16, .medium, relativeTo: .body)).foregroundStyle(Theme.ink)
                Text(s).font(.ds(14, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted)
            }
        }
        .accessibilityElement(children: .combine)
    }
}

struct NoticeCard: View {
    var notice: Notice
    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(notice.title).font(.ds(20, .regular, relativeTo: .title3)).foregroundStyle(Theme.ink)
            Text(notice.body).font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted)
        }
        .card(border: Theme.amber)
        .accessibilityElement(children: .combine)
    }
}

struct MicDeniedCard: View {
    @EnvironmentObject var c: ListenController
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text("The microphone is off for Doublespeak").font(.ds(20, .regular, relativeTo: .title3)).foregroundStyle(Theme.ink)
            Text("Doublespeak hears the call through the microphone while it plays on speakerphone. Turn the microphone on in Settings, then come back.")
                .font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted)
            Button("Open Settings") { c.openSettings() }.buttonStyle(DSButtonStyle(kind: .ghost, height: 48)).padding(.top, 4)
        }
        .card(border: Theme.amber)
    }
}

extension View {
    func card(border: Color? = nil) -> some View {
        self.padding(20).frame(maxWidth: .infinity, alignment: .leading)
            .background(Theme.plane, in: RoundedRectangle(cornerRadius: 24, style: .continuous))
            .overlay { if let b = border { RoundedRectangle(cornerRadius: 24, style: .continuous).stroke(b, lineWidth: 1.5) } }
    }
}
