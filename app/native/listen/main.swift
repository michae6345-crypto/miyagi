import Foundation
import AVFoundation
import CoreGraphics

// miyagi-listen: push-to-talk helper. Protocol: PUSH-TO-TALK.md (JSON lines on stdin/stdout).
//
//   miyagi-listen                         normal mode (key tap + mic + STT), spawned by miyagi's main process
//   miyagi-listen --stdin-only            no key tap, no mic; sessions are driven by {"cmd":"_simulate",...}
//   miyagi-listen --transcribe-file F [--terms a,b] [--locale en-US]
//                                         transcribe an audio file with the same Transcriber and print the final JSON
//   miyagi-listen --screens               print the displays' geometry (notch, safe area) as one JSON line and exit 0
//   miyagi-listen --windows --pid N | --owner NAME   print matching windows (layer, bounds, on-screen, z) as one JSON line and exit 0
//
// stdin also takes {"cmd":"capture",...}: one region of the screen as a JPEG file for circle to ask (Capture.swift).

setvbuf(stdout, nil, _IOLBF, 0)
signal(SIGPIPE, SIG_IGN)

let args = Array(CommandLine.arguments.dropFirst())
func argValue(_ name: String) -> String? {
    guard let i = args.firstIndex(of: name), i + 1 < args.count else { return nil }
    return args[i + 1]
}
let termsArg = (argValue("--terms") ?? "").split(separator: ",").map { $0.trimmingCharacters(in: .whitespaces) }.filter { !$0.isEmpty }
let localeArg = argValue("--locale") ?? "en-US"
Transcriber.forceModule = argValue("--module")

// MARK: --screens (NSScreen geometry only: no permissions, no tap, no mic)
if args.contains("--screens") { Screens.run() }

// MARK: --windows (CGWindowList entries for given pids / owners: layer, bounds, on-screen; read-only, no permissions)
if args.contains("--windows") { Windows.run(args) }

// MARK: --probe-input (fresh read of the Input Monitoring grant: preflight only, never prompts)
if args.contains("--probe-input") { print(CGPreflightListenEventAccess() ? "granted" : "denied"); exit(0) }

// MARK: --transcribe-file (offline self-test: no mic, no key tap, no prompts)

if let path = argValue("--transcribe-file") {
    Task {
        let started = Date()
        let locale = Locale(identifier: localeArg)
        do {
            let kind = await Transcriber.detect(locale: locale)
            guard kind == .speechanalyzer else {
                Out.error("no_stt", "--transcribe-file needs the SpeechAnalyzer path (macOS 26); detected \(kind.rawValue)")
                exit(2)
            }
            let stt = try Transcriber.makeSession(kind: kind, locale: locale, terms: termsArg)
            try await stt.start { _ in }
            try SimSource.feed(path: path, onBuffer: { stt.feed($0) })
            let text = await stt.finish()
            var module = "speech"
            if #available(macOS 26, *), let a = stt as? AnalyzerSession { module = a.moduleName }
            Out.emit("final", [("id", "file"), ("text", text), ("stt", kind.rawValue), ("module", module), ("terms", termsArg),
                               ("ms", Int(Date().timeIntervalSince(started) * 1000))])
            exit(0)
        } catch SttError.assetsMissing {
            Out.error("assets_missing", "The speech model for \(localeArg) isn't installed."); exit(3)
        } catch {
            Out.error("no_stt", "\(error)"); exit(1)
        }
    }
    RunLoop.main.run()
}

// MARK: normal / --stdin-only mode

let stdinOnly = args.contains("--stdin-only")
let ctl = Controller()
ctl.simulate = stdinOnly
Capture.simulate = stdinOnly
CaptureFiles.purgeAll()   // a crash or kill can leave captures behind: none survive a restart
ctl.config.locale = localeArg
if stdinOnly { ctl.config.enabled = true }   // tests don't need a config line first; "config" still overrides

let tap = KeyTap()
var lastTapError = ""

/// Create or tear down the tap to match config + permission. Creating a tap without Input Monitoring can make macOS
/// prompt, so it is only attempted once CGPreflightListenEventAccess says yes.
func syncTap() {
    if stdinOnly { return }
    tap.chord = ctl.config.chord
    if !ctl.config.enabled { tap.stop(); lastTapError = ""; return }
    if tap.isRunning { return }
    if Perms.inputStatus() != "granted" {
        if lastTapError != "input_denied" {
            lastTapError = "input_denied"
            Out.error("input_denied", "Input Monitoring isn't granted for miyagi, so the push-to-talk shortcut can't be heard.")
        }
        return
    }
    if tap.start() { lastTapError = "" }
    else if lastTapError != "tap_failed" {
        lastTapError = "tap_failed"
        Out.error("tap_failed", "macOS wouldn't create the key listener.")
    }
}

tap.onChord = { down in
    if down { Capture.warm() }   // circle to ask: the capture at circle-close skips the window list fetch
    ctl.chordChanged(down: down)
}
tap.onKeyDown = { code in ctl.keyDown(keyCode: code) }
ctl.onConfigChanged = { syncTap(); announceReady() }
Perms.onChange = { syncTap() }
Perms.onTick = { if ctl.config.enabled && !tap.isRunning && Perms.inputStatus() == "granted" { syncTap() } }

/// `ready` goes out when the speech engine, locale or chord differs from the last one announced (or when forced), so a
/// repeated `config` line can never turn into a ready/config ping-pong with the app.
var lastReadyKey = ""
func announceReady(force: Bool = false) {
    Task {
        let locale = Locale(identifier: ctl.config.locale)
        let kind = await Transcriber.detect(locale: locale)
        DispatchQueue.main.async {
            ctl.sttKind = kind
            let key = "\(kind.rawValue)/\(ctl.config.locale)/\(ctl.config.chord.rawValue)"
            Perms.locale = ctl.config.locale
            Perms.refresh(force: true)
            if !force && key == lastReadyKey { return }
            lastReadyKey = key
            Out.emit("ready", [("stt", kind.rawValue), ("locale", ctl.config.locale), ("chord", ctl.config.chord.rawValue)])
        }
    }
}

func handle(_ obj: [String: Any]) {
    guard let cmd = obj["cmd"] as? String else { return }
    switch cmd {
    case "config":
        var c = ctl.config
        if let v = obj["enabled"] as? Bool { c.enabled = v }
        if let v = obj["chord"] as? String, let ch = Chord(rawValue: v) { c.chord = ch }
        if let v = obj["minHoldMs"] as? Int { c.minHoldMs = max(0, v) }
        if let v = obj["maxHoldMs"] as? Int { c.maxHoldMs = max(1, v) }
        if let v = obj["finalWaitMs"] as? Int { c.finalWaitMs = max(0, v) }   // test knob
        if let v = obj["locale"] as? String, !v.isEmpty { c.locale = v }
        ctl.apply(config: c)
    case "context":
        let terms = (obj["terms"] as? [String] ?? []).map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
        ctl.terms = Array(terms.prefix(100))
    case "permissions":
        switch obj["request"] as? String {
        case "input": Perms.requestInput()
        case "mic": Perms.requestMic()
        case "assets":
            let loc = Locale(identifier: ctl.config.locale)
            Task {
                Perms.refresh(force: true)
                await Transcriber.requestAssets(locale: loc)
                DispatchQueue.main.async { Perms.refresh(force: true); announceReady() }
            }
        default: Perms.refresh(force: true)
        }
    case "cancel":
        ctl.cancelAll("esc")
    case "capture":
        Capture.handle(obj)   // circle to ask: one region of the screen as a JPEG file (Capture.swift)
    case "quit":
        shutdown()
    case "_simulate":
        guard stdinOnly else { return }
        var sim = SimOptions()
        sim.fakeText = obj["fakeText"] as? String
        sim.finalDelayMs = obj["finalDelayMs"] as? Int ?? 0
        sim.file = obj["file"] as? String
        switch obj["state"] as? String {
        case "down": ctl.nextSim = sim; ctl.chordChanged(down: true)
        case "up": ctl.chordChanged(down: false)
        case "key": ctl.keyDown(keyCode: obj["code"] as? Int ?? 0)   // code 53 = Esc
        default: break
        }
    default:
        break
    }
}

Perms.restartForPermission = {
    ctl.cancelAll("disabled")
    tap.stop()
    exit(75)   // the app respawns the helper
}

func shutdown() -> Never {
    ctl.cancelAll("disabled")
    tap.stop()
    CaptureFiles.purgeAll()
    exit(0)
}

// stdin: one JSON object per line; EOF means the parent is gone.
Thread.detachNewThread {
    while let line = readLine(strippingNewline: true) {
        guard !line.isEmpty, let data = line.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: data) as? [String: Any] else { continue }
        DispatchQueue.main.async { handle(obj) }
    }
    DispatchQueue.main.async { shutdown() }
}

var signalSources: [DispatchSourceSignal] = []
for sig in [SIGTERM, SIGINT] {
    signal(sig, SIG_IGN)
    let src = DispatchSource.makeSignalSource(signal: sig, queue: .main)
    src.setEventHandler { shutdown() }
    src.resume()
    signalSources.append(src)
}

announceReady()
Perms.startPolling()
RunLoop.main.run()
