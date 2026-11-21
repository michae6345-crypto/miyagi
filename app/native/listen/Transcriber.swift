import Foundation
import AVFoundation
import Speech

enum SttKind: String { case speechanalyzer, sfspeech, none }

enum SttError: Error { case assetsMissing, unavailable, failed(String) }

/// One streaming transcription. feed() is thread safe and non-blocking.
protocol SttSession: AnyObject {
    func start(onPartial: @escaping (String) -> Void) async throws
    func feed(_ buffer: AVAudioPCMBuffer)
    /// End the input and return the final text (may take a moment).
    func finish() async -> String
    /// Everything recognised so far, final or not.
    func bestText() -> String
    func cancel()
}

func joinText(_ parts: [String]) -> String {
    parts.joined(separator: " ").split(whereSeparator: { $0.isWhitespace }).joined(separator: " ")
}

enum Transcriber {
    /// Which engine this Mac will use for `locale`. Nothing here prompts.
    static func detect(locale: Locale) async -> SttKind {
        if #available(macOS 26, *) {
            if SpeechTranscriber.isAvailable, await SpeechTranscriber.supportedLocale(equivalentTo: locale) != nil {
                return .speechanalyzer
            }
        }
        if let r = SFSpeechRecognizer(locale: locale), r.isAvailable, r.supportsOnDeviceRecognition { return .sfspeech }
        return .none
    }

    static func makeSession(kind: SttKind, locale: Locale, terms: [String]) throws -> SttSession {
        switch kind {
        case .speechanalyzer:
            if #available(macOS 26, *) { return AnalyzerSession(locale: locale, terms: terms) }
            throw SttError.unavailable
        case .sfspeech:
            guard let r = SFSpeechRecognizer(locale: locale), r.supportsOnDeviceRecognition else { throw SttError.unavailable }
            return SFSession(recognizer: r, terms: terms)
        case .none:
            throw SttError.unavailable
        }
    }

    /// "installed" | "missing" | "downloading". On macOS 13-15 the on-device recognizer is the "asset".
    static func assetStatus(locale: Locale) async -> String {
        if #available(macOS 26, *) {
            guard let supported = await SpeechTranscriber.supportedLocale(equivalentTo: locale) else { return "missing" }
            if await isInstalled(supported) { return "installed" }
            if installing { return "downloading" }
            let t = SpeechTranscriber(locale: supported, transcriptionOptions: [], reportingOptions: [], attributeOptions: [])
            return await AssetInventory.status(forModules: [t]) == .downloading ? "downloading" : "missing"
        }
        if let r = SFSpeechRecognizer(locale: locale), r.supportsOnDeviceRecognition,
           SFSpeechRecognizer.authorizationStatus() == .authorized { return "installed" }
        return "missing"
    }

    static var installing = false
    /// Test knob (--module speech|dictation) for measuring both modules in --transcribe-file.
    static var forceModule: String?

    /// installedLocales is the reliable signal: AssetInventory.status can say "supported" for a locale that is
    /// installed (seen on macOS 26.6 for en-US).
    @available(macOS 26, *)
    static func isInstalled(_ locale: Locale) async -> Bool {
        let want = locale.identifier(.bcp47)
        return await SpeechTranscriber.installedLocales.contains { $0.identifier(.bcp47) == want }
    }

    /// Only called from an explicit `permissions` request. Downloads the locale's speech model if needed.
    static func requestAssets(locale: Locale) async {
        if #available(macOS 26, *) {
            guard let supported = await SpeechTranscriber.supportedLocale(equivalentTo: locale) else { return }
            let t = SpeechTranscriber(locale: supported, transcriptionOptions: [], reportingOptions: [.volatileResults], attributeOptions: [])
            installing = true
            defer { installing = false }
            do {
                if let req = try await AssetInventory.assetInstallationRequest(supporting: [t]) {
                    try await req.downloadAndInstall()
                }
            } catch { log("asset install failed: \(error)") }
        } else {
            await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
                SFSpeechRecognizer.requestAuthorization { _ in c.resume() }
            }
        }
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// macOS 26: SpeechAnalyzer + SpeechTranscriber
// ---------------------------------------------------------------------------------------------------------------------
@available(macOS 26.0, *)
final class AnalyzerSession: SttSession {
    private let locale: Locale
    private let terms: [String]
    private var analyzer: SpeechAnalyzer?
    private var targetFormat: AVAudioFormat?
    private var continuation: AsyncStream<AnalyzerInput>.Continuation?
    private var resultsTask: Task<Void, Never>?

    private let lock = NSLock()
    private var finals: [String] = []
    private var volatile = ""
    private var converter: AVAudioConverter?
    private var converterFrom: AVAudioFormat?

    init(locale: Locale, terms: [String]) { self.locale = locale; self.terms = terms }

    /// Which module did the work: "speech" (SpeechTranscriber) or "dictation" (DictationTranscriber).
    private(set) var moduleName = "speech"

    private func consume(_ text: String, final isFinal: Bool, onPartial: (String) -> Void) {
        lock.lock()
        if isFinal { finals.append(text); volatile = "" } else { volatile = text }
        let all = joinText(finals + [volatile])
        lock.unlock()
        onPartial(all)
    }

    func start(onPartial: @escaping (String) -> Void) async throws {
        guard let supported = await SpeechTranscriber.supportedLocale(equivalentTo: locale) else { throw SttError.unavailable }
        guard await Transcriber.isInstalled(supported) else { throw SttError.assetsMissing }

        // Measured on macOS 26.6 (ACCURACY.md): SpeechTranscriber ignores AnalysisContext.contextualStrings, while
        // DictationTranscriber honours them ("matplotlib", "DataFrame", "TensorFlow" come out right). So: with terms
        // use DictationTranscriber when its model is installed; otherwise SpeechTranscriber (better punctuation).
        var useDictation = false
        if !terms.isEmpty, Transcriber.forceModule != "speech" {
            if let dl = await DictationTranscriber.supportedLocale(equivalentTo: locale),
               await DictationTranscriber.installedLocales.contains(where: { $0.identifier(.bcp47) == dl.identifier(.bcp47) }) {
                useDictation = true
            }
        }
        if Transcriber.forceModule == "dictation" { useDictation = true }

        let module: any SpeechModule
        let a: SpeechAnalyzer
        let stream: AsyncStream<AnalyzerInput>
        let cont: AsyncStream<AnalyzerInput>.Continuation
        (stream, cont) = AsyncStream.makeStream(of: AnalyzerInput.self)
        if useDictation {
            let loc = await DictationTranscriber.supportedLocale(equivalentTo: locale) ?? supported
            let d = DictationTranscriber(locale: loc, contentHints: [], transcriptionOptions: [.punctuation],
                                         reportingOptions: [.volatileResults], attributeOptions: [])
            module = d; moduleName = "dictation"
            resultsTask = Task { [weak self] in
                do {
                    for try await r in d.results { self?.consume(String(r.text.characters), final: r.isFinal, onPartial: onPartial) }
                } catch { log("results ended: \(error)") }
            }
        } else {
            let t = SpeechTranscriber(locale: supported, transcriptionOptions: [], reportingOptions: [.volatileResults], attributeOptions: [])
            module = t
            resultsTask = Task { [weak self] in
                do {
                    for try await r in t.results { self?.consume(String(r.text.characters), final: r.isFinal, onPartial: onPartial) }
                } catch { log("results ended: \(error)") }
            }
        }
        a = SpeechAnalyzer(modules: [module])
        if !terms.isEmpty {
            let ctx = AnalysisContext()
            ctx.contextualStrings[.general] = terms
            try await a.setContext(ctx)
        }
        targetFormat = await SpeechAnalyzer.bestAvailableAudioFormat(compatibleWith: [module])
        continuation = cont
        analyzer = a
        try await a.start(inputSequence: stream)
    }

    func feed(_ buffer: AVAudioPCMBuffer) {
        guard let target = targetFormat, let cont = continuation else { return }
        if buffer.format == target { cont.yield(AnalyzerInput(buffer: buffer)); return }
        lock.lock(); defer { lock.unlock() }
        if converter == nil || converterFrom != buffer.format {
            converter = AVAudioConverter(from: buffer.format, to: target)
            converterFrom = buffer.format
        }
        guard let conv = converter else { return }
        let ratio = target.sampleRate / buffer.format.sampleRate
        let cap = AVAudioFrameCount(Double(buffer.frameLength) * ratio) + 64
        guard let out = AVAudioPCMBuffer(pcmFormat: target, frameCapacity: cap) else { return }
        var supplied = false
        var err: NSError?
        let status = conv.convert(to: out, error: &err) { _, outStatus in
            if supplied { outStatus.pointee = .noDataNow; return nil }
            supplied = true; outStatus.pointee = .haveData; return buffer
        }
        if status != .error, out.frameLength > 0 { cont.yield(AnalyzerInput(buffer: out)) }
    }

    func finish() async -> String {
        continuation?.finish()
        if let a = analyzer { try? await a.finalizeAndFinishThroughEndOfInput() }
        await resultsTask?.value
        return bestText()
    }

    func bestText() -> String {
        lock.lock(); defer { lock.unlock() }
        return joinText(finals + [volatile])
    }

    func cancel() {
        continuation?.finish()
        resultsTask?.cancel()
        if let a = analyzer { Task { await a.cancelAndFinishNow() } }
    }
}

// ---------------------------------------------------------------------------------------------------------------------
// macOS 13-15: SFSpeechRecognizer, on device only
// ---------------------------------------------------------------------------------------------------------------------
final class SFSession: SttSession {
    private let recognizer: SFSpeechRecognizer
    private let terms: [String]
    private var request: SFSpeechAudioBufferRecognitionRequest?
    private var task: SFSpeechRecognitionTask?
    private let lock = NSLock()
    private var text = ""
    private var done = false
    private var waiters: [CheckedContinuation<Void, Never>] = []

    init(recognizer: SFSpeechRecognizer, terms: [String]) { self.recognizer = recognizer; self.terms = terms }

    func start(onPartial: @escaping (String) -> Void) async throws {
        let req = SFSpeechAudioBufferRecognitionRequest()
        req.shouldReportPartialResults = true
        req.requiresOnDeviceRecognition = true
        req.taskHint = .dictation
        if !terms.isEmpty { req.contextualStrings = terms }
        request = req
        task = recognizer.recognitionTask(with: req) { [weak self] result, error in
            guard let self = self else { return }
            if let r = result {
                self.lock.lock(); self.text = r.bestTranscription.formattedString; self.lock.unlock()
                onPartial(r.bestTranscription.formattedString)
            }
            if error != nil || result?.isFinal == true { self.markDone() }
        }
    }

    private func markDone() {
        lock.lock(); done = true; let w = waiters; waiters = []; lock.unlock()
        for c in w { c.resume() }
    }

    func feed(_ buffer: AVAudioPCMBuffer) { request?.append(buffer) }

    func finish() async -> String {
        request?.endAudio()
        await withCheckedContinuation { (c: CheckedContinuation<Void, Never>) in
            lock.lock()
            if done { lock.unlock(); c.resume() } else { waiters.append(c); lock.unlock() }
        }
        return bestText()
    }

    func bestText() -> String { lock.lock(); defer { lock.unlock() }; return text }

    func cancel() { task?.cancel(); markDone() }
}

// ---------------------------------------------------------------------------------------------------------------------
// Test double (protocol tests only)
// ---------------------------------------------------------------------------------------------------------------------
final class FakeStt: SttSession {
    private let text: String
    private let finalDelayMs: Int
    private var cancelled = false
    init(text: String, finalDelayMs: Int) { self.text = text; self.finalDelayMs = finalDelayMs }

    func start(onPartial: @escaping (String) -> Void) async throws {
        if !text.isEmpty { onPartial(text) }
    }
    func feed(_ buffer: AVAudioPCMBuffer) {}
    func finish() async -> String {
        if finalDelayMs > 0 { try? await Task.sleep(nanoseconds: UInt64(finalDelayMs) * 1_000_000) }
        return text
    }
    func bestText() -> String { text }
    func cancel() { cancelled = true }
}
