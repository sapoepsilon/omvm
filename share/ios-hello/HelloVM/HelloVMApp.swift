import SwiftUI

@main
struct HelloVMApp: App {
    var body: some Scene {
        WindowGroup {
            VStack(spacing: 12) {
                Image(systemName: "desktopcomputer")
                    .font(.system(size: 64))
                Text("Hello from the omvm macOS VM")
                    .font(.title2)
            }
            .padding()
        }
    }
}
