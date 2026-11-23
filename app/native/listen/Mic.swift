import Foundation
import AVFoundation

/// Where audio buffers come from: the real microphone, or (tests only) a file.
protocol AudioSource: AnyObject {
    func start(onBuffer: @escaping (AVAudioPCMBuffer) -> Void) throws
    func stop()
}

enum MicError: Error { case noInput }

/// The default input device through AVAudioEngine. Buffers arrive on an audio thread in the device's own format;
/// the STT converts them. Never started unless microphone access is already granted (Session checks).
final class Mic: AudioSource {
    private let engine = AVAudioEngine()
    private var running = false

    func start(onBuffer: @escaping (AVAudioPCMBuffer) -> Void) throws {
        let input = engine.inputNode
        let format = input.outputFormat(forBus: 0)
        guard format.sampleRate > 0, format.channelCount > 0 else { throw MicError.noInput }
        input.installTap(onBus: 0, bufferSize: 4096, format: format) { buffer, _ in onBuffer(buffer) }
        engine.prepare()
        do { try engine.start() } catch { input.removeTap(onBus: 0); throw error }
        running = true
    }

    func stop() {
        guard running else { return }
        running = false
        engine.inputNode.removeTap(onBus: 0)
        engine.stop()
    }
}

/// Feeds an audio file as if it were the mic. Used by --transcribe-file and the _simulate test command.
/// With no file it produces silence-free nothing at all (an empty hold).
final class SimSource: AudioSource {
    private let file: String?
    private var stopped = false

    init(file: String?) { self.file = file }

    func start(onBuffer: @escaping (AVAudioPCMBuffer) -> Void) throws {
        guard let path = file else { return }
        DispatchQueue.global().async { [weak self] in
            do { try SimSource.feed(path: path, onBuffer: onBuffer, cancelled: { self?.stopped ?? true }) }
            catch { log("sim file failed: \(error)") }
        }
    }

    func stop() { stopped = true }

    /// Reads the file in 4096-frame chunks, like a mic would deliver them.
    static func feed(path: String, onBuffer: (AVAudioPCMBuffer) -> Void, cancelled: () -> Bool = { false }) throws {
        let f = try AVAudioFile(forReading: URL(fileURLWithPath: path))
        let fmt = f.processingFormat
        while f.framePosition < f.length, !cancelled() {
            guard let buf = AVAudioPCMBuffer(pcmFormat: fmt, frameCapacity: 4096) else { break }
            try f.read(into: buf, frameCount: 4096)
            if buf.frameLength == 0 { break }
            onBuffer(buf)
        }
    }
}
