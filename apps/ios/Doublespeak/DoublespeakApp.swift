import SwiftUI

@main
struct DoublespeakApp: App {
    @StateObject private var controller = ListenController()
    @StateObject private var blocker = BlockController()
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(controller)
                .environmentObject(blocker)
                .tint(Theme.teal)
        }
    }
}
