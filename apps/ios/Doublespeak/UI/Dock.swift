import SwiftUI

/// The primary action lives in the thumb zone. Three states: start, listening (timer, level meter, big Stop), stopped.
struct Dock: View {
    @EnvironmentObject var c: ListenController

    var body: some View {
        VStack(spacing: 10) {
            switch c.mode {
            case .listening: listening
            case .ended: ended
            default: idle
            }
        }
        .padding(.horizontal, 20).padding(.top, 12).padding(.bottom, 8)
        .frame(maxWidth: .infinity)
        .background(Theme.bg.ignoresSafeArea(edges: .bottom))
        .overlay(alignment: .top) { Rectangle().fill(Theme.line).frame(height: 1) }
    }

    private var idle: some View {
        VStack(spacing: 10) {
            Button { c.startTapped() } label: {
                HStack(spacing: 10) {
                    Image(systemName: "mic").font(.system(size: 20, weight: .regular))
                    Text(c.mode == .offline ? "Connect to your computer first" : c.callActive ? "Unavailable during a call" : "Start listening")
                }
            }
            .buttonStyle(DSButtonStyle(kind: .primary, height: 64))
            .disabled(c.mode == .offline || c.callActive)
            .opacity(c.mode == .offline || c.callActive ? 0.45 : 1)
            Text(c.mode == .offline ? "Run the command above, then this turns on." : c.callActive ? "Starts again when the call ends." : "Speaker mode. The call has to play out loud near this phone.")
                .font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted).multilineTextAlignment(.center)
        }
    }

    private var listening: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(spacing: 14) {
                RecDot()
                VStack(alignment: .leading, spacing: 1) {
                    Text(c.callBanner == .interrupted ? "Microphone interrupted" : "Listening").font(.ds(18, .medium, relativeTo: .headline)).foregroundStyle(Theme.ink)
                    Text("\(clockString(c.elapsed)) · speaker mode").font(.ds(13, .regular, relativeTo: .footnote))
                        .foregroundStyle(Theme.muted).monospacedDigit()
                }
                Spacer()
                Button("Stop") { c.stopTapped() }
                    .buttonStyle(DSButtonStyle(kind: .stop, height: 56)).frame(width: 112)
                    .accessibilityHint("Stops listening and clears the audio buffer")
            }
            HStack(spacing: 3) {
                ForEach(0..<c.levels.count, id: \.self) { i in
                    Rectangle().fill(c.levels[i] > 0.12 ? Theme.teal : Theme.cellOff).frame(height: 8)
                }
            }
            .padding(.trailing, 6)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("Microphone level")
            .accessibilityValue(c.micFlat ? "No sound" : "Receiving sound")
            if c.callBanner == .interrupted {
                Text(CallBanner.interrupted.title + ". " + CallBanner.interrupted.body)
                    .font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.ink)
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .background(Theme.amber.opacity(0.18), in: RoundedRectangle(cornerRadius: 12))
            } else if c.micFlat {
                Text("No sound is reaching the microphone. Is the call playing out loud near this phone?")
                    .font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.ink)
                    .padding(.horizontal, 12).padding(.vertical, 8)
                    .background(Theme.amber.opacity(0.18), in: RoundedRectangle(cornerRadius: 12))
            } else {
                Text("Audio goes only to your computer over USB. Nothing is saved.")
                    .font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted)
            }
        }
        .padding(.leading, 20).padding(.trailing, 14).padding(.vertical, 14)
        .background(Theme.plane, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 28, style: .continuous).stroke(Theme.tier(c.verdict?.tier ?? "unsure"), lineWidth: 1.5))
    }

    private var ended: some View {
        VStack(spacing: 10) {
            HStack {
                VStack(alignment: .leading, spacing: 1) {
                    Text("Listening stopped").font(.ds(17, .medium, relativeTo: .headline)).foregroundStyle(Theme.ink)
                    Text("Nothing was saved.").font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted)
                }
                Spacer()
                Button("Clear screen") { c.clearScreen() }.buttonStyle(DSButtonStyle(kind: .ghost, height: 44)).frame(width: 140)
            }
            Button("Start again") { c.startTapped() }.buttonStyle(DSButtonStyle(kind: .primary, height: 56))
        }
        .padding(14)
        .background(Theme.plane, in: RoundedRectangle(cornerRadius: 28, style: .continuous))
    }
}

struct RecDot: View {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var dim = false
    var body: some View {
        Circle().fill(Theme.red).frame(width: 12, height: 12).opacity(dim ? 0.25 : 1)
            .accessibilityHidden(true)
            .onAppear { guard !reduceMotion else { return }
                withAnimation(.easeInOut(duration: 0.8).repeatForever(autoreverses: true)) { dim = true } }
    }
}
