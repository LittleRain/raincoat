import AppKit
import Carbon.HIToolbox
import CoreGraphics
import PromptCore

@MainActor
final class PromptApplication: NSObject, NSApplicationDelegate {
    private let panel = PromptPanelController()
    private let defaults = UserDefaults.standard
    private var statusItem: NSStatusItem?
    private var shortcutRegistration = ShortcutRegistration<EventHotKeyRef>()
    private var nextHotKeyID: UInt32 = 1
    private var eventHandler: EventHandlerRef?
    private var confirmation: Task<Void, Never>?
    private var settingShortcut = false

    private var savedShortcut: LaunchShortcut? {
        LaunchShortcut.load(defaults.data(forKey: "launchShortcut"), legacyIndex: defaults.integer(forKey: "shortcutIndex"))
    }

    func applicationDidFinishLaunching(_ notification: Notification) {
        let item = NSStatusBar.system.statusItem(withLength: NSStatusItem.squareLength)
        statusItem = item
        item.button?.image = NSImage(systemSymbolName: "text.quote", accessibilityDescription: "Raincoat Prompt")
        item.button?.toolTip = "Raincoat Prompt"
        panel.didCopy = { [weak self] in self?.showCopied() }
        panel.configureShortcut = { [weak self] in self?.showShortcutSettings() }

        var event = EventTypeSpec(eventClass: OSType(kEventClassKeyboard), eventKind: UInt32(kEventHotKeyPressed))
        _ = InstallEventHandler(
            GetApplicationEventTarget(),
            { _, _, context in
                guard let context else { return OSStatus(eventNotHandledErr) }
                let app = Unmanaged<PromptApplication>.fromOpaque(context).takeUnretainedValue()
                MainActor.assumeIsolated {
                    if app.shortcutRegistration.token != nil && !app.settingShortcut { app.showPanel() }
                }
                return noErr
            },
            1, &event, Unmanaged.passUnretained(self).toOpaque(), &eventHandler
        )
        applyShortcut(savedShortcut)
        refreshMenu()
        showPanel()
    }

    func applicationWillTerminate(_ notification: Notification) {
        if let hotKey = shortcutRegistration.token { UnregisterEventHotKey(hotKey) }
        if let eventHandler { RemoveEventHandler(eventHandler) }
    }

    @objc private func showPanel() { panel.show() }

    @objc private func showShortcutSettings() {
        guard !settingShortcut else { return }
        settingShortcut = true
        defer { settingShortcut = false }
        guard case .set(let selected) = ShortcutSettings.select(current: savedShortcut) else { return }
        if applyShortcut(selected) {
            defaults.set(LaunchShortcut.encodePreference(selected), forKey: "launchShortcut")
            refreshMenu()
        } else {
            let alert = NSAlert()
            alert.messageText = "无法启用 \(selected?.label ?? "快捷键")"
            alert.informativeText = shortcutRegistration.shortcut.map { "继续使用 \($0.label)。请试试其他组合。" }
                ?? "仍可从菜单栏打开，请试试其他组合。"
            alert.addButton(withTitle: "好")
            alert.runModal()
        }
    }

    @objc private func toggleCapture(_ sender: NSMenuItem) {
        let enabled = !UserDefaults.standard.bool(forKey: "screenRecognition")
        UserDefaults.standard.set(enabled, forKey: "screenRecognition")
        if enabled && !CGPreflightScreenCaptureAccess() {
            _ = CGRequestScreenCaptureAccess()
        }
        sender.state = enabled ? .on : .off
    }

    @discardableResult
    private func applyShortcut(_ shortcut: LaunchShortcut?) -> Bool {
        let handlerAvailable = eventHandler != nil
        let id = nextHotKeyID
        nextHotKeyID &+= 1
        return shortcutRegistration.update(shortcut, register: { candidate in
            guard handlerAvailable else { return nil }
            var modifiers: UInt32 = 0
            if candidate.modifiers.contains(.control) { modifiers |= UInt32(controlKey) }
            if candidate.modifiers.contains(.option) { modifiers |= UInt32(optionKey) }
            if candidate.modifiers.contains(.shift) { modifiers |= UInt32(shiftKey) }
            if candidate.modifiers.contains(.command) { modifiers |= UInt32(cmdKey) }
            var registered: EventHotKeyRef?
            let status = RegisterEventHotKey(
                UInt32(candidate.keyCode), modifiers, EventHotKeyID(signature: 0x524E4350, id: id),
                GetApplicationEventTarget(), UInt32(kEventHotKeyExclusive), &registered
            )
            return status == noErr ? registered : nil
        }, unregister: { _ = UnregisterEventHotKey($0) })
    }

    private func refreshMenu() {
        let shortcutLabel = shortcutRegistration.shortcut?.label
        panel.shortcutLabel = shortcutLabel
        let menu = NSMenu()
        let openTitle = shortcutLabel.map { "打开 Raincoat Prompt  \($0)" } ?? "打开 Raincoat Prompt"
        menu.addItem(makeItem(openTitle, #selector(showPanel)))
        menu.addItem(makeItem("设置唤起快捷键…", #selector(showShortcutSettings)))

        let capture = makeItem("截图识别目标模型", #selector(toggleCapture(_:)))
        capture.state = UserDefaults.standard.bool(forKey: "screenRecognition") ? .on : .off
        menu.addItem(capture)
        menu.addItem(.separator())
        let quit = NSMenuItem(title: "退出 Raincoat Prompt", action: #selector(NSApplication.terminate(_:)), keyEquivalent: "q")
        quit.target = NSApp
        menu.addItem(quit)
        statusItem?.menu = menu
    }

    private func makeItem(_ title: String, _ action: Selector) -> NSMenuItem {
        let item = NSMenuItem(title: title, action: action, keyEquivalent: "")
        item.target = self
        return item
    }

    private func showCopied() {
        confirmation?.cancel()
        statusItem?.button?.image = NSImage(systemSymbolName: "checkmark", accessibilityDescription: "已复制")
        statusItem?.button?.toolTip = "Prompt 已复制"
        confirmation = Task { [weak self] in
            try? await Task.sleep(for: .seconds(1.5))
            guard !Task.isCancelled, let self else { return }
            statusItem?.button?.image = NSImage(systemSymbolName: "text.quote", accessibilityDescription: "Raincoat Prompt")
            statusItem?.button?.toolTip = "Raincoat Prompt"
        }
    }
}
