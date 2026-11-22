import PromptCore
import Testing

@Test func formatsAndValidatesARecordedShortcut() {
    let shortcut = LaunchShortcut(keyCode: 40, keyLabel: "K", modifiers: [.control, .option, .shift])
    #expect(shortcut.isValid)
    #expect(shortcut.label == "⌃⌥⇧K")
    #expect(!LaunchShortcut(keyCode: 40, keyLabel: "K", modifiers: [.shift]).isValid)
    #expect(!LaunchShortcut(keyCode: 36, keyLabel: "↵", modifiers: [.command]).isValid)
}

@Test func migratesPresetsAndPersistsCustomOrDisabledShortcuts() throws {
    #expect(LaunchShortcut.load(nil, legacyIndex: 0) == .standard)
    #expect(LaunchShortcut.load(nil, legacyIndex: 1)?.label == "⌃⌥P")
    #expect(LaunchShortcut.load(nil, legacyIndex: 2)?.label == "⇧⌘P")
    let shortcut = LaunchShortcut(keyCode: 40, keyLabel: "K", modifiers: [.control, .shift])
    let stored = try #require(LaunchShortcut.encodePreference(shortcut))
    #expect(LaunchShortcut.load(stored, legacyIndex: 0) == shortcut)
    let disabled = try #require(LaunchShortcut.encodePreference(nil))
    #expect(LaunchShortcut.load(disabled, legacyIndex: 1) == nil)
}

@Test func keepsTheOldBindingWhenRegistrationFails() {
    var binding = ShortcutRegistration<Int>()
    var released: [Int] = []
    let custom = LaunchShortcut(keyCode: 40, keyLabel: "K", modifiers: [.control, .option])
    let installed = binding.update(.standard, register: { _ in 1 }, unregister: { released.append($0) })
    let rejected = binding.update(custom, register: { _ in nil }, unregister: { released.append($0) })
    #expect(installed)
    #expect(!rejected)
    #expect(binding.shortcut == .standard)
    #expect(released.isEmpty)
    let replaced = binding.update(custom, register: { _ in 2 }, unregister: { released.append($0) })
    #expect(replaced)
    #expect(binding.shortcut == custom)
    #expect(released == [1])
    let disabled = binding.update(nil, register: { _ in nil }, unregister: { released.append($0) })
    #expect(disabled)
    #expect(binding.shortcut == nil)
    #expect(released == [1, 2])
}
