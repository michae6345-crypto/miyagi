import Foundation
import AVFoundation

// Offline word-loss measurement for the release tail (Tail.swift). Built and run by measure-tail.sh.
// No mic, no key tap, no prompts, nothing on screen: each audio file goes through the real Transcriber (SpeechAnalyzer),
// and every change of its text is timed against "release", so measure-tail.py can replay any tail policy on it.
//
//   tail-measure warm <padMs> <file>...   the recognizer is ready before the keys go down; the file is fed at mic pace
//                                         (85 ms buffers, like the 4096-frame 48 kHz tap), then padMs of silence,
//                                         then release
//   tail-measure cold <padMs> <file>...   the recognizer is still starting at release (first hold after launch): the
//                                         whole hold is queued, then flushed at once when it is ready, like
//                                         Session.sttStarted; the tail starts at the flush
//
// One JSON line per file: {file, mode, audioMs, startMs, finishMs, final, events: [[ms, text], ...]} with ms relative
// to release (or the flush, for cold). The words never leave this process except as that line on stdout.

func log(_ s: String) { fputs("[tail-measure] \(s)\n", stderr) }

func emit(_ obj: [String: Any]) {
    guard let d = try? JSONSerialization.data(withJSONObject: obj, options: [.withoutEscapingSlashes]),
          let s = String(data: d, encoding: .utf8) else { return }
    print(s); fflush(stdout)
}

/// The file in mic-sized buffers (about 85 ms each), plus padMs of silence.
func readBuffers(_ path: String, padMs: Int) throws -> (bufs: [AVAudioPCMBuffer], audioMs: Double, bufMs: Double) {
    let f = try AVAudioFile(forReading: URL(fileURLWithPath: path))
    let fmt = f.processingFormat
    let chunk = AVAudioFrameCount(max(256, Int(fmt.sampleRate * 0.085)))
    var out: [AVAudioPCMBuffer] = []
    while f.framePosition < f.length {
        guard let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: chunk) else { break }
        try f.read(into: buf, frameCount: chunk)
        if buf.frameLength == 0 { break }
        out.append(buf)
    }
    var padFrames = Int(fmt.sampleRate * Double(padMs) / 1000)
    while padFrames > 0 {
        let n = AVAudioFrameCount(min(Int(chunk), padFrames))
        guard let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: n) else { break }
        buf.frameLength = n   // zero-filled: room silence
        out.append(buf)
        padFrames -= Int(n)
    }
    let ms = Double(f.length) / fmt.sampleRate * 1000 + Double(padMs)
    return (out, ms, Double(chunk) / fmt.sampleRate * 1000)
}

final class Timeline {
    private let lock = NSLock()
    private var origin = Date()
    private var events: [(Date, String)] = []
    func add(_ text: String) { lock.lock(); events.append((Date(), text)); lock.unlock() }
    func setOrigin(_ d: Date) { lock.lock(); origin = d; lock.unlock() }
    func rel(_ d: Date) -> Int { lock.lock(); defer { lock.unlock() }; return Int((d.timeIntervalSince(origin) * 1000).rounded()) }
    func dump() -> [[Any]] {
        lock.lock(); defer { lock.unlock() }
        return events.map { [Int(($0.0.timeIntervalSince(origin) * 1000).rounded()), $0.1] }
    }
}

let argv = Array(CommandLine.arguments.dropFirst())
guard argv.count >= 3, ["warm", "cold"].contains(argv[0]), let padMs = Int(argv[1]) else {
    log("usage: tail-measure warm|cold <padMs> <file>..."); exit(64)
}
let mode = argv[0]
let files = Array(argv.dropFirst(2))

Task {
    let locale = Locale(identifier: "en-US")
    guard await Transcriber.detect(locale: locale) == .speechanalyzer else { log("needs SpeechAnalyzer (macOS 26)"); exit(2) }
    for path in files {
        do {
            let (bufs, audioMs, bufMs) = try readBuffers(path, padMs: padMs)
            let stt = try Transcriber.makeSession(kind: .speechanalyzer, locale: locale, terms: [])
            let tl = Timeline()
            let t0 = Date()
            try await stt.start { text in tl.add(text) }
            let startMs = Int(Date().timeIntervalSince(t0) * 1000)
            if mode == "warm" {
                // Mic pace: each buffer goes in when its audio would have been captured.
                let feedStart = Date()
                for (i, b) in bufs.enumerated() {
                    let wait = feedStart.addingTimeInterval(Double(i + 1) * bufMs / 1000).timeIntervalSinceNow
                    if wait > 0 { try? await Task.sleep(nanoseconds: UInt64(wait * 1e9)) }
                    stt.feed(b)
                }
                tl.setOrigin(Date())   // release
            } else {
                tl.setOrigin(Date())   // the flush (Session.sttStarted), where the tail starts
                for b in bufs { stt.feed(b) }
            }
            let final = await stt.finish()
            let finishMs = tl.rel(Date())
            emit(["file": (path as NSString).lastPathComponent, "mode": mode, "padMs": padMs, "audioMs": Int(audioMs),
                  "startMs": startMs, "finishMs": finishMs, "final": final, "events": tl.dump()])
        } catch {
            log("\(path): \(error)")
        }
    }
    exit(0)
}
RunLoop.main.run()
