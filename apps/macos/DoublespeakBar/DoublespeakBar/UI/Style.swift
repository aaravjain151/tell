import SwiftUI

/// One identity: calm and instrument-like. Brand teal = the machine half (listening), brand red = flag.
/// State is never colour-only: every state also has its own symbol shape and its own words.
enum Palette {
    static let teal = Color(red: 0.094, green: 0.569, blue: 0.573)      // #189192
    static let amber = Color(red: 0.89, green: 0.58, blue: 0.0)         // readable on light and dark bars
    static let red = Color(red: 0.969, green: 0.235, blue: 0.275)       // #F73C45
}

extension DisplayState {
    var symbol: String {
        switch self {
        case .off: return "power.circle"
        case .waiting: return "ear"
        case .listening: return "waveform.circle.fill"
        case .amber: return "exclamationmark.triangle.fill"
        case .red: return "exclamationmark.octagon.fill"
        case .paused: return "pause.circle"
        case .engineProblem: return "wrench.and.screwdriver"
        }
    }

    var tint: Color? {
        switch self {
        case .listening: return Palette.teal
        case .amber: return Palette.amber
        case .red: return Palette.red
        case .engineProblem: return Palette.amber
        default: return nil
        }
    }

    var accessibilityName: String {
        switch self {
        case .off: return "Doublespeak is off"
        case .waiting: return "Doublespeak is waiting for a call"
        case .listening: return "Doublespeak is listening to a call"
        case .amber: return "Doublespeak: possible scam call"
        case .red: return "Doublespeak: likely scam call"
        case .paused: return "Doublespeak is paused"
        case .engineProblem: return "Doublespeak has an engine problem"
        }
    }
}

struct MenuRow: View {
    let title: String
    var systemImage: String?
    var role: ButtonRole?
    let action: () -> Void
    @State private var hover = false

    var body: some View {
        Button(role: role, action: action) {
            HStack(spacing: 10) {
                if let systemImage {
                    Image(systemName: systemImage).frame(width: 18).foregroundStyle(.secondary)
                }
                Text(title)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 10)
            .frame(height: 30)
            .contentShape(Rectangle())
            .background(RoundedRectangle(cornerRadius: 6, style: .continuous).fill(hover ? Color.primary.opacity(0.08) : .clear))
        }
        .buttonStyle(.plain)
        .onHover { hover = $0 }
    }
}
