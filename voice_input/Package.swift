// swift-tools-version: 6.0

import PackageDescription

let package = Package(
    name: "voice_input",
    platforms: [
        .macOS(.v15)
    ],
    products: [
        .executable(name: "voice_input", targets: ["voice_input"])
    ],
    targets: [
        .executableTarget(
            name: "voice_input"
        ),
        .testTarget(
            name: "voice_inputTests",
            dependencies: ["voice_input"]
        ),
    ],
    swiftLanguageModes: [.v6]
)
