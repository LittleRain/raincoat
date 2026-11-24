import Foundation
import Vision
import AppKit

let path = CommandLine.arguments[1]
guard let img = NSImage(contentsOfFile: path),
      let cg = img.cgImage(forProposedRect: nil, context: nil, hints: nil) else {
    FileHandle.standardError.write("cannot load\n".data(using: .utf8)!)
    exit(1)
}
let req = VNRecognizeTextRequest()
req.recognitionLevel = .accurate
req.recognitionLanguages = ["zh-Hans", "ja-JP", "en-US"]
req.usesLanguageCorrection = false
let handler = VNImageRequestHandler(cgImage: cg, options: [:])
do { try handler.perform([req]) } catch { exit(2) }
for obs in (req.results ?? []) {
    if let c = obs.topCandidates(1).first { print(c.string) }
}
