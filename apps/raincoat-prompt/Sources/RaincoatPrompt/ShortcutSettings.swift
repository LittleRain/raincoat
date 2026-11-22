import AppKit
import Carbon.HIToolbox
import PromptCore

@MainActor
enum ShortcutSettings {
    enum Selection {
        case cancelled
        case set(LaunchShortcut?)
    }

    static func select(current: LaunchShortcut?) -> Selection {
        let alert = NSAlert()
        alert.messageText = "设置唤起快捷键"
        alert.informativeText = "按下新的组合键，再点「保存」。停用后可从菜单栏打开。"
        let save = alert.addButton(withTitle: "保存")
        alert.addButton(withTitle: "取消").keyEquivalent = "\u{1B}"
        alert.addButton(withTitle: "恢复默认").keyEquivalent = ""
        alert.addButton(withTitle: "仅从菜单栏唤起").keyEquivalent = ""
        let recorder = ShortcutRecorder(current: current)
        alert.accessoryView = recorder
        save.isEnabled = current != nil
        recorder.didChange = { save.isEnabled = $0 != nil }
        alert.layout()
        alert.window.initialFirstResponder = recorder
        alert.window.makeFirstResponder(recorder)
        NSApp.activate()
        switch alert.runModal() {
        case .alertFirstButtonReturn:
            return recorder.value.map { .set($0) } ?? .cancelled
        case .alertThirdButtonReturn:
            return .set(.standard)
        case NSApplication.ModalResponse(rawValue: NSApplication.ModalResponse.alertThirdButtonReturn.rawValue + 1):
            return .set(nil)
        default:
            return .cancelled
        }
    }
}

@MainActor
private final class ShortcutRecorder: NSView {
    private let label = NSTextField(labelWithString: "")
    private let feedback = NSTextField(labelWithString: "")
    private(set) var value: LaunchShortcut?
    var didChange: ((LaunchShortcut?) -> Void)?

    init(current: LaunchShortcut?) {
        value = current
        super.init(frame: NSRect(x: 0, y: 0, width: 284, height: 58))
        let box = NSBox(frame: NSRect(x: 0, y: 20, width: 284, height: 38))
        box.boxType = .custom
        box.fillColor = .textBackgroundColor
        box.borderColor = .separatorColor
        box.cornerRadius = 6
        label.frame = NSRect(x: 8, y: 8, width: 266, height: 22)
        label.alignment = .center
        label.font = .systemFont(ofSize: 15, weight: .medium)
        box.addSubview(label)
        addSubview(box)
        feedback.frame = NSRect(x: 0, y: 0, width: 284, height: 17)
        feedback.font = .systemFont(ofSize: 11)
        feedback.textColor = .secondaryLabelColor
        addSubview(feedback)
        setAccessibilityElement(true)
        setAccessibilityRole(.textField)
        setAccessibilityLabel("唤起快捷键录入")
        update()
    }

    required init?(coder: NSCoder) { nil }
    override var acceptsFirstResponder: Bool { true }
    override func mouseDown(with event: NSEvent) { window?.makeFirstResponder(self) }

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        guard event.type == .keyDown, !event.modifierFlags.intersection([.control, .option, .command]).isEmpty else {
            return super.performKeyEquivalent(with: event)
        }
        record(event)
        return true
    }

    override func keyDown(with event: NSEvent) {
        if event.keyCode == kVK_Escape, event.modifierFlags.intersection([.control, .option, .command, .shift]).isEmpty {
            super.keyDown(with: event)
        } else {
            record(event)
        }
    }

    private func record(_ event: NSEvent) {
        guard !event.isARepeat else { return }
        var modifiers: LaunchShortcut.Modifiers = []
        if event.modifierFlags.contains(.control) { modifiers.insert(.control) }
        if event.modifierFlags.contains(.option) { modifiers.insert(.option) }
        if event.modifierFlags.contains(.shift) { modifiers.insert(.shift) }
        if event.modifierFlags.contains(.command) { modifiers.insert(.command) }
        let key = LaunchShortcut(keyCode: event.keyCode, keyLabel: Self.keyLabel(event), modifiers: modifiers)
        if key.isValid {
            value = key
            update()
            didChange?(key)
        } else {
            feedback.stringValue = key.label == "⌘↵" ? "⌘↵ 用于优化和复制，请换一组。" : "请同时按下 ⌃、⌥ 或 ⌘。"
        }
    }

    private func update() {
        label.stringValue = value?.label ?? "按下组合键"
        setAccessibilityValue(label.stringValue)
        feedback.stringValue = "可使用 ⌃、⌥、⇧、⌘ 与其他键组合"
    }

    private static func keyLabel(_ event: NSEvent) -> String {
        switch Int(event.keyCode) {
        case kVK_Space: return "Space"
        case kVK_Return, kVK_ANSI_KeypadEnter: return "↵"
        case kVK_Escape: return "Esc"
        case kVK_Tab: return "⇥"
        case kVK_Delete: return "⌫"
        case kVK_ForwardDelete: return "⌦"
        case kVK_LeftArrow: return "←"
        case kVK_RightArrow: return "→"
        case kVK_UpArrow: return "↑"
        case kVK_DownArrow: return "↓"
        default:
            let functionKeys = [kVK_F1, kVK_F2, kVK_F3, kVK_F4, kVK_F5, kVK_F6, kVK_F7, kVK_F8, kVK_F9, kVK_F10,
                                kVK_F11, kVK_F12, kVK_F13, kVK_F14, kVK_F15, kVK_F16, kVK_F17, kVK_F18, kVK_F19, kVK_F20]
            if let index = functionKeys.firstIndex(of: Int(event.keyCode)) { return "F\(index + 1)" }
            let characters = event.charactersIgnoringModifiers?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            return characters.isEmpty ? "键 \(event.keyCode)" : characters.uppercased()
        }
    }
}
