import Foundation

public enum AgentTarget: String, CaseIterable, Codable, Sendable {
    case general, chatGPT, deepResearch, bitto, workBuddy, codex, claude, deepseek

    public var title: String {
        switch self {
        case .general: "通用 Agent"
        case .chatGPT: "ChatGPT"
        case .deepResearch: "ChatGPT Deep Research"
        case .bitto: "Bitto"
        case .workBuddy: "WorkBuddy"
        case .codex: "Codex CLI"
        case .claude: "Claude / Claude Code"
        case .deepseek: "DeepSeek App"
        }
    }

    public static func detect(bundleID: String?, windowTitle: String?) -> AgentTarget? {
        switch bundleID {
        case "ai.bitto.desktop": return .bitto
        case "com.anthropic.claudefordesktop": return .claude
        case "com.tencent.workbuddy.mac", "com.workbuddy.workbuddy": return .workBuddy
        case "com.openai.chat": return .chatGPT
        case "com.openai.codex", "com.google.Chrome", "com.apple.Safari", "com.microsoft.edgemac", "org.mozilla.firefox", "company.thebrowser.Browser":
            let title = windowTitle?.trimmingCharacters(in: .whitespacesAndNewlines) ?? ""
            if title == "ChatGPT" || title.hasPrefix("ChatGPT - ") || title.hasPrefix("ChatGPT — ") {
                return .chatGPT
            }
            return nil
        default: return nil
        }
    }

    public static func explicit(in text: String) -> AgentTarget? {
        let firstLine = text.prefix(200).split(whereSeparator: \.isNewline).first.map(String.init) ?? ""
        guard let range = routingPrefix(in: firstLine) else { return nil }
        let destination = firstLine[range].lowercased()
            .replacingOccurrences(of: #"\s+"#, with: " ", options: .regularExpression)
        if destination.contains("deep research") { return .deepResearch }
        if destination.contains("chatgpt") { return .chatGPT }
        if destination.contains("bitto") { return .bitto }
        return .workBuddy
    }

    static func taskText(in text: String) -> String {
        guard let range = routingPrefix(in: text) else { return text }
        return String(text[range.upperBound...]).replacingOccurrences(
            of: #"^[\s：:，,。]+"#, with: "", options: .regularExpression
        )
    }

    private static func routingPrefix(in text: String) -> Range<String.Index>? {
        text.range(
            of: #"^\s*(?:这条\s*|请\s*)?(?:发给|用\s+)\s*(ChatGPT\s+Deep\s+Research|ChatGPT|Bitto|WorkBuddy)(?=[\s：:，,。]|$)"#,
            options: [.regularExpression, .caseInsensitive]
        )
    }
}

public enum ModelLabel {
    public static let known = [
        "GPT-6 Astra", "GPT-6.1 Sol", "GPT-6.1 Terra", "GPT-6 Luna",
        "DeepSeek V4.1 Flash", "DeepSeek V4 Flash", "DeepSeek V4 Pro",
        "Claude Opus 5.5", "Claude Fable 5.2", "Gemini 3 Pro", "Gemini 3 Flash", "Kimi K2.5"
    ]

    static func key(_ label: String) -> String {
        label.lowercased().filter { $0.isLetter || $0.isNumber || $0 == "." }
    }

    public static func detect(in lines: [String]) -> String? {
        let matches = Set(lines.compactMap { line in
            let label = line.replacingOccurrences(
                of: #"^\s*(?:选择模型|模型|select model|model)\s*[:：]\s*"#,
                with: "", options: [.regularExpression, .caseInsensitive]
            )
            return known.first { key($0) == key(label) }
        })
        return matches.count == 1 ? matches.first : nil
    }
}
