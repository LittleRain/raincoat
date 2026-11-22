import Foundation

public struct LaunchShortcut: Codable, Equatable, Sendable {
    public struct Modifiers: OptionSet, Codable, Sendable {
        public let rawValue: UInt8
        public init(rawValue: UInt8) { self.rawValue = rawValue }
        public static let control = Self(rawValue: 1)
        public static let option = Self(rawValue: 2)
        public static let shift = Self(rawValue: 4)
        public static let command = Self(rawValue: 8)
    }

    public let keyCode: UInt16
    public let keyLabel: String
    public let modifiers: Modifiers

    public init(keyCode: UInt16, keyLabel: String, modifiers: Modifiers) {
        self.keyCode = keyCode
        self.keyLabel = keyLabel
        self.modifiers = modifiers
    }

    // macOS virtual key codes also used by the original preset picker.
    public static let standard = LaunchShortcut(keyCode: 49, keyLabel: "Space", modifiers: [.control, .option])
    public var label: String {
        [(Modifiers.control, "⌃"), (.option, "⌥"), (.shift, "⇧"), (.command, "⌘")]
            .filter { modifiers.contains($0.0) }.map(\.1).joined() + keyLabel
    }

    public var isValid: Bool {
        let supported: Modifiers = [.control, .option, .shift, .command]
        guard keyCode <= 127, !keyLabel.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty,
              !modifiers.intersection([.control, .option, .command]).isEmpty,
              modifiers.subtracting(supported).isEmpty
        else { return false }
        return !([36, 76].contains(keyCode) && modifiers == .command)
    }

    public static func load(_ stored: Data?, legacyIndex: Int) -> LaunchShortcut? {
        if let stored {
            do {
                let decoded = try JSONDecoder().decode(LaunchShortcut?.self, from: stored)
                return decoded?.isValid == false ? standard : decoded
            } catch {
                return standard
            }
        }
        switch legacyIndex {
        case 1: return LaunchShortcut(keyCode: 35, keyLabel: "P", modifiers: [.control, .option])
        case 2: return LaunchShortcut(keyCode: 35, keyLabel: "P", modifiers: [.command, .shift])
        default: return standard
        }
    }

    public static func encodePreference(_ value: LaunchShortcut?) -> Data? {
        try? JSONEncoder().encode(value)
    }
}

public struct ShortcutRegistration<Token> {
    public private(set) var shortcut: LaunchShortcut?
    public private(set) var token: Token?

    public init() {}

    @discardableResult
    public mutating func update(
        _ newShortcut: LaunchShortcut?,
        register: (LaunchShortcut) -> Token?,
        unregister: (Token) -> Void
    ) -> Bool {
        var replacement: Token?
        if let newShortcut {
            guard newShortcut.isValid else { return false }
            if newShortcut.keyCode == shortcut?.keyCode, newShortcut.modifiers == shortcut?.modifiers {
                shortcut = newShortcut
                return true
            }
            guard let registered = register(newShortcut) else { return false }
            replacement = registered
        }
        if let token { unregister(token) }
        shortcut = newShortcut
        token = replacement
        return true
    }
}
