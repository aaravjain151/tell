import XCTest
import SwiftUI
@testable import Doublespeak

/// Renders the popover for each state to PNGs when DS_SNAPSHOT_DIR is set (skipped otherwise). A look-at-it aid, not an assertion.
@MainActor
final class SnapshotTests: XCTestCase {
    func testRenderPopovers() throws {
        guard let dir = ProcessInfo.processInfo.environment["DS_SNAPSHOT_DIR"] ?? UserDefaults(suiteName: "dev.doublespeak.app.mac.tests")?.string(forKey: "DS_SNAPSHOT_DIR") else {
            throw XCTSkip("DS_SNAPSHOT_DIR not set")
        }
        let cases: [(String, (inout Inputs) -> Void)] = [
            ("waiting", { _ in }),
            ("listening", { $0.live.apply(.verdict(tick: 3, stable: StableInfo(tier: "human", state: "steady", alert: .none), comboLabel: "Human voice, no scam pattern heard.")) }),
            ("amber", { $0.live.apply(.verdict(tick: 5, stable: StableInfo(tier: "scam", state: "escalated", alert: .amber), comboLabel: "AI voice and scam pattern in what was said.")) }),
            ("red", { $0.live.apply(.verdict(tick: 9, stable: StableInfo(tier: "scam", state: "latched", alert: .red), comboLabel: "AI voice and scam pattern in what was said.")) }),
            ("paused", { $0.pausedUntil = Date().addingTimeInterval(3000) }),
            ("problem", { $0.engine = .down; $0.engineGivenUp = true }),
            ("off", { $0.enabled = false }),
        ]
        for (name, mutate) in cases {
            let model = AppModel(launcher: FakeLauncher())
            var i = Inputs(); i.consentGiven = true; i.engine = .up
            mutate(&i)
            model.debugShow(i)
            let view = VStack(spacing: 10) {
                MenuBarIcon(model: model).font(.system(size: 17)).padding(8)
                MenuView(model: model, windows: WindowPresenter(model: model))
            }
            .padding(12)
            .background(Color(nsColor: .windowBackgroundColor))
            for scheme in [ColorScheme.light, .dark] {
                let r = ImageRenderer(content: view.environment(\.colorScheme, scheme))
                r.scale = 2
                guard let img = r.nsImage, let tiff = img.tiffRepresentation, let rep = NSBitmapImageRep(data: tiff),
                      let png = rep.representation(using: .png, properties: [:]) else { XCTFail("render \(name)"); continue }
                try png.write(to: URL(fileURLWithPath: dir).appendingPathComponent("popover-\(name)-\(scheme == .dark ? "dark" : "light").png"))
            }
        }
    }
}
