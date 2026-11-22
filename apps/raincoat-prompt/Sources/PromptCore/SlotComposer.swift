import Foundation

// v0.3: six-slot, plain-text composer. The user's own words stay verbatim; the
// composer only adds the structure the target model still needs (see
// docs/product-v0.3.md). Length budgets apply to the added sentences, not to the
// user's input.

public struct ModelProfile: Codable, Sendable {
    public let id: String
    public let display: String
    public let tier: String
    public let sentence_budget: Int
    public let char_budget: Int
    public let order: [String]
    public let official: Bool
    public let source: String
    public let fetched_at: String
    public let notes: String
    public let extra: [String]?
}

public struct ModelProfileCatalog: Codable, Sendable {
    public let version: String
    public let profiles: [ModelProfile]
}

public struct SceneSlotSpec: Codable, Sendable {
    public let id: String
    public let label: String
    public let aliases: [String]
    public let blocking: [String]
    public let optional: [String]
    public let defaults: [String: String]
}

public struct SceneSlotCatalog: Codable, Sendable {
    public let version: String
    public let slots: [String]
    public let scenes: [SceneSlotSpec]
}

public struct PromptQuestion: Codable, Sendable, Equatable {
    public let slot: String
    public let text: String
    public let defaultValue: String
}

public struct SlotDraft: Codable, Sendable, Equatable {
    public let text: String
    public let questions: [PromptQuestion]
    public let missing: [String]
    public let profile: String
    public let tier: String
    public let scene: String
    public let addedCharacters: Int
    public let addedSentences: Int
}

public struct SlotComposer: Sendable {
    public let profiles: ModelProfileCatalog
    public let scenes: SceneSlotCatalog

    public init(profiles: ModelProfileCatalog, scenes: SceneSlotCatalog) {
        self.profiles = profiles
        self.scenes = scenes
    }

    public static func bundled() -> SlotComposer {
        let embedded = Bundle.main.resourceURL?.appendingPathComponent("RaincoatPrompt_PromptCore.bundle")
        let bundle = embedded.flatMap { Bundle(url: $0) } ?? Bundle.module
        let profilesURL = bundle.url(forResource: "model-profiles", withExtension: "json")!
        let scenesURL = bundle.url(forResource: "scene-slots", withExtension: "json")!
        let decoder = JSONDecoder()
        return SlotComposer(
            profiles: try! decoder.decode(ModelProfileCatalog.self, from: Data(contentsOf: profilesURL)),
            scenes: try! decoder.decode(SceneSlotCatalog.self, from: Data(contentsOf: scenesURL))
        )
    }

    public func profile(for target: AgentTarget, model: String?) -> ModelProfile {
        let id: String
        switch target {
        case .chatGPT, .codex, .deepResearch, .general: id = "gpt"
        case .claude: id = "claude"
        case .bitto: id = "bitto"
        case .workBuddy: id = "workbuddy"
        case .deepseek: id = "deepseek"
        }
        if let id = profiles.profiles.first(where: { $0.id == id }) { return id }
        return profiles.profiles.first { $0.id == "gpt" }!
    }

    public func scene(for text: String) -> SceneSlotSpec {
        let topic = text.lowercased()
        var best: (SceneSlotSpec, Int)?
        for scene in scenes.scenes {
            let hits = scene.aliases.reduce(0) { $0 + (topic.contains($1.lowercased()) ? 1 : 0) }
            if hits > (best?.1 ?? 0) { best = (scene, hits) }
        }
        return best?.0 ?? scenes.scenes[0]
    }

    public func compose(_ text: String, target: AgentTarget, model: String?, overrides: [String: String] = [:], sceneId: String? = nil) -> SlotDraft {
        let original = AgentTarget.taskText(in: text.trimmingCharacters(in: .whitespacesAndNewlines))
        let profile = profile(for: target, model: model)
        let scene = sceneId.flatMap { id in scenes.scenes.first { $0.id == id } } ?? scene(for: original)
        let present = slotsPresent(in: original)

        var missing = scene.blocking.filter { !present.contains($0) && overrides[$0] == nil }
        if missing.count > 3 { missing = Array(missing.prefix(3)) }
        let questions = missing.map { slot in
            PromptQuestion(slot: slot, text: questionText(slot, scene: scene),
                           defaultValue: scene.defaults[slot] ?? "")
        }

        var sentences: [(slot: String, text: String, blocking: Bool)] = []
        // Frontier models get no role play: OpenAI and Anthropic both say the
        // newer models need goals and outcomes, not scripts.
        if profile.tier != "frontier", let role = roleSentence(scene) {
            sentences.append(("role", role, false))
        }
        sentences.append(("goal", original, true))
        if let override = overrides["acceptance"], !override.isEmpty {
            sentences.append(("acceptance", override, true))
        } else if let acceptance = sentence(for: "acceptance", scene: scene, present: present, profile: profile) {
            sentences.append(("acceptance", acceptance, true))
        }
        // Constraints the scene treats as blocking are merged into one sentence so
        // the frontier budget stays at goal + acceptance + constraint.
        var constraintParts: [String] = []
        for slot in ["material", "boundary", "format"] where scene.blocking.contains(slot) {
            if let override = overrides[slot], !override.isEmpty {
                constraintParts.append(override)
            } else if let value = sentence(for: slot, scene: scene, present: present, profile: profile) {
                constraintParts.append(value)
            }
        }
        if !constraintParts.isEmpty {
            sentences.append(("constraint", constraintParts.joined(separator: "；"), false))
        }
        if profile.extra?.contains("no_tools_boundary") == true {
            sentences.append(("boundary", "你没有工具执行能力，缺材料就列清单，不要伪造调用。", false))
        }
        var ordered = sentences
        func addedCount(_ rows: [(slot: String, text: String, blocking: Bool)]) -> (Int, Int) {
            let added = rows.filter { $0.slot != "goal" }
            return (added.reduce(0) { $0 + $1.text.count }, added.count)
        }
        // Trim optional sentences first, then stop. Goal and acceptance are kept.
        while addedCount(ordered).0 > profile.char_budget || addedCount(ordered).1 > profile.sentence_budget {
            guard let index = ordered.lastIndex(where: { !$0.blocking && $0.slot != "goal" }) else { break }
            ordered.remove(at: index)
        }
        var trimmed: [String] = []
        var remaining = profile.char_budget
        for row in ordered {
            if row.slot == "goal" { trimmed.append(row.text); continue }
            if row.text.count <= remaining {
                trimmed.append(row.text)
                remaining -= row.text.count
            } else if row.blocking {
                trimmed.append(row.text)  // never drop the acceptance sentence
            }
        }
        let body = trimmed
            .map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }
            .filter { !$0.isEmpty }
            .map { $0.hasSuffix("。") ? $0 : $0 + "。" }
            .joined()
        let counts = addedCount(ordered)
        return SlotDraft(text: body, questions: questions, missing: missing,
                         profile: profile.id, tier: profile.tier, scene: scene.id,
                         addedCharacters: counts.0, addedSentences: counts.1)
    }

    private func slotsPresent(in text: String) -> Set<String> {
        var found: Set<String> = ["goal"]
        if text.containsAny(["你是", "作为", "以…身份", "以...身份"]) { found.insert("role") }
        if text.containsAny(["材料", "附件", "数据", "口径", "预算", "周期", "代码", "报错",
                             "记录", "报价", "访谈", "约束", "人手", "期间", "分母"]) { found.insert("material") }
        if text.containsAny(["验收", "标准", "怎么算", "可复算", "通过", "测试", "检查", "复算"]) { found.insert("acceptance") }
        if text.containsAny(["不要", "别", "禁止", "不得", "未知", "待确认", "不确定"]) { found.insert("boundary") }
        if text.containsAny(["字", "句", "格式", "表格", "JSON", "json", "列表", "一行", "段落", "篇幅"]) { found.insert("format") }
        return found
    }

    private func roleSentence(_ scene: SceneSlotSpec) -> String? {
        guard let role = scene.defaults["role"], !role.isEmpty else { return nil }
        return role.hasPrefix("你是") ? role : "你是" + role
    }

    private func sentence(for slot: String, scene: SceneSlotSpec, present: Set<String>, profile: ModelProfile) -> String? {
        let defaultValue = scene.defaults[slot] ?? ""
        switch slot {
        case "acceptance":
            if present.contains("acceptance") { return nil }
            return defaultValue.isEmpty ? nil : defaultValue
        case "material":
            if present.contains("material") { return nil }
            return defaultValue.isEmpty ? nil : defaultValue
        case "boundary":
            if present.contains("boundary") { return nil }
            return defaultValue.isEmpty ? nil : defaultValue
        case "format":
            if present.contains("format") { return nil }
            return defaultValue.isEmpty ? nil : defaultValue
        default:
            return nil
        }
    }

    private func questionText(_ slot: String, scene: SceneSlotSpec) -> String {
        switch slot {
        case "goal": return "这次要交付什么、给谁用？"
        case "material": return "依据哪些材料或约束？（\(scene.label)）"
        case "acceptance": return "怎么算完成？验收方式是什么？"
        case "boundary": return "有什么不能做，或者必须标注为未知的？"
        case "format": return "交付形态和长度有什么要求？"
        case "role": return "以什么身份来写？"
        default: return "补充 \(slot)？"
        }
    }
}

private extension String {
    func containsAny(_ candidates: [String]) -> Bool { candidates.contains { contains($0) } }
}
