import SwiftUI

/// 2x2 (voice x content), the three scores incl. the honest "How sure", reasons and the last words heard.
struct ReadingSection: View {
    var v: VerdictView
    @EnvironmentObject var c: ListenController

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            VStack(alignment: .leading, spacing: 16) {
                HStack(alignment: .center, spacing: 22) {
                    QuadGrid(v: v)
                    VStack(spacing: 12) {
                        ScoreRow(name: "Scam score", value: "\(v.scam)", fill: v.scam, tint: Theme.tier(v.tier))
                        ScoreRow(name: "AI-voice score", value: "\(v.aiVoice)", fill: v.aiVoice, tint: Theme.tier(v.tier))
                        ScoreRow(name: "How sure", value: v.howSure.rawValue, fill: v.confidencePct, tint: Theme.tier(v.tier))
                    }
                }
                if !v.howSureNote.isEmpty {
                    Text(v.howSureNote).font(.ds(14, .regular, relativeTo: .footnote)).foregroundStyle(Theme.ink)
                        .padding(.horizontal, 12).padding(.vertical, 8)
                        .background(Theme.plane2, in: RoundedRectangle(cornerRadius: 12))
                }
                Text(v.quadText).font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.ink)
                Text("Scores, not probabilities. How sure reflects how many checks agreed, not how often this is right.")
                    .font(.ds(12, .regular, relativeTo: .caption)).foregroundStyle(Theme.muted)
            }
            .card()
            .accessibilityElement(children: .combine)

            if !v.reasons.isEmpty {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(v.reasons, id: \.self) { r in
                        HStack(alignment: .firstTextBaseline, spacing: 10) {
                            Rectangle().fill(Theme.tier(v.tier)).frame(width: 6, height: 6).accessibilityHidden(true)
                            Text(r).font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.ink)
                        }
                    }
                }
                .padding(.top, 16).padding(.horizontal, 4)
            }

            VStack(alignment: .leading, spacing: 10) {
                HStack(alignment: .firstTextBaseline) {
                    Text("What was said").font(.ds(15, .medium, relativeTo: .subheadline)).foregroundStyle(Theme.ink)
                    Text("this screen only").font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted)
                }
                Transcript(text: v.transcript, ranges: v.markedRanges)
            }
            .padding(.top, 24)
        }
    }
}

struct QuadGrid: View {
    var v: VerdictView
    private let cells = ["human_ok", "human_scam", "ai_ok", "ai_scam"]
    var body: some View {
        HStack(spacing: 6) {
            VStack(spacing: 4) {
                Spacer().frame(height: 14)
                axis("Human"); axis("AI")
            }.frame(width: 38)
            VStack(spacing: 4) {
                HStack(spacing: 4) { axis("Not scam"); axis("Scam") }.frame(height: 14)
                LazyVGrid(columns: [GridItem(.fixed(42), spacing: 4), GridItem(.fixed(42), spacing: 4)], spacing: 4) {
                    ForEach(cells, id: \.self) { id in cell(id) }
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Voice and content grid. \(v.quadText)")
    }
    private func axis(_ s: String) -> some View {
        Text(s).font(.ds(10.5, .regular, relativeTo: .caption2)).foregroundStyle(Theme.muted)
            .lineLimit(1).minimumScaleFactor(0.7).frame(maxWidth: .infinity, maxHeight: .infinity)
    }
    @ViewBuilder private func cell(_ id: String) -> some View {
        let on = v.quadCell == id
        let maybe = v.quadMaybe.contains(id)
        RoundedRectangle(cornerRadius: 10, style: .continuous)
            .fill(on ? Theme.tier(v.tier) : (maybe ? Color.clear : Theme.cellOff))
            .overlay { if maybe { RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Theme.unsure, style: StrokeStyle(lineWidth: 1.5, dash: [3, 3])) } }
            .overlay { if on { RoundedRectangle(cornerRadius: 10, style: .continuous).stroke(Theme.tier(v.tier).opacity(0.25), lineWidth: 3).padding(-3) } }
            .frame(width: 42, height: 42)
    }
}

struct ScoreRow: View {
    var name: String, value: String, fill: Int, tint: Color
    var body: some View {
        VStack(spacing: 4) {
            HStack(alignment: .firstTextBaseline) {
                Text(name).font(.ds(13, .regular, relativeTo: .footnote)).foregroundStyle(Theme.muted)
                Spacer(minLength: 4)
                Text(value).font(.ds(17, .medium, relativeTo: .body)).foregroundStyle(Theme.ink).monospacedDigit()
            }
            HStack(spacing: 2) {
                let on = Int((Double(fill) / 100 * 20).rounded())
                ForEach(0..<20, id: \.self) { i in
                    Rectangle().fill(i < on ? tint : Theme.cellOff).frame(height: 6)
                }
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(name): \(value)")
    }
}

struct Transcript: View {
    var text: String
    var ranges: [Range<Int>]
    private var attributed: AttributedString {
        var a = AttributedString(text)
        let chars = Array(text)
        for r in ranges where r.upperBound <= chars.count {
            let s = text.index(text.startIndex, offsetBy: r.lowerBound), e = text.index(text.startIndex, offsetBy: r.upperBound)
            if let lo = AttributedString.Index(s, within: a), let hi = AttributedString.Index(e, within: a) {
                a[lo..<hi].backgroundColor = UIColor(Theme.red).withAlphaComponent(0.22)
                a[lo..<hi].underlineStyle = .single
                a[lo..<hi].underlineColor = UIColor(Theme.red)
            }
        }
        return a
    }
    var body: some View {
        Group {
            if text.isEmpty {
                Text("Nothing clear enough to show yet.").font(.ds(15, .regular, relativeTo: .subheadline)).foregroundStyle(Theme.muted)
            } else {
                Text(attributed).font(.system(.body, design: .serif)).lineSpacing(5).foregroundStyle(Theme.ink)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 14).frame(maxWidth: .infinity, alignment: .leading)
        .background(Theme.plane, in: RoundedRectangle(cornerRadius: 18, style: .continuous))
    }
}
