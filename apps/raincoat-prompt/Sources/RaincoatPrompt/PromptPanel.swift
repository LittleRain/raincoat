import AppKit
import PromptCore

@MainActor
private final class EditorPanel: NSPanel {
    override var canBecomeKey: Bool { true }
}

@MainActor
private final class PromptEditor: NSTextView {
    var submit: (() -> Void)?
    var dismiss: (() -> Void)?

    override func performKeyEquivalent(with event: NSEvent) -> Bool {
        let modifiers = event.modifierFlags.intersection([.command, .option, .control, .shift])
        if !hasMarkedText() {
            if modifiers == .command {
                if [36, 76].contains(event.keyCode) {
                    submit?()
                    return true
                }
                // An accessory application has no system Edit menu to route these shortcuts.
                switch event.charactersIgnoringModifiers?.lowercased() {
                case "a": selectAll(nil)
                case "c": copy(nil)
                case "q": NSApp.terminate(nil)
                case "x": cut(nil)
                case "v": paste(nil)
                case "w": dismiss?()
                case "z": undoManager?.undo()
                default: return super.performKeyEquivalent(with: event)
                }
                return true
            }
            if modifiers == [.command, .shift], event.charactersIgnoringModifiers?.lowercased() == "z" {
                undoManager?.redo()
                return true
            }
        }
        return super.performKeyEquivalent(with: event)
    }

    override func cancelOperation(_ sender: Any?) {
        if hasMarkedText() {
            super.cancelOperation(sender)
        } else {
            dismiss?()
        }
    }
}

@MainActor
final class PromptPanelController: NSObject, NSTextViewDelegate, NSWindowDelegate {
    private let panel = EditorPanel(
        contentRect: NSRect(x: 0, y: 0, width: 638, height: 385),
        styleMask: [.titled, .closable], backing: .buffered, defer: true
    )
    private let heading = NSTextField(labelWithString: "Raincoat Prompt")
    private let contextLabel = NSTextField(labelWithString: "")
    private let provenance = NSTextField(labelWithString: "")
    private let placeholder = NSTextField(labelWithString: "例如，分析最近两周的退货率，找出主要变化。")
    private let editor = PromptEditor()
    private let scenePicker = NSPopUpButton()
    private let targetPicker = NSPopUpButton()
    private let modelPicker = NSPopUpButton()
    private let submitButton = NSButton(title: "优化 Prompt", target: nil, action: nil)
    private let backButton = NSButton(title: "返回修改", target: nil, action: nil)
    private let shortcutSettingsButton = NSButton(title: "唤起设置…", target: nil, action: nil)
    private let overrideField = NSTextField()
    private let overrideRow = NSStackView()

    private let defaults = UserDefaults.standard
    private var sourceApp: NSRunningApplication?
    private var windowTarget: AgentTarget?
    private var detectedModel: String?
    private var sceneOverride: String?
    private let slotComposer = SlotComposer.bundled()
    private var targetOverride: AgentTarget?
    private var modelOverride: String?
    private var original = ""
    private var preview: SlotDraft?
    private var captureTask: Task<Void, Never>?
    private var classificationTask: Task<Void, Never>?

    var shortcutLabel: String? {
        didSet { refresh() }
    }
    var didCopy: (() -> Void)?
    var configureShortcut: (() -> Void)?

    private var recentTarget: AgentTarget? {
        let date = defaults.double(forKey: "recentTargetTime")
        guard Date.now.timeIntervalSince1970 - date < 30 * 24 * 3600 else { return nil }
        return defaults.string(forKey: "recentTarget").flatMap(AgentTarget.init(rawValue:))
    }

    private var target: AgentTarget {
        targetOverride ?? AgentTarget.explicit(in: original) ?? windowTarget ?? recentTarget ?? .general
    }

    private var model: String? {
        if let modelOverride { return modelOverride.isEmpty ? nil : modelOverride }
        guard target == windowTarget else { return nil }
        return detectedModel
    }

    override init() {
        super.init()
        configurePanel()
        refresh()
    }

    func show() {
        if panel.isVisible && panel.isKeyWindow {
            hide()
            return
        }

        let activeApp = NSWorkspace.shared.frontmostApplication
        if activeApp?.processIdentifier != ProcessInfo.processInfo.processIdentifier {
            sourceApp = activeApp
        }
        let observation = WindowObservation.observe(sourceApp)
        captureTask?.cancel()
        if preview == nil {
            windowTarget = observation.target
            detectedModel = nil
        }

        refresh()
        if let screen = NSScreen.screens.first(where: { $0.frame.contains(NSEvent.mouseLocation) }) ?? NSScreen.main {
            let frame = screen.visibleFrame
            panel.setFrameOrigin(NSPoint(x: frame.midX - panel.frame.width / 2, y: frame.midY - panel.frame.height / 2 + 36))
        } else {
            panel.center()
        }
        NSApp.activate()
        panel.makeKeyAndOrderFront(nil)
        panel.makeFirstResponder(editor)

        guard preview == nil, windowTarget != nil, let windowID = observation.windowID,
              defaults.bool(forKey: "screenRecognition")
        else { return }
        captureTask = Task { [weak self] in
            let recognition = Task.detached(priority: .utility) { try? await WindowModelRecognition.detect(windowID: windowID) }
            let label = await withTaskCancellationHandler {
                await recognition.value
            } onCancel: {
                recognition.cancel()
            }
            guard !Task.isCancelled, let self, panel.isVisible, preview == nil else { return }
            detectedModel = label
            refresh()
        }
    }

    private func hide() {
        captureTask?.cancel()
        classificationTask?.cancel()
        panel.orderOut(nil)
        if let sourceApp, !sourceApp.isTerminated { sourceApp.activate() }
    }

    func windowShouldClose(_ sender: NSWindow) -> Bool {
        hide()
        return false
    }

    private func configurePanel() {
        panel.delegate = self
        panel.title = "Raincoat Prompt"
        panel.titleVisibility = .hidden
        panel.titlebarAppearsTransparent = true
        panel.level = .floating
        panel.collectionBehavior = [.moveToActiveSpace, .fullScreenAuxiliary]
        panel.isReleasedWhenClosed = false
        panel.hidesOnDeactivate = true
        panel.isMovableByWindowBackground = true

        heading.font = .systemFont(ofSize: 23, weight: .semibold)
        contextLabel.font = .monospacedSystemFont(ofSize: 11, weight: .regular)
        contextLabel.textColor = .secondaryLabelColor
        provenance.font = .systemFont(ofSize: 12)
        provenance.textColor = .secondaryLabelColor
        placeholder.font = .systemFont(ofSize: 16)
        placeholder.textColor = .placeholderTextColor

        scenePicker.addItems(withTitles: ["自动"] + slotComposer.scenes.scenes.map(\.label))
        targetPicker.addItems(withTitles: ["自动"] + AgentTarget.allCases.map(\.title))
        modelPicker.addItems(withTitles: ["自动", "通用写法", "上次使用"] + ModelLabel.known)
        modelPicker.menu?.autoenablesItems = false
        configurePicker(scenePicker, "场景", #selector(sceneChanged))
        configurePicker(targetPicker, "发送到", #selector(targetChanged))
        configurePicker(modelPicker, "目标模型", #selector(modelChanged))

        let toolbar = NSStackView(views: [targetPicker, modelPicker, scenePicker])
        toolbar.spacing = 7
        let header = NSStackView(views: [heading, NSView(), contextLabel])
        header.alignment = .firstBaseline

        let scroll = NSScrollView()
        scroll.borderType = .bezelBorder
        scroll.hasVerticalScroller = true
        scroll.documentView = editor
        editor.backgroundColor = .textBackgroundColor
        editor.textColor = .textColor
        editor.font = .systemFont(ofSize: 16)
        editor.isRichText = false
        editor.importsGraphics = false
        editor.isAutomaticQuoteSubstitutionEnabled = false
        editor.isAutomaticDashSubstitutionEnabled = false
        editor.isAutomaticTextReplacementEnabled = false
        editor.allowsUndo = true
        editor.isHorizontallyResizable = false
        editor.isVerticallyResizable = true
        editor.maxSize = NSSize(width: CGFloat.greatestFiniteMagnitude, height: CGFloat.greatestFiniteMagnitude)
        editor.autoresizingMask = [.width]
        editor.textContainer?.widthTracksTextView = true
        editor.textContainerInset = NSSize(width: 14, height: 13)
        editor.delegate = self
        editor.submit = { [weak self] in self?.submit() }
        editor.dismiss = { [weak self] in self?.hide() }
        editor.setAccessibilityLabel("Prompt")

        let editorArea = NSView()
        for view in [scroll, placeholder] as [NSView] {
            view.translatesAutoresizingMaskIntoConstraints = false
            editorArea.addSubview(view)
        }
        NSLayoutConstraint.activate([
            scroll.topAnchor.constraint(equalTo: editorArea.topAnchor),
            scroll.bottomAnchor.constraint(equalTo: editorArea.bottomAnchor),
            scroll.leadingAnchor.constraint(equalTo: editorArea.leadingAnchor),
            scroll.trailingAnchor.constraint(equalTo: editorArea.trailingAnchor),
            placeholder.topAnchor.constraint(equalTo: editorArea.topAnchor, constant: 16),
            placeholder.leadingAnchor.constraint(equalTo: editorArea.leadingAnchor, constant: 20),
            placeholder.trailingAnchor.constraint(lessThanOrEqualTo: editorArea.trailingAnchor, constant: -20)
        ])

        submitButton.bezelStyle = .rounded
        submitButton.contentTintColor = NSColor(name: nil) { appearance in
            appearance.bestMatch(from: [.aqua, .darkAqua]) == .darkAqua
                ? NSColor(srgbRed: 0.39, green: 0.85, blue: 0.73, alpha: 1)
                : NSColor(srgbRed: 0.05, green: 0.39, blue: 0.34, alpha: 1)
        }
        submitButton.target = self
        submitButton.action = #selector(submit)
        submitButton.toolTip = "⌘↵"
        backButton.target = self
        backButton.action = #selector(backToInput)
        shortcutSettingsButton.target = self
        shortcutSettingsButton.action = #selector(showShortcutSettings)
        overrideField.placeholderString = "材料=…；验收=…"
        overrideField.font = .systemFont(ofSize: 12)
        overrideField.setAccessibilityLabel("补充槽位")
        let overrideLabel = NSTextField(labelWithString: "补充")
        overrideLabel.font = .systemFont(ofSize: 12)
        overrideLabel.textColor = .secondaryLabelColor
        overrideRow.setViews([overrideLabel, overrideField], in: .leading)
        overrideRow.spacing = 8
        overrideRow.isHidden = true
        let footer = NSStackView(views: [provenance, NSView(), shortcutSettingsButton, backButton, submitButton])
        footer.alignment = .centerY
        footer.spacing = 8

        let body = NSStackView(views: [header, toolbar, editorArea, overrideRow, footer])
        body.orientation = .vertical
        body.alignment = .leading
        body.spacing = 13
        body.translatesAutoresizingMaskIntoConstraints = false
        let container = NSView()
        panel.contentView = container
        container.addSubview(body)
        NSLayoutConstraint.activate([
            body.topAnchor.constraint(equalTo: container.topAnchor, constant: 22),
            body.bottomAnchor.constraint(equalTo: container.bottomAnchor, constant: -19),
            body.leadingAnchor.constraint(equalTo: container.leadingAnchor, constant: 23),
            body.trailingAnchor.constraint(equalTo: container.trailingAnchor, constant: -23),
            header.widthAnchor.constraint(equalTo: body.widthAnchor),
            editorArea.widthAnchor.constraint(equalTo: body.widthAnchor),
            editorArea.heightAnchor.constraint(greaterThanOrEqualToConstant: 150),
            overrideRow.widthAnchor.constraint(equalTo: body.widthAnchor),
            footer.widthAnchor.constraint(equalTo: body.widthAnchor)
        ])
    }

    private func configurePicker(_ picker: NSPopUpButton, _ label: String, _ action: Selector) {
        picker.controlSize = .small
        picker.setAccessibilityLabel(label)
        picker.toolTip = label
        picker.target = self
        picker.action = action
    }

    private func refresh() {
        let isPreview = preview != nil
        let autoScene = slotComposer.scene(for: original)
        scenePicker.item(at: 0)?.title = "自动 · \(autoScene.label)"
        targetPicker.item(at: 0)?.title = "自动 · \(target.title)"
        let automaticModel = modelOverride == nil ? model : nil
        modelPicker.item(at: 0)?.title = automaticModel.map { "自动 · \($0)" } ?? "模型 · 自动"
        let priorModel = defaults.string(forKey: "model-\(target.rawValue)")
        modelPicker.item(at: 2)?.title = priorModel.map { "上次 · \($0)" } ?? "无上次模型"
        modelPicker.item(at: 2)?.isEnabled = priorModel != nil
        if let modelOverride {
            modelPicker.selectItem(at: ModelLabel.known.firstIndex(of: modelOverride).map { $0 + 3 } ?? (modelOverride.isEmpty ? 1 : 2))
        } else {
            modelPicker.selectItem(at: 0)
        }
        for picker in [scenePicker, targetPicker, modelPicker] { picker.isEnabled = !isPreview }

        if let preview {
            heading.stringValue = preview.addedSentences == 0 ? "Prompt 预览" : "优化后的 Prompt"
        } else {
            heading.stringValue = "Raincoat Prompt"
        }
        contextLabel.stringValue = isPreview ? "⌘↵ 复制" : "⌘↵ 优化"
        let hasText = !editor.string.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        placeholder.isHidden = isPreview || !editor.string.isEmpty
        submitButton.title = isPreview ? "复制并关闭" : "优化 Prompt"
        submitButton.isEnabled = hasText
        backButton.isHidden = !isPreview
        shortcutSettingsButton.isHidden = isPreview
        if let preview {
            var note = preview.addedSentences == 0
                ? "原文已保留"
                : "\(preview.profile) · \(preview.scene) · 补充 \(preview.addedSentences) 句"
            if !preview.missing.isEmpty {
                note += " · 待补充：" + preview.missing.joined(separator: "、") + "（已用默认）"
            }
            provenance.stringValue = note
            overrideRow.isHidden = preview.missing.isEmpty
            if !preview.missing.isEmpty, overrideField.stringValue.isEmpty {
                overrideField.stringValue = preview.questions
                    .map { "\(slotLabel($0.slot))=\($0.defaultValue)" }
                    .joined(separator: "；")
            }
        } else if targetOverride != nil || AgentTarget.explicit(in: original) != nil {
            provenance.stringValue = "已指定目标"
        } else if windowTarget != nil {
            provenance.stringValue = "当前窗口"
        } else if recentTarget != nil {
            provenance.stringValue = "上次使用"
        } else {
            provenance.stringValue = shortcutLabel.map { "\($0) 唤起" } ?? "菜单栏唤起"
        }
    }

    @objc private func showShortcutSettings() {
        configureShortcut?()
        panel.makeFirstResponder(editor)
    }

    func textDidChange(_ notification: Notification) {
        guard !editor.hasMarkedText() else { return }
        placeholder.isHidden = preview != nil || !editor.string.isEmpty
        submitButton.isEnabled = !editor.string.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty
        guard preview == nil else { return }
        original = editor.string
        classificationTask?.cancel()
        classificationTask = Task { [weak self] in
            try? await Task.sleep(for: .milliseconds(300))
            guard !Task.isCancelled, let self, !editor.hasMarkedText() else { return }
            refresh()
        }
    }

    @objc private func sceneChanged() {
        let index = scenePicker.indexOfSelectedItem - 1
        sceneOverride = slotComposer.scenes.scenes.indices.contains(index) ? slotComposer.scenes.scenes[index].id : nil
        panel.makeFirstResponder(editor)
        refresh()
    }

    @objc private func targetChanged() {
        let index = targetPicker.indexOfSelectedItem - 1
        targetOverride = AgentTarget.allCases.indices.contains(index) ? AgentTarget.allCases[index] : nil
        modelOverride = nil
        panel.makeFirstResponder(editor)
        refresh()
    }

    @objc private func modelChanged() {
        switch modelPicker.indexOfSelectedItem {
        case 0: modelOverride = nil
        case 1: modelOverride = ""
        case 2: modelOverride = defaults.string(forKey: "model-\(target.rawValue)")
        case let index where ModelLabel.known.indices.contains(index - 3): modelOverride = ModelLabel.known[index - 3]
        default: return
        }
        panel.makeFirstResponder(editor)
        refresh()
    }

    private func slotLabel(_ slot: String) -> String {
        switch slot {
        case "material": return "材料"
        case "acceptance": return "验收"
        case "boundary": return "边界"
        case "format": return "输出形态"
        case "role": return "角色"
        case "goal": return "目标"
        default: return slot
        }
    }

    private func slotKey(_ label: String) -> String {
        let map = ["材料": "material", "验收": "acceptance", "边界": "boundary",
                   "输出形态": "format", "角色": "role", "目标": "goal"]
        return map[label] ?? label
    }

    private func parseOverrides(_ text: String) -> [String: String] {
        var result: [String: String] = [:]
        for pair in text.split(whereSeparator: { $0 == "；" || $0 == ";" }) {
            let normalized = pair.replacingOccurrences(of: "＝", with: "=")
            let parts = normalized.split(separator: "=", maxSplits: 1, omittingEmptySubsequences: true)
            guard parts.count == 2 else { continue }
            let label = parts[0].trimmingCharacters(in: .whitespaces)
            let value = parts[1].trimmingCharacters(in: .whitespaces)
            guard !label.isEmpty, !value.isEmpty else { continue }
            result[slotKey(label)] = value
        }
        return result
    }

    @objc private func backToInput() {
        preview = nil
        editor.string = original
        panel.makeFirstResponder(editor)
        editor.setSelectedRange(NSRange(location: editor.string.utf16.count, length: 0))
        refresh()
    }

    @objc private func submit() {
        guard !editor.hasMarkedText() else { return }
        if let draft = preview {
            let overrides = parseOverrides(overrideField.stringValue)
            if !overrides.isEmpty {
                let refreshed = slotComposer.compose(original, target: target, model: model, overrides: overrides, sceneId: sceneOverride)
                preview = refreshed
                editor.string = refreshed.text
                refresh()
            }
            let output = editor.string
            guard !output.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty else { return }
            let clipboard = NSPasteboard.general
            clipboard.clearContents()
            guard clipboard.setString(output, forType: .string) else {
                provenance.stringValue = "剪贴板写入失败，请重试"
                return
            }
            defaults.set(target.rawValue, forKey: "recentTarget")
            defaults.set(Date.now.timeIntervalSince1970, forKey: "recentTargetTime")
            if let model { defaults.set(model, forKey: "model-\(target.rawValue)") }
            original = ""
            editor.string = ""
            preview = nil
            sceneOverride = nil
            targetOverride = nil
            modelOverride = nil
            hide()
            didCopy?()
        } else {
            original = editor.string
            let draft = slotComposer.compose(original, target: target, model: model, sceneId: sceneOverride)
            captureTask?.cancel()
            classificationTask?.cancel()
            preview = draft
            editor.string = draft.text
            editor.setSelectedRange(NSRange(location: 0, length: 0))
            editor.scrollRangeToVisible(NSRange(location: 0, length: 0))
            refresh()
        }
    }
}
