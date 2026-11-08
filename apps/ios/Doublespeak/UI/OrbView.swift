import SwiftUI

/// The orb: a disc inside a 48-tick ring. The ring lights up to the larger of the scam and AI-voice scores.
/// Status is never colour-only: the word in the middle, the ring count and the headline all say it.
struct OrbView: View {
    var tier: String
    var lit: Int
    var word: String
    var sub: String
    var mode: Mode
    var offline: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var breathe = false

    private var color: Color { mode == .listening || mode == .ended ? Theme.tier(tier) : Theme.unsure }

    var body: some View {
        ZStack {
            Canvas { ctx, size in
                let s = size.width / 240
                let c = CGPoint(x: size.width / 2, y: size.height / 2)
                // soft halo
                let halo = Path(ellipseIn: CGRect(x: c.x - 120 * s, y: c.y - 120 * s, width: 240 * s, height: 240 * s))
                ctx.fill(halo, with: .radialGradient(
                    Gradient(stops: [.init(color: color.opacity(offline || mode == .idle ? 0.10 : 0.30), location: 0.55),
                                     .init(color: color.opacity(0), location: 1)]),
                    center: c, startRadius: 0, endRadius: 120 * s))
                // disc
                let disc = Path(ellipseIn: CGRect(x: c.x - 82 * s, y: c.y - 82 * s, width: 164 * s, height: 164 * s))
                ctx.fill(disc, with: .color(Theme.plane))
                ctx.stroke(disc, with: .color(color), style: StrokeStyle(lineWidth: 1.5 * s, dash: offline ? [3 * s, 6 * s] : []))
                // ticks
                for i in 0..<VerdictView.ringTicks {
                    let a = (Double(i) / Double(VerdictView.ringTicks)) * 2 * .pi - .pi / 2
                    var p = Path()
                    p.move(to: CGPoint(x: c.x + cos(a) * 94 * s, y: c.y + sin(a) * 94 * s))
                    p.addLine(to: CGPoint(x: c.x + cos(a) * 108 * s, y: c.y + sin(a) * 108 * s))
                    ctx.stroke(p, with: .color(i < lit ? color : Theme.cellOff), style: StrokeStyle(lineWidth: 3.4 * s, lineCap: .butt))
                }
            }
            .scaleEffect(breathe ? 1.02 : 1)
            VStack(spacing: 2) {
                Text(word)
                    .font(.ds(offline ? 24 : 42, .extraLight, relativeTo: .largeTitle))
                    .foregroundStyle(Theme.ink)
                    .minimumScaleFactor(0.6).lineLimit(1)
                if !sub.isEmpty {
                    Text(sub).font(.ds(14, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted)
                }
            }
            .padding(.horizontal, 36)
        }
        .aspectRatio(1, contentMode: .fit)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Verdict gauge")
        .accessibilityValue("\(word). \(lit) of \(VerdictView.ringTicks) ring marks lit.")
        .onAppear {
            guard !reduceMotion else { return }
            withAnimation(.easeInOut(duration: 5).repeatForever(autoreverses: true)) { breathe = true }
        }
    }
}
