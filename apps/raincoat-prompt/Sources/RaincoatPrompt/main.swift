import AppKit
import PromptCore

let arguments = CommandLine.arguments
if arguments.dropFirst().first == "--v3-json" {
    guard arguments.count == 3 || arguments.count == 4,
          let target = AgentTarget(rawValue: arguments[2]) else { exit(64) }
    let input = String(decoding: FileHandle.standardInput.readDataToEndOfFile(), as: UTF8.self)
    let model = arguments.count == 4 ? arguments[3] : nil
    let draft = SlotComposer.bundled().compose(input, target: target, model: model)
    let encoder = JSONEncoder()
    encoder.outputFormatting = [.sortedKeys]
    if let data = try? encoder.encode(draft), let text = String(data: data, encoding: .utf8) {
        print(text)
    } else { exit(70) }
} else if arguments.dropFirst().first == "--v3-compose" {
    guard arguments.count == 3 || arguments.count == 4,
          let target = AgentTarget(rawValue: arguments[2]) else { exit(64) }
    let input = String(decoding: FileHandle.standardInput.readDataToEndOfFile(), as: UTF8.self)
    let model = arguments.count == 4 ? arguments[3] : nil
    print(SlotComposer.bundled().compose(input, target: target, model: model).text)
} else if arguments.count == 1 {
    let application = NSApplication.shared
    let delegate = PromptApplication()
    application.delegate = delegate
    application.setActivationPolicy(.accessory)
    application.run()
} else {
    FileHandle.standardError.write(Data("Usage: RaincoatPrompt [--v3-compose <target> [model] | --v3-json <target> [model]]\n".utf8))
    exit(64)
}
