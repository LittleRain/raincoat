import Foundation
import Testing
@testable import PromptCore

private let composer = SlotComposer.bundled()

@Test func resolvesKnownAgentsAndIgnoresAmbiguousWindows() {
    #expect(AgentTarget.detect(bundleID: "ai.bitto.desktop", windowTitle: nil) == .bitto)
    #expect(AgentTarget.detect(bundleID: "com.tencent.workbuddy.mac", windowTitle: nil) == .workBuddy)
    #expect(AgentTarget.detect(bundleID: "com.anthropic.claudefordesktop", windowTitle: nil) == .claude)
    #expect(AgentTarget.detect(bundleID: "com.openai.codex", windowTitle: "Codex") == nil)
    #expect(AgentTarget.detect(bundleID: "com.openai.codex", windowTitle: "ChatGPT") == .chatGPT)
    #expect(AgentTarget.detect(bundleID: "com.google.Chrome", windowTitle: "调研 ChatGPT") == nil)
}

@Test func explicitDestinationStaysOutOfTheCopiedPrompt() {
    #expect(AgentTarget.explicit(in: "这条发给 Bitto，分析退货率") == .bitto)
    #expect(AgentTarget.explicit(in: "帮我调研 ChatGPT Deep Research 的工作原理") == nil)
    let draft = composer.compose("这条发给 Bitto，分析这两周退货率", target: .bitto, model: "deepseek-v4.1-flash")
    #expect(!draft.text.contains("发给 Bitto"))
    #expect(draft.text.contains("退货率"))
}

@Test func onlyUsesAnUnambiguousModelLabel() {
    #expect(ModelLabel.detect(in: ["选择模型：deepseek-v4.1-flash"]) == "DeepSeek V4.1 Flash")
    #expect(ModelLabel.detect(in: ["GPT-6 Astra", "Claude Opus 5.5"]) == nil)
    #expect(ModelLabel.detect(in: ["建议使用 GPT-6 Astra 做证据调研"]) == nil)
}

@Test func classifiesSevenOfficeScenes() {
    let probes: [(String, String)] = [
        ("把这段通知改得客气一点，明天发全员", "writing"),
        ("写个本周周报，老板要看", "report"),
        ("整理一下今天的会议纪要", "meeting"),
        ("这两周退货率是不是变高了，问题主要出在哪", "data"),
        ("调研一下竞品定价", "research"),
        ("设计一个为期两周的试点方案", "plan"),
        ("支付回调重试会不会重复扣款", "code"),
    ]
    for (text, expected) in probes {
        #expect(composer.scene(for: text).id == expected)
    }
}

@Test func frontierProfilesStayWithinBudgetAndSkipRolePlay() {
    for target in [AgentTarget.claude, .chatGPT, .codex] {
        let draft = composer.compose("这两周退货率是不是变高了，问题主要出在哪", target: target, model: nil)
        #expect(draft.tier == "frontier")
        #expect(!draft.text.contains("你是"))
        #expect(draft.addedSentences <= 4)
        #expect(draft.addedCharacters <= 120)
    }
}

@Test func midProfilesAddRoleAndKeepTheWorkBuddyBoundary() {
    let draft = composer.compose("帮我加个重试机制", target: .workBuddy, model: "kimi-k2.5")
    #expect(draft.tier == "mid")
    #expect(draft.text.contains("你是"))
    #expect(draft.text.contains("没有工具执行能力"))
    #expect(draft.addedSentences <= 7)
    #expect(draft.addedCharacters <= 220)
}

@Test func blockingGapsBecomeAtMostThreeQuestionsWithDefaults() {
    let draft = composer.compose("写个本周周报，老板要看", target: .chatGPT, model: nil)
    #expect(draft.questions.count <= 3)
    #expect(!draft.questions.isEmpty)
    for question in draft.questions {
        #expect(!question.defaultValue.isEmpty)
        #expect(draft.missing.contains(question.slot))
    }
}

@Test func overridesReplaceDefaultsAndClearTheQuestion() {
    let text = "这两周退货率是不是变高了，问题主要出在哪"
    let base = composer.compose(text, target: .claude, model: nil)
    #expect(base.missing.contains("acceptance"))
    let overridden = composer.compose(text, target: .claude, model: nil,
                                      overrides: ["acceptance": "验收以财务口径的净退款为准"])
    #expect(overridden.text.contains("验收以财务口径的净退款为准"))
    #expect(!overridden.missing.contains("acceptance"))
    #expect(!overridden.questions.contains { $0.slot == "acceptance" })
}

@Test func rendersPlainTextWithNoMarkupOrPlaceholders() {
    let draft = composer.compose("整理一下今天的会议纪要", target: .bitto, model: nil)
    for marker in ["#", "**", "<", ">", "1."] {
        #expect(!draft.text.contains(marker))
    }
    for placeholder in ["TODO", "待补充", "[请填写]"] {
        #expect(!draft.text.contains(placeholder))
    }
}

@Test func renderIsDeterministicAndSceneOverrideWins() {
    let text = "调研一下竞品定价"
    #expect(composer.compose(text, target: .bitto, model: nil) == composer.compose(text, target: .bitto, model: nil))
    let forced = composer.compose(text, target: .bitto, model: nil, sceneId: "writing")
    #expect(forced.scene == "writing")
}
