import CoreGraphics
import Foundation
import ImageIO
import ScreenCaptureKit

// `capture`: grab one region of the screen for circle to ask, while the keys are still held.
//
//   main -> helper  {"cmd":"capture","id":"cap-1","rect":{"x":100,"y":80,"w":320,"h":200},"displayId":1,"margin":0.15}
//   helper -> main  {"type":"capture","id":"cap-1","path":"/.../miyagi-capture/cap-<pid>-<uuid>.jpg","w":1092,"h":683,
//                    "pxPerPoint":2.0,"rect":{"x":52,"y":50,"w":416,"h":260},"displayId":1,"ms":142}
//              or   {"type":"capture","id":"cap-1","error":"screen_denied","message":"...","ms":3}
//   helper -> main  {"type":"capture-warm","ok":true,"ms":180}   once per process, first chord-down (Capture.warm)
//
// rect: global screen points, top-left origin (Electron's screen space; the contract's ScreenRegion). displayId: the
// CGDirectDisplayID (Electron's Display.id). 0, a missing displayId, or a display that is gone (empty CGDisplayBounds)
// means the display under the box's center (CGGetDisplaysWithPoint), else the main display (CaptureMath.resolveDisplay).
// margin: 0 to 0.5 of the box added on every side. The answer's rect is the box that was really captured (margin added,
// clamped to the display, whole points) and its displayId the display really used: map crop pixels back with them.
//
// ScreenCaptureKit only (macOS 14+: SCScreenshotManager with SCStreamConfiguration.sourceRect). miyagi's own windows are
// left out (the parent process, this helper, any dev.sandhacks.miyagi* app, plus `excludePids`). The 15.2 rect API
// (captureImage(in:)) can't leave windows out, so it is not used. The image is scaled by ScreenCaptureKit so its long edge
// is at most 1092 px, then encoded as JPEG 0.82 into a 0600 file in a 0700 folder under the per-user temp dir. Each file
// is deleted 30 s after it is written (its own timer), or sooner: by the engine after reading it, or by
// {"cmd":"capture-release","id"} / {"cmd":"capture-release","path"} (main gave up on it). Files carry this helper's pid
// (cap-<pid>-<uuid>.jpg) and a helper only ever deletes its own, so the dev app and the packaged app running at once
// never delete each other's crop in flight. All but the newest few of its own are deleted on every capture; all of its
// own at startup and on quit, plus the files of a helper that is no longer running (and old cap-<uuid>.jpg past the TTL).
// Pixels are never logged. Screen Recording is only checked (CGPreflightScreenCaptureAccess), never requested here:
// without it the answer is error "screen_denied".
//
// --stdin-only: no screen at all. A gray image of the planned size is written instead (simDisplay {x,y,w,h,scale} in the
// command sets the fake display), so the protocol, the files and the cleanup are testable offline.

enum CaptureError: Error {
    case code(String, String)
}

enum CaptureFiles {
    /// Every file is deleted this long after it is written (a timer per file, not only on the next capture), so the last
    /// crop never sits in the temp folder while the helper idles. The consumer (the engine) deletes it sooner, after reading.
    static let defaultTTL: TimeInterval = 30
    static let keep = 8
    private static let lock = NSLock()
    /// Ask id -> the file written for it, until it is released, expires or is pruned.
    private static var byId: [String: String] = [:]
    /// Ids released before their capture finished: the capture is deleted as soon as it is written, never announced.
    private static var releasedEarly: [String] = []

    /// --stdin-only test knob: MIYAGI_CAPTURE_TTL_MS (50 ms to 30 s) so the expiry is testable without waiting.
    static var ttl: TimeInterval {
        if Capture.simulate, let v = ProcessInfo.processInfo.environment["MIYAGI_CAPTURE_TTL_MS"], let ms = Double(v), ms.isFinite {
            return min(max(ms, 50), defaultTTL * 1000) / 1000
        }
        return defaultTTL
    }

    /// The written file now belongs to `id`; it goes after `ttl` whatever happens next. false = `id` was already
    /// released (the file is deleted here and must not be announced).
    static func adopt(id: String, path: String) -> Bool {
        lock.lock()
        if let i = releasedEarly.firstIndex(of: id) {
            releasedEarly.remove(at: i)
            lock.unlock()
            unlink(path)
            return false
        }
        if let old = byId[id], old != path { unlink(old) }
        byId[id] = path
        lock.unlock()
        DispatchQueue.global(qos: .utility).asyncAfter(deadline: .now() + ttl) { expire(id: id, path: path) }
        return true
    }

    private static func expire(id: String, path: String) {
        lock.lock()
        if byId[id] == path { byId[id] = nil }
        lock.unlock()
        unlink(path)   // already gone (read by the engine, released, pruned): ENOENT, harmless
    }

    /// {"cmd":"capture-release","id"} or {"cmd":"capture-release","path"}: the consumer is done with it, or main gave
    /// up on it (timed out, answered late). An id not written yet is remembered, so its capture is deleted on arrival.
    /// A path is only honoured when it is one of ours: cap-<...>.jpg directly inside the capture folder.
    static func release(_ obj: [String: Any]) {
        if let id = obj["id"] as? String, CaptureMath.validId(id) {
            lock.lock()
            let path = byId.removeValue(forKey: id)
            if path == nil {
                releasedEarly.append(id)
                if releasedEarly.count > 32 { releasedEarly.removeFirst(releasedEarly.count - 32) }
            }
            lock.unlock()
            if let p = path { unlink(p) }
        }
        if let p = obj["path"] as? String, isOurs(p) {
            lock.lock()
            for (k, v) in byId where v == p { byId[k] = nil }
            lock.unlock()
            unlink(p)
        }
    }

    /// A capture file of this helper process: cap-<our pid>-<...>.jpg whose folder (symlinks resolved) is the capture folder.
    static func isOurs(_ p: String) -> Bool {
        guard p.hasPrefix("/"), p.count < 1024, !p.contains("/../"), !p.contains("/./") else { return false }
        let u = URL(fileURLWithPath: p)
        let name = u.lastPathComponent
        guard name.hasPrefix(prefix), name.hasSuffix(".jpg"), !name.contains("/") else { return false }
        return u.deletingLastPathComponent().resolvingSymlinksInPath().path == dir.resolvingSymlinksInPath().path
    }

    /// This process's file names start with this. Another helper (the dev app and the packaged app at once) has its own.
    static let prefix = "cap-\(getpid())-"

    /// The pid in cap-<pid>-<uuid>.jpg (7 dash-separated parts), nil for an old cap-<uuid>.jpg (6 parts) or anything else.
    static func ownerPid(_ name: String) -> pid_t? {
        let parts = name.split(separator: "-", omittingEmptySubsequences: false)
        guard parts.count == 7, parts[0] == "cap", (1...10).contains(parts[1].count),
              parts[1].allSatisfy({ $0.isASCII && $0.isNumber }), let n = Int32(parts[1]), n > 0 else { return nil }
        return n
    }

    /// Is a helper with this pid still running? (kill 0 only checks; EPERM = alive but not ours to signal.)
    static func alive(_ pid: pid_t) -> Bool {
        if pid == getpid() { return true }
        return kill(pid, 0) == 0 || errno == EPERM
    }

    static var dir: URL {
        if Capture.simulate, let d = ProcessInfo.processInfo.environment["MIYAGI_CAPTURE_DIR"], !d.isEmpty {
            return URL(fileURLWithPath: d, isDirectory: true)
        }
        return URL(fileURLWithPath: NSTemporaryDirectory(), isDirectory: true).appendingPathComponent("miyagi-capture", isDirectory: true)
    }

    /// The folder, 0700, a real directory owned by us (not a symlink someone planted).
    static func ensureDir() throws -> URL {
        let url = dir
        let path = url.path
        if mkdir(path, 0o700) != 0 && errno != EEXIST { throw CaptureError.code("failed", "could not make the capture folder") }
        var st = stat()
        guard lstat(path, &st) == 0, (st.st_mode & S_IFMT) == S_IFDIR, st.st_uid == getuid() else {
            throw CaptureError.code("failed", "the capture folder is not ours")
        }
        if (st.st_mode & 0o777) != 0o700 { chmod(path, 0o700) }
        return url
    }

    /// Every cap-*.jpg in the folder, any helper's. `mine` = only this process's (cap-<our pid>-...).
    static func files(mine: Bool = true) -> [(url: URL, name: String, date: Date)] {
        let fm = FileManager.default
        guard let names = try? fm.contentsOfDirectory(atPath: dir.path) else { return [] }
        return names.filter { $0.hasPrefix(mine ? prefix : "cap-") && $0.hasSuffix(".jpg") }.map { name in
            let u = dir.appendingPathComponent(name)
            let d = (try? fm.attributesOfItem(atPath: u.path)[.modificationDate] as? Date) ?? .distantPast
            return (u, name, d)
        }
    }

    /// Delete this helper's files past the TTL, then all but its newest `keepNewest`. Never another helper's files.
    static func prune(keepNewest: Int = keep - 1, now: Date = Date()) {
        let all = files().sorted { $0.date > $1.date }
        for (i, f) in all.enumerated() where i >= keepNewest || now.timeIntervalSince(f.date) > ttl {
            unlink(f.url.path)
        }
    }

    /// Startup, quit and SIGTERM: every file of this helper, and what a helper that is gone left behind (a pid that
    /// no longer runs, or an old cap-<uuid>.jpg past the TTL). A running helper's crops are never touched.
    static func purgeAll(now: Date = Date()) {
        lock.lock()
        byId.removeAll()
        lock.unlock()
        for f in files(mine: false) {
            let stale: Bool
            if f.name.hasPrefix(prefix) { stale = true }
            else if let pid = ownerPid(f.name) { stale = !alive(pid) }
            else { stale = now.timeIntervalSince(f.date) > defaultTTL }
            if stale { unlink(f.url.path) }
        }
    }

    /// A new 0600 file, created exclusively (never follows or reuses a path).
    static func write(_ data: Data) throws -> String {
        let d = try ensureDir()
        prune()
        let path = d.appendingPathComponent("\(prefix)\(UUID().uuidString.lowercased()).jpg").path
        let fd = open(path, O_WRONLY | O_CREAT | O_EXCL | O_NOFOLLOW, 0o600)
        guard fd >= 0 else { throw CaptureError.code("failed", "could not write the capture") }
        defer { close(fd) }
        fchmod(fd, 0o600)
        let ok = data.withUnsafeBytes { buf -> Bool in
            var off = 0
            while off < buf.count {
                let n = Darwin.write(fd, buf.baseAddress!.advanced(by: off), buf.count - off)
                if n <= 0 { return false }
                off += n
            }
            return true
        }
        if !ok { unlink(path); throw CaptureError.code("failed", "could not write the capture") }
        return path
    }
}

@available(macOS 12.3, *)
final class ShareableCache {
    static let shared = ShareableCache()
    private let lock = NSLock()
    private var content: SCShareableContent?
    private var at = Date.distantPast
    static let maxAge: TimeInterval = 10

    func get(fresh: Bool = false) async throws -> SCShareableContent {
        if !fresh, let c = cached() { return c }
        let c = try await SCShareableContent.excludingDesktopWindows(false, onScreenWindowsOnly: true)
        store(c)
        return c
    }

    private func store(_ c: SCShareableContent) {
        lock.lock(); defer { lock.unlock() }
        content = c
        at = Date()
    }

    private func cached() -> SCShareableContent? {
        lock.lock(); defer { lock.unlock() }
        guard let c = content, Date().timeIntervalSince(at) < ShareableCache.maxAge else { return nil }
        return c
    }
}

/// The once-per-process screenshot warm-up (Capture.warm): claimed by the first key-down, given back if it failed.
enum ScreenshotWarm {
    private static let lock = NSLock()
    private static var claimed = false

    static func claim() -> Bool {
        lock.lock(); defer { lock.unlock() }
        if claimed { return false }
        claimed = true
        return true
    }

    static func failed() {
        lock.lock(); defer { lock.unlock() }
        claimed = false
    }
}

enum Capture {
    static var simulate = false

    static func screenGranted() -> Bool { CGPreflightScreenCaptureAccess() }

    /// Key-down: fetch the shareable content now so the capture at circle-close skips it, and once per helper process
    /// take one tiny throwaway screenshot, because the first SCScreenshotManager.captureImage in a process is the slow
    /// one (it sets up the capture service). Never prompts: only runs once Screen Recording is granted. The warm-up
    /// image (16x16 points of a display) is dropped at once: never written, sent or logged. Its time goes to main as
    /// {"type":"capture-warm","ok","ms"}, which main logs next to each capture's ms. A failed warm-up is tried again
    /// on the next key-down.
    static func warm() {
        guard !simulate, screenGranted() else { return }
        if #available(macOS 14.0, *) {
            let first = ScreenshotWarm.claim()
            Task.detached {
                let started = Date()
                guard let content = try? await ShareableCache.shared.get() else {
                    if first { ScreenshotWarm.failed() }
                    return
                }
                guard first else { return }
                let ok = await warmScreenshot(content)
                if !ok { ScreenshotWarm.failed() }
                Out.emit("capture-warm", [("ok", ok), ("ms", Int(Date().timeIntervalSince(started) * 1000))])
            }
        }
    }

    @available(macOS 14.0, *)
    static func warmScreenshot(_ content: SCShareableContent) async -> Bool {
        guard let display = content.displays.first(where: { $0.displayID == CGMainDisplayID() }) ?? content.displays.first else {
            return false
        }
        let cfg = SCStreamConfiguration()
        cfg.sourceRect = CGRect(x: 0, y: 0, width: 16, height: 16)
        cfg.width = 16
        cfg.height = 16
        cfg.showsCursor = false
        let filter = SCContentFilter(display: display, excludingApplications: [], exceptingWindows: [])
        return (try? await SCScreenshotManager.captureImage(contentFilter: filter, configuration: cfg)) != nil
    }

    static func num(_ v: Any?) -> Double? {
        if let n = v as? NSNumber { return n.doubleValue }
        return nil
    }

    static func rect(_ v: Any?) -> CGRect? {
        guard let o = v as? [String: Any], let x = num(o["x"]), let y = num(o["y"]), let w = num(o["w"]), let h = num(o["h"]) else { return nil }
        let r = CGRect(x: x, y: y, width: w, height: h)
        return CaptureMath.finite(r) ? r : nil
    }

    static func rectJSON(_ r: CGRect) -> [String: Any] {
        ["x": Double(r.minX), "y": Double(r.minY), "w": Double(r.width), "h": Double(r.height)]
    }

    /// The display's frame in global points (top-left origin) and its pixels per point. nil = no such display.
    /// CoreGraphics only: handle() runs on the stdin reader thread, where AppKit (NSScreen) must not be touched. When
    /// the mode can't be read the scale is taken as 2: ScreenCaptureKit scales to the planned size either way, and the
    /// long edge stays capped at 1092.
    static func display(_ id: CGDirectDisplayID) -> (frame: CGRect, scale: Double)? {
        let frame = CGDisplayBounds(id)
        guard frame.width > 0, frame.height > 0 else { return nil }
        var scale = 0.0
        if let mode = CGDisplayCopyDisplayMode(id), mode.width > 0 { scale = Double(mode.pixelWidth) / Double(mode.width) }
        return (frame, scale.isFinite && scale > 0 ? scale : 2)
    }

    /// Every active display and its frame (CGGetActiveDisplayList + CGDisplayBounds), plus `requested` when it is online
    /// with a real frame but not in that list. CoreGraphics only, safe off the main thread.
    static func displays(including requested: CGDirectDisplayID) -> [DisplayFrame] {
        var ids = [CGDirectDisplayID](repeating: 0, count: 32)
        var count: UInt32 = 0
        var out: [DisplayFrame] = []
        if CGGetActiveDisplayList(UInt32(ids.count), &ids, &count) == .success {
            out = ids.prefix(Int(count)).map { DisplayFrame(id: $0, frame: CGDisplayBounds($0)) }
        }
        if requested != 0, !out.contains(where: { $0.id == requested }) {
            let f = CGDisplayBounds(requested)
            if f.width > 0, f.height > 0 { out.append(DisplayFrame(id: requested, frame: f)) }
        }
        return out
    }

    /// The display under a global point (CGGetDisplaysWithPoint), nil when none.
    static func displayUnder(_ p: CGPoint) -> CGDirectDisplayID? {
        var id: CGDirectDisplayID = 0
        var count: UInt32 = 0
        guard CGGetDisplaysWithPoint(p, 1, &id, &count) == .success, count > 0, id != 0 else { return nil }
        return id
    }

    static func handle(_ obj: [String: Any]) {
        let started = Date()
        guard let id = obj["id"] as? String, CaptureMath.validId(id) else { return }   // no id: nobody to answer
        func ms() -> Int { Int(Date().timeIntervalSince(started) * 1000) }
        func fail(_ code: String, _ message: String) {
            Out.emit("capture", [("id", id), ("error", code), ("message", message), ("ms", ms())])
        }
        guard let r = rect(obj["rect"]), r.width > 0, r.height > 0 else { return fail("bad_rect", "The circled box is empty.") }
        let margin = num(obj["margin"]) ?? 0
        // 0 (or no displayId) = "the display under the region": the app sends 0 when its layout has none.
        let displayNum = num(obj["displayId"]) ?? 0
        guard displayNum >= 0, displayNum <= Double(UInt32.max), displayNum == displayNum.rounded() else {
            return fail("no_display", "That display isn't connected.")
        }
        let requested = CGDirectDisplayID(displayNum)
        let extraPids = ((obj["excludePids"] as? [Any]) ?? []).compactMap { num($0) }.filter { $0 > 0 && $0 < 1e7 }.map { pid_t($0) }

        if simulate {
            // One fake display: simDisplay {x,y,w,h,scale,id}. Its id defaults to the requested one (1 when 0 was asked).
            let sd = rect(obj["simDisplay"]) ?? CGRect(x: 0, y: 0, width: 1512, height: 982)
            let so = obj["simDisplay"] as? [String: Any]
            let scale = num(so?["scale"]) ?? 2
            let simId = num(so?["id"]).flatMap { $0 > 0 && $0 <= Double(UInt32.max) ? UInt32($0) : nil } ?? (requested != 0 ? requested : 1)
            let displayID = CaptureMath.resolveDisplay(requested: requested, rect: r, displays: [DisplayFrame(id: simId, frame: sd)], main: simId)
            guard let plan = CaptureMath.plan(rect: r, margin: margin, display: sd, scale: scale) else {
                return fail("bad_rect", "The circled box is off the screen or too small.")
            }
            guard let img = gray(plan.width, plan.height) else { return fail("failed", "Couldn't make the test image.") }
            return finish(id: id, img: img, plan: plan, displayID: displayID, ms: ms, fail: fail, sim: true)
        }

        // 0, or a display whose bounds are empty (gone): the display under the box's center, then the main display.
        // The answer carries the display actually used.
        let displayID = CaptureMath.resolveDisplay(requested: requested, rect: r, displays: displays(including: requested),
                                                   main: CGMainDisplayID(), under: displayUnder)
        guard let disp = display(displayID) else { return fail("no_display", "That display isn't connected.") }
        guard let plan = CaptureMath.plan(rect: r, margin: margin, display: disp.frame, scale: disp.scale) else {
            return fail("bad_rect", "The circled box is off the screen or too small.")
        }
        guard screenGranted() else {
            return fail("screen_denied", "Screen Recording isn't on for miyagi, so it can't see what you circled.")
        }
        guard #available(macOS 14.0, *) else { return fail("unsupported", "Circle to ask needs macOS 14 or later.") }
        Task.detached {
            do {
                let img = try await grab(plan: plan, displayID: displayID, extraPids: extraPids)
                finish(id: id, img: img, plan: plan, displayID: displayID, ms: ms, fail: fail, sim: false)
            } catch CaptureError.code(let c, let m) {
                fail(c, m)
            } catch {
                let ns = error as NSError
                if ns.domain == SCStreamErrorDomain && ns.code == SCStreamError.userDeclined.rawValue {
                    fail("screen_denied", "Screen Recording isn't on for miyagi, so it can't see what you circled.")
                } else {
                    fail("failed", "The screen capture didn't work.")
                }
            }
        }
    }

    @available(macOS 14.0, *)
    static func grab(plan: CapturePlan, displayID: CGDirectDisplayID, extraPids: [pid_t]) async throws -> CGImage {
        var content = try await ShareableCache.shared.get()
        if !content.displays.contains(where: { $0.displayID == displayID }) {
            content = try await ShareableCache.shared.get(fresh: true)   // a display came or went since the warm-up
        }
        guard var display = content.displays.first(where: { $0.displayID == displayID }) else {
            throw CaptureError.code("no_display", "That display isn't connected.")
        }
        let own = Set([getpid(), getppid()] + extraPids)
        func ownApps(_ c: SCShareableContent) -> [SCRunningApplication] {
            c.applications.filter { own.contains($0.processID) || $0.bundleIdentifier.lowercased().hasPrefix("dev.sandhacks.miyagi") }
        }
        var apps = ownApps(content)
        // The cache (up to 10 s old, on-screen windows only) may predate the circle's ink window: miyagi was then not in
        // its app list and the ink would land in the crop. Ask once more, fresh, before capturing.
        if !apps.contains(where: { $0.processID == getppid() }) {
            content = try await ShareableCache.shared.get(fresh: true)
            guard let d = content.displays.first(where: { $0.displayID == displayID }) else {
                throw CaptureError.code("no_display", "That display isn't connected.")
            }
            display = d
            apps = ownApps(content)
        }
        if apps.isEmpty { log("capture: no miyagi window found to leave out of the crop") }   // never pixels or paths
        let filter = SCContentFilter(display: display, excludingApplications: apps, exceptingWindows: [])
        let cfg = SCStreamConfiguration()
        cfg.sourceRect = plan.local
        cfg.width = plan.width
        cfg.height = plan.height
        cfg.scalesToFit = true
        cfg.preservesAspectRatio = true
        cfg.captureResolution = .best
        cfg.showsCursor = false
        cfg.colorSpaceName = CGColorSpace.sRGB
        return try await SCScreenshotManager.captureImage(contentFilter: filter, configuration: cfg)
    }

    static func finish(id: String, img: CGImage, plan: CapturePlan, displayID: CGDirectDisplayID, ms: () -> Int,
                       fail: (String, String) -> Void, sim: Bool) {
        // ScreenCaptureKit scales to the configured size; this only runs if it ever hands back something else.
        guard let sized = resized(img, plan.width, plan.height), let data = jpeg(sized, quality: CaptureMath.jpegQuality) else {
            return fail("failed", "Couldn't encode the capture.")
        }
        do {
            let path = try CaptureFiles.write(data)
            guard CaptureFiles.adopt(id: id, path: path) else { return }   // released before it was ready: gone, unannounced
            var fields: [(String, Any)] = [("id", id), ("path", path), ("w", plan.width), ("h", plan.height),
                                           ("pxPerPoint", plan.pxPerPoint), ("rect", rectJSON(plan.global)),
                                           ("displayId", Int(displayID)), ("ms", ms())]
            if sim { fields.append(("sim", true)) }
            Out.emit("capture", fields)
        } catch CaptureError.code(let c, let m) {
            fail(c, m)
        } catch {
            fail("failed", "Couldn't save the capture.")
        }
    }

    static func resized(_ img: CGImage, _ w: Int, _ h: Int) -> CGImage? {
        if img.width == w && img.height == h { return img }
        guard let cs = CGColorSpace(name: CGColorSpace.sRGB),
              let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0, space: cs,
                                  bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return nil }
        ctx.interpolationQuality = .high
        ctx.draw(img, in: CGRect(x: 0, y: 0, width: w, height: h))
        return ctx.makeImage()
    }

    static func gray(_ w: Int, _ h: Int) -> CGImage? {
        guard let cs = CGColorSpace(name: CGColorSpace.sRGB),
              let ctx = CGContext(data: nil, width: w, height: h, bitsPerComponent: 8, bytesPerRow: 0, space: cs,
                                  bitmapInfo: CGImageAlphaInfo.noneSkipLast.rawValue) else { return nil }
        ctx.setFillColor(CGColor(gray: 0.5, alpha: 1))
        ctx.fill(CGRect(x: 0, y: 0, width: w, height: h))
        return ctx.makeImage()
    }

    /// JPEG with no metadata.
    static func jpeg(_ img: CGImage, quality: Double) -> Data? {
        let data = NSMutableData()
        guard let dest = CGImageDestinationCreateWithData(data, "public.jpeg" as CFString, 1, nil) else { return nil }
        CGImageDestinationAddImage(dest, img, [kCGImageDestinationLossyCompressionQuality: quality] as CFDictionary)
        guard CGImageDestinationFinalize(dest) else { return nil }
        return data as Data
    }
}
