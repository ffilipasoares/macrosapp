import SwiftUI
import FirebaseCore

@main
struct KitchenMacrosApp: App {
    init() {
        FirebaseApp.configure()
    }

    var body: some Scene {
        WindowGroup {
            ContentView()
                .task {
                    try? await AuthService.shared.signInIfNeeded()
                }
        }
    }
}
