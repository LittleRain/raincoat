// swift-tools-version: 6.0
import PackageDescription

let package = Package(
    name: "RaincoatPrompt",
    platforms: [.macOS(.v14)],
    products: [
        .executable(name: "RaincoatPrompt", targets: ["RaincoatPrompt"])
    ],
    targets: [
        .target(name: "PromptCore", resources: [.copy("Resources/model-profiles.json"), .copy("Resources/scene-slots.json")]),
        .executableTarget(name: "RaincoatPrompt", dependencies: ["PromptCore"]),
        .testTarget(name: "PromptCoreTests", dependencies: ["PromptCore"])
    ]
)
