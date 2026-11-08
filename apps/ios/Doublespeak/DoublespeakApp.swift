import SwiftUI

@main
struct DoublespeakApp: App {
    @StateObject private var controller = ListenController()
    var body: some Scene {
        WindowGroup {
            ContentView()
                .environmentObject(controller)
                .tint(Theme.teal)
        }
    }
}
