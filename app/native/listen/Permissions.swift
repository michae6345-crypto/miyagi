import Foundation
import AVFoundation
import CoreGraphics

/// Permission status and (only on an explicit `permissions` command) requests. Reading status never prompts.
enum Perms {
    static func micStatus() -> String {
        switch AVCaptureDevice.authorizationStatus(for: .audio) {
        case .authorized: return "granted"
        case .notDetermined: return "undetermined"
        default: return "denied"
        }
    }

    static func inputStatus() -> String { CGPreflightListenEventAccess() ? "granted" : "denied" }

    static func requestMic() {
        AVCaptureDevice.requestAccess(for: .audio) { _ in DispatchQueue.main.async { Perms.refresh() } }
    }

    static func requestInput() {
        _ = CGRequestListenEventAccess()
        DispatchQueue.main.async { Perms.refresh() }
    }

    // MARK: state + change events

    private static var last = ""
    static var current: (mic: String, input: String, assets: String) = ("undetermined", "denied", "missing")
    static var locale = "en-US"
    static var onChange: (() -> Void)?

    /// Re-reads everything and emits a `perm` event when it differs from the last one (or when `force`).
    static func refresh(force: Bool = false) {
        let mic = micStatus(), input = inputStatus()
        let loc = Locale(identifier: locale)
        Task {
            let assets = await Transcriber.assetStatus(locale: loc)
            DispatchQueue.main.async {
                current = (mic, input, assets)
                let key = "\(mic)/\(input)/\(assets)"
                if force || key != last {
                    last = key
                    Out.emit("perm", [("mic", mic), ("input", input), ("assets", assets)])
                    onChange?()
                }
            }
        }
    }

    static var allGood: Bool { current.mic == "granted" && current.input == "granted" && current.assets == "installed" }

    private static var timer: Timer?
    /// Poll every ~3 s while something is not granted, so the app sees the switch flip in System Settings.
    static func startPolling() {
        timer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { _ in
            if !allGood { refresh() }
        }
    }
}
