import AppKit
import ApplicationServices
import CoreGraphics
import PromptCore
import ScreenCaptureKit
import Vision

struct WindowObservation {
    let target: AgentTarget?
    let windowID: CGWindowID?

    static func observe(_ app: NSRunningApplication?) -> WindowObservation {
        guard let app else { return WindowObservation(target: nil, windowID: nil) }
        let windows = CGWindowListCopyWindowInfo([.optionOnScreenOnly, .excludeDesktopElements], kCGNullWindowID)
            as? [[String: Any]] ?? []
        let window = windows.first {
            guard $0[kCGWindowOwnerPID as String] as? Int32 == app.processIdentifier,
                  $0[kCGWindowLayer as String] as? Int == 0,
                  let bounds = $0[kCGWindowBounds as String] as? [String: Any],
                  let frame = CGRect(dictionaryRepresentation: bounds as CFDictionary)
            else { return false }
            return frame.width > 240 && frame.height > 200
        }
        let bundleTarget = AgentTarget.detect(bundleID: app.bundleIdentifier, windowTitle: nil)
        let title = bundleTarget == nil
            ? (focusedWindowTitle(of: app.processIdentifier) ?? window?[kCGWindowName as String] as? String)
            : nil
        return WindowObservation(
            target: bundleTarget ?? AgentTarget.detect(bundleID: app.bundleIdentifier, windowTitle: title),
            windowID: (window?[kCGWindowNumber as String] as? NSNumber)?.uint32Value
        )
    }

    private static func focusedWindowTitle(of pid: pid_t) -> String? {
        guard AXIsProcessTrusted() else { return nil }
        var window: CFTypeRef?
        let app = AXUIElementCreateApplication(pid)
        AXUIElementSetMessagingTimeout(app, 0.08)
        guard AXUIElementCopyAttributeValue(app, kAXFocusedWindowAttribute as CFString, &window) == .success,
              let window, CFGetTypeID(window) == AXUIElementGetTypeID()
        else { return nil }
        var title: CFTypeRef?
        let element = unsafeDowncast(window, to: AXUIElement.self)
        AXUIElementCopyAttributeValue(element, kAXTitleAttribute as CFString, &title)
        return title as? String
    }
}

enum WindowModelRecognition {
    static func detect(windowID: CGWindowID) async throws -> String? {
        guard CGPreflightScreenCaptureAccess() else { return nil }
        let available = try await SCShareableContent.excludingDesktopWindows(true, onScreenWindowsOnly: false)
        guard let window = available.windows.first(where: { $0.windowID == windowID }) else { return nil }
        let filter = SCContentFilter(desktopIndependentWindow: window)
        let configuration = SCStreamConfiguration()
        configuration.width = min(Int(window.frame.width * 2), 3200)
        configuration.height = min(Int(window.frame.height * 2), 2200)
        configuration.showsCursor = false
        let image = try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: configuration)
        try Task.checkCancellation()

        // Vision uses a bottom-left origin. Inspect the toolbar and composer.
        let regions = [
            CGRect(x: 0, y: 0.89, width: 1, height: 0.11),
            CGRect(x: 0, y: 0, width: 1, height: 0.18)
        ]
        let requests = regions.map { region in
            let request = VNRecognizeTextRequest()
            request.recognitionLevel = .accurate
            request.recognitionLanguages = ["en-US", "zh-Hans"]
            request.usesLanguageCorrection = false
            request.regionOfInterest = region
            return request
        }
        try VNImageRequestHandler(cgImage: image).perform(requests)
        let labels = requests.flatMap { $0.results ?? [] }
            .compactMap { $0.topCandidates(1).first }
            .filter { $0.confidence >= 0.65 }.map(\.string)
        return ModelLabel.detect(in: labels)
    }
}
