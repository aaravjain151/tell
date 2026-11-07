// swift-tools-version:5.9
import PackageDescription

// The Info.plist is embedded in the binary so macOS has an
// NSAudioCaptureUsageDescription for the permission prompt.
let package = Package(
    name: "tap_audio",
    platforms: [.macOS("14.4")],
    targets: [
        .executableTarget(
            name: "tap_audio",
            linkerSettings: [
                .unsafeFlags(["-Xlinker", "-sectcreate", "-Xlinker", "__TEXT",
                              "-Xlinker", "__info_plist", "-Xlinker", "Info.plist"])
            ]
        )
    ]
)
