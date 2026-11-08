import SwiftUI
import UIKit

/// Tokens match apps/android/app.css, apps/web and design/tokens.json: navy ink, teal = the machine half, red = flag.
enum Theme {
    private static func dyn(_ light: UInt32, _ dark: UInt32) -> Color {
        Color(UIColor { $0.userInterfaceStyle == .dark ? UIColor(hex: dark) : UIColor(hex: light) })
    }
    static let bg = dyn(0xFFFFFF, 0x0B1020)
    static let ink = dyn(0x141D44, 0xF1F3FA)
    static let muted = dyn(0x5C6482, 0x9AA3C0)
    static let line = dyn(0xE3E6EF, 0x1F2745)
    static let plane = dyn(0xF3F5F9, 0x111833)
    static let plane2 = dyn(0xE9ECF4, 0x182148)
    static let teal = dyn(0x189192, 0x2BB5B6)
    static let red = dyn(0xF73C45, 0xFF5A63)
    static let amber = dyn(0xB7790B, 0xF2B632)
    static let blue = dyn(0x3A55C8, 0x8C9BFF)
    static let unsure = dyn(0x8A92AD, 0x6B7491)
    static let cellOff = dyn(0xDDE1EC, 0x1D2647)
    static let alertBg = dyn(0xC81D28, 0xFF5A63)
    static let alertFg = dyn(0xFFFFFF, 0x0B1020)
    static let primary = dyn(0x141D44, 0x2BB5B6)
    static let onPrimary = dyn(0xFFFFFF, 0x0B1020)

    static func tier(_ t: String) -> Color {
        switch t {
        case "human": return teal
        case "ai_disclosed": return blue
        case "ai_undisclosed": return amber
        case "scam": return red
        default: return unsure
        }
    }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(red: CGFloat((hex >> 16) & 255) / 255, green: CGFloat((hex >> 8) & 255) / 255, blue: CGFloat(hex & 255) / 255, alpha: 1)
    }
}

enum DSWeight { case extraLight, light, regular, medium
    var name: String {
        switch self { case .extraLight: return "Outfit-ExtraLight"; case .light: return "Outfit-Light"
        case .regular: return "Outfit-Regular"; case .medium: return "Outfit-Medium" }
    }
}

extension Font {
    /// Outfit (OFL, bundled, no network). Scales with Dynamic Type relative to a text style.
    static func ds(_ size: CGFloat, _ w: DSWeight = .regular, relativeTo style: Font.TextStyle = .body) -> Font {
        .custom(w.name, size: size, relativeTo: style)
    }
}

/// Two shapes of button, both at least 48 pt tall.
struct DSButtonStyle: ButtonStyle {
    enum Kind { case primary, ghost, stop, alert }
    var kind: Kind = .primary
    var height: CGFloat = 56
    func makeBody(configuration: Configuration) -> some View {
        let bg: Color, fg: Color
        switch kind {
        case .primary: bg = Theme.primary; fg = Theme.onPrimary
        case .ghost: bg = Theme.plane2; fg = Theme.ink
        case .stop: bg = Theme.ink; fg = Theme.bg
        case .alert: bg = Theme.alertFg; fg = Theme.alertBg
        }
        return configuration.label
            .font(.ds(18, .medium, relativeTo: .headline))
            .foregroundStyle(fg)
            .frame(maxWidth: .infinity, minHeight: height)
            .background(bg, in: Capsule())
            .scaleEffect(configuration.isPressed ? 0.98 : 1)
            .contentShape(Capsule())
    }
}
