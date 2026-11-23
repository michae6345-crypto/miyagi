import AppKit
import CoreGraphics
import Foundation
import ImageIO
import ScreenCaptureKit

// `capture`: grab one region of the screen for circle to ask, while the keys are still held.
//
//   main -> helper  {"cmd":"capture","id":"cap-1","rect":{"x":100,"y":80,"w":320,"h":200},"displayId":1,"margin":0.15}
//   helper -> main  {"type":"capture","id":"cap-1","path":"/.../miyagi-capture/cap-<uuid>.jpg","w":1092,"h":683,
//                    "pxPerPoint":2.0,"rect":{"x":52,"y":50,"w":416,"h":260},"displayId":1,"ms":142}
//              or   {"type":"capture","id":"cap-1","error":"screen_denied","message":"...","ms":3}
//
// rect: global screen points, top-left origin (Electron's screen space; the contract's ScreenRegion). displayId: the
// CGDirectDisplayID (Electron's Display.id). margin: 0 to 0.5 of the box added on every side. The answer's rect is the
// box that was really captured (margin added, clamped to the display, whole points): map crop pixels back with it.
//
// ScreenCaptureKit only (macOS 14+: SCScreenshotManager with SCStreamConfiguration.sourceRect). miyagi's own windows are
// left out (the parent process, this helper, any dev.sandhacks.miyagi* app, plus `excludePids`). The 15.2 rect API
// (captureImage(in:)) can't leave windows out, so it is not used. The image is scaled by ScreenCaptureKit so its long edge
// is at most 1092 px, then encoded as JPEG 0.82 into a 0600 file in a 0700 folder under the per-user temp dir. Files
// older than 2 minutes, and all but the newest few, are deleted on every capture; all of them at startup and on quit.
// Pixels are never logged. Screen Recording is only checked (CGPreflightScreenCaptureAccess), never requested here:
// without it the answer is error "screen_denied".
//
// --stdin-only: no screen at all. A gray image of the planned size is written instead (simDisplay {x,y,w,h,scale} in the
// command sets the fake display), so the protocol, the files and the cleanup are testable offline.

enum CaptureError: Error {
    case code(String, String)
}

enum CaptureFiles {
    static let ttl: TimeInterval = 120
    static let keep = 8

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

    static func files() -> [(url: URL, date: Date)] {
        let fm = FileManager.default
        guard let names = try? fm.contentsOfDirectory(atPath: dir.path) else { return [] }
        return names.filter { $0.hasPrefix("cap-") && $0.hasSuffix(".jpg") }.map { name in
            let u = dir.appendingPathComponent(name)
            let d = (try? fm.attributesOfItem(atPath: u.path)[.modificationDate] as? Date) ?? .distantPast
            return (u, d)
        }
    }

    /// Delete files past the TTL, then all but the newest `keepNewest`.
    static func prune(keepNewest: Int = keep - 1, now: Date = Date()) {
        let all = files().sorted { $0.date > $1.date }
        for (i, f) in all.enumerated() where i >= keepNewest || now.timeIntervalSince(f.date) > ttl {
            unlink(f.url.path)
        }
    }

    static func purgeAll() { for f in files() { unlink(f.url.path) } }

    /// A new 0600 file, created exclusively (never follows or reuses a path).
    static func write(_ data: Data) throws -> String {
        let d = try ensureDir()
        prune()
        let path = d.appendingPathComponent("cap-\(UUID().uuidString.lowercased()).jpg").path
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

enum Capture {
    static var simulate = false

    static func screenGranted() -> Bool { CGPreflightScreenCaptureAccess() }

    /// Key-down: fetch the shareable content now so the capture at circle-close skips it. Never prompts.
    static func warm() {
        guard !simulate, screenGranted() else { return }
        if #available(macOS 14.0, *) {
            Task.detached { _ = try? await ShareableCache.shared.get() }
        }
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
    static func display(_ id: CGDirectDisplayID) -> (frame: CGRect, scale: Double)? {
        let frame = CGDisplayBounds(id)
        guard frame.width > 0, frame.height > 0 else { return nil }
        var scale = 0.0
        if let mode = CGDisplayCopyDisplayMode(id), mode.width > 0 { scale = Double(mode.pixelWidth) / Double(mode.width) }
        if !(scale > 0) {
            scale = NSScreen.screens.first {
                ($0.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber)?.uint32Value == id
            }.map { Double($0.backingScaleFactor) } ?? 2
        }
        return (frame, scale)
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
        let displayNum = num(obj["displayId"]) ?? Double(CGMainDisplayID())
        guard displayNum >= 0, displayNum <= Double(UInt32.max), displayNum == displayNum.rounded() else {
            return fail("no_display", "That display isn't connected.")
        }
        let displayID = CGDirectDisplayID(displayNum)
        let extraPids = ((obj["excludePids"] as? [Any]) ?? []).compactMap { num($0) }.filter { $0 > 0 && $0 < 1e7 }.map { pid_t($0) }

        if simulate {
            let sd = rect(obj["simDisplay"]) ?? CGRect(x: 0, y: 0, width: 1512, height: 982)
            let scale = num((obj["simDisplay"] as? [String: Any])?["scale"]) ?? 2
            guard let plan = CaptureMath.plan(rect: r, margin: margin, display: sd, scale: scale) else {
                return fail("bad_rect", "The circled box is off the screen or too small.")
            }
            guard let img = gray(plan.width, plan.height) else { return fail("failed", "Couldn't make the test image.") }
            return finish(id: id, img: img, plan: plan, displayID: displayID, ms: ms, fail: fail, sim: true)
        }

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
        guard let display = content.displays.first(where: { $0.displayID == displayID }) else {
            throw CaptureError.code("no_display", "That display isn't connected.")
        }
        let own = Set([getpid(), getppid()] + extraPids)
        let apps = content.applications.filter {
            own.contains($0.processID) || $0.bundleIdentifier.lowercased().hasPrefix("dev.sandhacks.miyagi")
        }
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
