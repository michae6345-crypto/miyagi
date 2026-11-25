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
    private static var probing = false
    private static var ticks = 0
    static var onTick: (() -> Void)?
    /// Poll every ~3 s so the app sees a switch flip in System Settings (granted or revoked). Re-reading the two
    /// statuses is cheap; the full refresh (which also asks the speech assets) runs only when something changed or
    /// something is still not granted.
    static func startPolling() {
        timer = Timer.scheduledTimer(withTimeInterval: 3, repeats: true) { _ in
            ticks += 1
            if !allGood || micStatus() != current.mic || inputStatus() != current.input { refresh() }
            onTick?()   // retry a key listener that couldn't be created yet
            if inputStatus() != "granted" && ticks % 3 == 0 { probeInput() }
        }
    }

    /// CGPreflightListenEventAccess can keep saying "denied" in a process that started before the grant. When Input
    /// Monitoring is off for us, ask a fresh copy of this binary; if it says granted, restart: the app respawns the
    /// helper and the new process hears the shortcut. Never prompts (preflight only).
    private static func probeInput() {
        if probing || CommandLine.arguments.contains("--stdin-only") { return }
        probing = true
        let p = Process()
        p.executableURL = URL(fileURLWithPath: CommandLine.arguments[0])
        p.arguments = ["--probe-input"]
        let pipe = Pipe()
        p.standardOutput = pipe
        p.standardError = FileHandle.nullDevice
        p.terminationHandler = { _ in
            let out = String(data: pipe.fileHandleForReading.readDataToEndOfFile(), encoding: .utf8) ?? ""
            DispatchQueue.main.async {
                probing = false
                if out.contains("granted") && inputStatus() != "granted" {
                    log("Input Monitoring is granted for a fresh process: restarting to pick it up")
                    restartForPermission?()
                }
            }
        }
        do { try p.run() } catch { probing = false }
    }
    static var restartForPermission: (() -> Void)?
}
