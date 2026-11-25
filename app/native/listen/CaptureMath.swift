import CoreGraphics
import Foundation

// Pure sizing math for the `capture` command (Capture.swift). No AppKit, no ScreenCaptureKit, no I/O, so test.sh compiles
// it with test-capture-math.swift and runs the checks without touching the screen.
//
// Spaces: `rect` and `display` are global screen POINTS with a TOP-LEFT origin (CG's space, which is also Electron's
// screen space and the contract's ScreenRegion space). `local` is the same box relative to the display's top-left corner,
// which is what SCStreamConfiguration.sourceRect wants.

struct CapturePlan: Equatable {
    /// The box that is captured, in global points (after the margin, clamped to the display, snapped to whole points).
    let global: CGRect
    /// `global` relative to the display's top-left corner (sourceRect).
    let local: CGRect
    /// Output size in pixels. The long edge is at most `maxEdge`, never more than the display's own pixels.
    let width: Int
    let height: Int
    /// Output pixels per point along x (width / global.width). A crop pixel px maps back to global.x + px / pxPerPoint.
    let pxPerPoint: Double
}

/// A display's id (CGDirectDisplayID) and frame in global points, top-left origin (CGDisplayBounds).
struct DisplayFrame {
    let id: UInt32
    let frame: CGRect
}

enum CaptureMath {
    /// 1092 px on the long edge: the API's documented 1:1 size (1092x1092) that it sends as is, never resized. A full
    /// 1092x1092 crop is about 1,590 tokens (w * h / 750); a wider or taller crop is fewer.
    static let maxEdge = 1092
    static let jpegQuality = 0.82
    /// Smallest box worth sending, in points (a dot of ink is not a question about anything).
    static let minPoints: CGFloat = 4
    static let maxMargin = 0.5

    static func finite(_ r: CGRect) -> Bool {
        [r.origin.x, r.origin.y, r.size.width, r.size.height].allSatisfy { $0.isFinite }
    }

    /// Plan one capture. nil = nothing sensible to capture (empty or non-finite box, box off the display, bad display).
    static func plan(rect: CGRect, margin: Double = 0, display: CGRect, scale: Double, maxEdge: Int = maxEdge) -> CapturePlan? {
        guard finite(rect), finite(display), rect.width > 0, rect.height > 0, display.width > 0, display.height > 0,
              scale.isFinite, scale > 0, maxEdge > 0 else { return nil }
        let m = margin.isFinite ? min(max(margin, 0), maxMargin) : 0
        let padded = rect.insetBy(dx: -rect.width * CGFloat(m), dy: -rect.height * CGFloat(m))
        let clipped = padded.intersection(display)
        guard !clipped.isNull, !clipped.isEmpty else { return nil }
        // Whole points: sourceRect is then exact, and the box the app is told about is the box that was captured.
        let g = clipped.integral.intersection(display)
        guard !g.isNull, g.width >= minPoints, g.height >= minPoints else { return nil }
        let nativeW = Double(g.width) * scale
        let nativeH = Double(g.height) * scale
        let k = min(1.0, Double(maxEdge) / max(nativeW, nativeH))
        let w = min(maxEdge, max(1, Int((nativeW * k).rounded())))
        let h = min(maxEdge, max(1, Int((nativeH * k).rounded())))
        let local = g.offsetBy(dx: -display.minX, dy: -display.minY)
        return CapturePlan(global: g, local: local, width: w, height: h, pxPerPoint: Double(w) / Double(g.width))
    }

    /// Which display to capture. The requested id when it names a display with a real frame. Otherwise (0, which the
    /// app sends for "the display under the region", or a display that is gone): the display under the box's center
    /// (`under`: CGGetDisplaysWithPoint in the helper; the frames when nil or when it finds none), then the display the
    /// box overlaps most (a box whose center hangs off every screen), then `main`. The answer's displayId is this id.
    static func resolveDisplay(requested: UInt32, rect: CGRect, displays: [DisplayFrame], main: UInt32,
                               under: ((CGPoint) -> UInt32?)? = nil) -> UInt32 {
        func usable(_ id: UInt32) -> Bool {
            id != 0 && displays.contains { $0.id == id && finite($0.frame) && $0.frame.width > 0 && $0.frame.height > 0 }
        }
        if usable(requested) { return requested }
        guard finite(rect) else { return main }
        let c = CGPoint(x: rect.midX, y: rect.midY)
        if let u = under?(c), usable(u) { return u }
        if let d = displays.first(where: { usable($0.id) && $0.frame.contains(c) }) { return d.id }
        func area(_ d: DisplayFrame) -> CGFloat {
            let i = d.frame.intersection(rect)
            return i.isNull ? 0 : i.width * i.height
        }
        if let best = displays.filter({ usable($0.id) && area($0) > 0 }).max(by: { area($0) < area($1) }) { return best.id }
        return main
    }

    /// A crop pixel back to a global screen point. Not called by the helper: it pins the formula the engine uses for
    /// [DRAW:x,y,r] (shared/capture_file.py crop_to_screen), tested in test-capture-math.swift. Clamped to the crop.
    static func toScreen(_ p: CapturePlan, px: Double, py: Double) -> CGPoint {
        let x = min(max(px, 0), Double(p.width))
        let y = min(max(py, 0), Double(p.height))
        return CGPoint(x: Double(p.global.minX) + x * Double(p.global.width) / Double(p.width),
                       y: Double(p.global.minY) + y * Double(p.global.height) / Double(p.height))
    }

    /// An ask id: a short token (same rule as the app's pttProtocol isId).
    static func validId(_ s: String) -> Bool {
        !s.isEmpty && s.count <= 64 && s.unicodeScalars.allSatisfy {
            CharacterSet.alphanumerics.contains($0) && $0.isASCII || "_.:-".unicodeScalars.contains($0)
        }
    }
}
