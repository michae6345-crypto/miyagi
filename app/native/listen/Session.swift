import Foundation
import AVFoundation

// ---------------------------------------------------------------------------------------------------------------------
// JSON-lines output (stdout). One object per line, "type" first. See PUSH-TO-TALK.md for the protocol.
// ---------------------------------------------------------------------------------------------------------------------
enum Out {
    private static let lock = NSLock()

    static func enc(_ v: Any) -> String {
        guard let d = try? JSONSerialization.data(withJSONObject: v, options: [.fragmentsAllowed, .withoutEscapingSlashes]),
              let s = String(data: d, encoding: .utf8) else { return "null" }
        return s
    }

    static func emit(_ type: String, _ fields: [(String, Any)] = []) {
        var parts = ["\"type\":" + enc(type)]
        for (k, v) in fields { parts.append(enc(k) + ":" + enc(v)) }
        let line = "{" + parts.joined(separator: ",") + "}\n"
        lock.lock(); defer { lock.unlock() }
        fputs(line, stdout)
        fflush(stdout)
    }

    static func error(_ code: String, _ message: String) {
        emit("error", [("code", code), ("message", message)])
    }
}

func log(_ s: String) { fputs("[miyagi-listen] \(s)\n", stderr) }

// ---------------------------------------------------------------------------------------------------------------------
// Config and ids
// ---------------------------------------------------------------------------------------------------------------------
enum Chord: String {
    case fnControl = "fn+control"
    case controlOption = "control+option"
}

struct Config {
    var enabled = false
    var chord: Chord = .fnControl
    var minHoldMs = 250
    var maxHoldMs = 60_000
    var locale = "en-US"
    /// The release tail's warm cap (Tail.swift): the final goes the moment it comes; if it has not come by this cap
    /// (longer after a cold-start flush), the best text so far goes. Kept within Tail.floorMs...Tail.ceilingMs.
    var tailMs = Tail.maxMs
}

enum Ids {
    private static var counter = 0
    private static let base = String(UInt64(Date().timeIntervalSince1970 * 1000) % 1_679_616, radix: 36)
    static func next() -> String {
        counter += 1
        return "\(base)-\(counter)"
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// Test hooks (only reachable with --stdin-only via the hidden {"cmd":"_simulate"} command)
// ---------------------------------------------------------------------------------------------------------------------
struct SimOptions {
    var fakeText: String?        // use a fake STT that returns exactly this text
    var finalDelayMs = 0         // fake STT only: how long finish() takes
    var lagMs = -1               // fake STT only: >= 0 makes it lag like SpeechAnalyzer: the last word is missing from
                                 // its text until lagMs after the input ends (then a partial brings it)
    var startDelayMs = 0         // fake STT only: how long start() takes (a cold start: release before it is ready)
    var file: String?            // feed this audio file through the real Transcriber instead of the mic
}

// ---------------------------------------------------------------------------------------------------------------------
// One hold of the chord. Everything here runs on the main thread, except onAudio (audio thread).
// ---------------------------------------------------------------------------------------------------------------------
final class Session {
    enum Phase { case held, opening, listening, finishing, done }

    let id = Ids.next()
    private(set) var phase: Phase = .held
    private let ctl: Controller
    private let config: Config
    private let terms: [String]
    private let sim: SimOptions?

    private var minHoldItem: DispatchWorkItem?
    private var maxHoldItem: DispatchWorkItem?
    private var audio: AudioSource?
    private var stt: SttSession?

    // audio -> stt hand-off. Mic buffers that arrive before the STT is ready are queued, then flushed in order.
    private let bufLock = NSLock()
    private var pending: [AVAudioPCMBuffer] = []
    private var sttReady = false
    private var finishWanted = false
    private var lastPartial = ""
    private var resolved = false
    // The release tail (Tail.swift): audio flushed at once when the STT became ready (a cold start lengthens the cap).
    private var flushedMs = 0
    private var flushedAt: Date?
    private var tailStarted = false

    init(ctl: Controller, config: Config, terms: [String], sim: SimOptions?) {
        self.ctl = ctl; self.config = config; self.terms = terms; self.sim = sim
    }

    // MARK: lifecycle

    func begin() {
        Out.emit("ptt", [("state", "down"), ("id", id)])
        let min = DispatchWorkItem { [weak self] in self?.openMic() }
        minHoldItem = min
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(config.minHoldMs), execute: min)
        let max = DispatchWorkItem { [weak self] in self?.heldTooLong() }
        maxHoldItem = max
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(config.maxHoldMs), execute: max)
    }

    /// The chord was released.
    func release() {
        guard phase != .done, phase != .finishing else { return }
        Out.emit("ptt", [("state", "up"), ("id", id)])
        minHoldItem?.cancel(); maxHoldItem?.cancel()
        if phase == .held {                 // released before the minimum hold: the mic never opened
            phase = .done; resolved = true
            Out.emit("cancelled", [("id", id), ("reason", "short")])
            ctl.sessionEnded(self)
            return
        }
        // opening or listening: close the mic now; the STT may still be starting (async), it finishes when ready.
        phase = .finishing
        audio?.stop(); audio = nil
        bufLock.lock(); finishWanted = true; let ready = sttReady; bufLock.unlock()
        if ready { startFinishing() }
    }

    /// Drop the session with a reason. No-op once it has ended.
    func abort(_ reason: String) {
        guard phase != .done, !resolved else { return }
        minHoldItem?.cancel(); maxHoldItem?.cancel()
        phase = .done; resolved = true
        audio?.stop(); audio = nil
        stt?.cancel(); stt = nil
        Out.emit("cancelled", [("id", id), ("reason", reason)])
        ctl.sessionEnded(self)
    }

    private func heldTooLong() {
        guard phase == .held || phase == .opening || phase == .listening else { return }
        ctl.holdCapped(self)
        abort("timeout")
    }

    // MARK: opening the mic

    private func openMic() {
        guard phase == .held else { return }
        phase = .opening
        // 1. Audio first, so nothing the user says during the STT start is lost.
        let source: AudioSource
        if let sim = sim { source = SimSource(file: sim.file) } else { source = Mic() }
        if sim == nil, Perms.micStatus() != "granted" {
            // Never asked is not the same as refused: the app shows an Allow card for one and Open settings for the other.
            if Perms.micStatus() == "undetermined" { Out.error("mic_undetermined", "Microphone access hasn't been asked for yet.") }
            else { Out.error("mic_denied", "Microphone access isn't granted for miyagi.") }
            Perms.refresh(force: true)
            abort("disabled"); return
        }
        do {
            try source.start { [weak self] buf in self?.onAudio(buf) }
        } catch {
            Out.error("mic_denied", "Couldn't open the microphone: \(error.localizedDescription)")
            abort("disabled"); return
        }
        audio = source
        phase = .listening
        Out.emit("listening", [("id", id)])

        // 2. The STT starts in parallel (async); buffers queue until it is ready.
        let session: SttSession
        do {
            if let sim = sim, let fake = sim.fakeText {
                session = FakeStt(text: fake, finalDelayMs: sim.finalDelayMs, lagMs: sim.lagMs, startDelayMs: sim.startDelayMs)
            }
            else { session = try Transcriber.makeSession(kind: ctl.sttKind, locale: Locale(identifier: config.locale), terms: terms) }
        } catch {
            sttFailed(error); return
        }
        stt = session
        Task { [weak self] in
            do {
                try await session.start { text in
                    DispatchQueue.main.async { self?.gotPartial(text) }
                }
                DispatchQueue.main.async { self?.sttStarted(session) }
            } catch {
                DispatchQueue.main.async { self?.sttFailed(error) }
            }
        }
    }

    private func sttFailed(_ error: Error) {
        guard phase != .done else { return }
        if case SttError.assetsMissing = error {
            Out.error("assets_missing", "The speech model for \(config.locale) isn't installed yet.")
        } else if case SttError.unavailable = error {
            Out.error("no_stt", "No on-device speech recognition is available.")
        } else {
            Out.error("no_stt", "Speech recognition failed to start: \(error.localizedDescription)")
        }
        abort("disabled")
    }

    private func sttStarted(_ session: SttSession) {
        guard phase != .done, stt === session else { session.cancel(); return }
        bufLock.lock()
        let queued = pending; pending = []
        for b in queued { session.feed(b) }
        // How much audio went in at once: the recognizer may need a while to work through it (a cold start).
        flushedMs = Int(queued.reduce(0.0) { $0 + Double($1.frameLength) / max($1.format.sampleRate, 1) } * 1000)
        flushedAt = Date()
        sttReady = true
        let wanted = finishWanted
        bufLock.unlock()
        if wanted { startFinishing() }
    }

    private func onAudio(_ buf: AVAudioPCMBuffer) {
        bufLock.lock(); defer { bufLock.unlock() }
        if sttReady { stt?.feed(buf) }
        else if let copy = buf.copied() { pending.append(copy) }
    }

    // MARK: results

    private func gotPartial(_ text: String) {
        guard phase == .listening || phase == .finishing, !resolved else { return }
        let t = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !t.isEmpty, t != lastPartial else { return }
        lastPartial = t
        Out.emit("partial", [("id", id), ("text", t)])
    }

    /// Mic is closed and the STT is ready: end the input and send the final the moment it comes (about 65 ms on
    /// SpeechAnalyzer); if it has not come by the cap (Tail.swift: 1 s, up to 1.5 s after a cold-start flush), send the
    /// best text so far. The tail starts here: at release, or when the STT is ready if that is later.
    private func startFinishing() {
        guard let stt = stt, phase == .finishing, !resolved, !tailStarted else { return }
        tailStarted = true
        let since = flushedAt.map { Int(Date().timeIntervalSince($0) * 1000) } ?? 0
        let cap = Tail.capMs(backlogMs: Tail.backlogMs(flushedMs: flushedMs, sinceFlushMs: since), maxMs: config.tailMs)
        Task { [weak self] in
            let text = await stt.finish()
            DispatchQueue.main.async { self?.resolve(final: text, timedOut: false) }
        }
        DispatchQueue.main.asyncAfter(deadline: .now() + .milliseconds(cap)) { [weak self] in
            guard let self = self, !self.resolved else { return }
            self.resolve(final: nil, timedOut: true)
        }
    }

    private func resolve(final: String?, timedOut: Bool) {
        guard !resolved else { return }
        resolved = true
        phase = .done
        // The final wins when it came back with words; then everything recognised so far; then the last partial.
        if let best = Tail.pick(final: final, best: stt?.bestText() ?? "", lastPartial: lastPartial) {
            Out.emit("final", [("id", id), ("text", best)])
        } else {
            Out.emit("cancelled", [("id", id), ("reason", "empty")])
        }
        if timedOut { stt?.cancel() }
        stt = nil
        ctl.sessionEnded(self)
    }
}

extension AVAudioPCMBuffer {
    func copied() -> AVAudioPCMBuffer? {
        guard let out = AVAudioPCMBuffer(pcmFormat: format, frameCapacity: frameLength) else { return nil }
        out.frameLength = frameLength
        let src = UnsafeMutableAudioBufferListPointer(mutableAudioBufferList)
        let dst = UnsafeMutableAudioBufferListPointer(out.mutableAudioBufferList)
        for i in 0..<min(src.count, dst.count) {
            if let s = src[i].mData, let d = dst[i].mData {
                memcpy(d, s, Int(min(src[i].mDataByteSize, dst[i].mDataByteSize)))
            }
        }
        return out
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// Owns the current hold, the sessions still waiting for a final, and the config.
// ---------------------------------------------------------------------------------------------------------------------
final class Controller {
    var config = Config()
    var terms: [String] = []
    var sttKind: SttKind = .none
    var simulate = false                // --stdin-only
    var nextSim: SimOptions?

    private var held: Session?
    private var finishing: [ObjectIdentifier: Session] = [:]
    /// After an abort (keypress/esc/cap) ignore the chord until it is released, so one hold is one session.
    private var suppressed = false

    var onConfigChanged: (() -> Void)?

    func apply(config new: Config) {
        let old = config
        config = new
        if !new.enabled || old.chord != new.chord { cancelAll("disabled") }
        onConfigChanged?()
    }

    func chordChanged(down: Bool) {
        if down {
            guard config.enabled, !suppressed, held == nil else { return }   // idempotent
            let s = Session(ctl: self, config: config, terms: terms, sim: simulate ? (nextSim ?? SimOptions()) : nil)
            nextSim = nil
            held = s
            s.begin()
        } else {
            suppressed = false
            guard let s = held else { return }
            held = nil
            finishing[ObjectIdentifier(s)] = s
            s.release()
        }
    }

    /// A key went down while the chord was held (Fn+Ctrl+arrow, Esc, ...).
    func keyDown(keyCode: Int) {
        // Not a real key press: a modifier (shift/control/option/command/caps/fn, codes 54-63) or the Globe key (179).
        // Some keyboards and macOS settings report Fn/Globe as a keyDown while the chord is held; aborting on that
        // would make Fn+Control end the moment it starts.
        if Controller.isModifierKey(keyCode) { return }
        guard let s = held else { return }
        held = nil; suppressed = true
        s.abort(keyCode == 53 ? "esc" : "keypress")
    }

    static func isModifierKey(_ code: Int) -> Bool { (54...63).contains(code) || code == 179 }

    func holdCapped(_ s: Session) {
        if held === s { held = nil; suppressed = true }
    }

    func cancelAll(_ reason: String) {
        if held != nil { suppressed = true }
        let all = [held].compactMap { $0 } + Array(finishing.values)
        held = nil
        for s in all { s.abort(reason) }
    }

    func sessionEnded(_ s: Session) {
        finishing.removeValue(forKey: ObjectIdentifier(s))
        if held === s { held = nil }
    }
}
