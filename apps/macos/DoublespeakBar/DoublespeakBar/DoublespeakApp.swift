import SwiftUI

@MainActor
final class AppDelegate: NSObject, NSApplicationDelegate {
    let model = AppModel()
    lazy var windows = WindowPresenter(model: model)

    func applicationDidFinishLaunching(_ notification: Notification) {
        model.launch()
        if model.needsOnboarding { windows.showWelcome() }
    }

    func applicationWillTerminate(_ notification: Notification) {
        model.stopForQuit()
    }
}

@main
struct DoublespeakApp: App {
    @NSApplicationDelegateAdaptor(AppDelegate.self) private var delegate

    var body: some Scene {
        // isInserted is pinned to true and no menu item hides the icon: while a call is listened to, the icon stays.
        MenuBarExtra(isInserted: .constant(true)) {
            MenuView(model: delegate.model, windows: delegate.windows)
        } label: {
            MenuBarIcon(model: delegate.model)
        }
        .menuBarExtraStyle(.window)
    }
}
