import CoreGraphics
import Foundation

// Pure checks for CaptureMath.swift (no screen, no permissions). test.sh compiles this with CaptureMath.swift:
//   xcrun swiftc -parse-as-library CaptureMath.swift test-capture-math.swift -o <tmp> && <tmp>

@main
enum CaptureMathTests {
    static var failed: [String] = []

    static func check(_ name: String, _ ok: Bool, _ detail: @autoclosure () -> String = "") {
        print((ok ? "PASS " : "FAIL ") + name + (ok ? "" : "  \(detail())"))
        if !ok { failed.append(name) }
    }

    static func main() {
        let mac = CGRect(x: 0, y: 0, width: 1512, height: 982)

        // Small box on a 2x display: native pixels, no upscaling.
        if let p = CaptureMath.plan(rect: CGRect(x: 100, y: 80, width: 300, height: 200), display: mac, scale: 2) {
            check("small box keeps native pixels", p.width == 600 && p.height == 400 && p.pxPerPoint == 2, "\(p)")
            check("local == global on the primary display", p.local == p.global, "\(p)")
        } else { check("small box plans", false) }

        // Big box: long edge capped at 1092, aspect kept.
        if let p = CaptureMath.plan(rect: CGRect(x: 0, y: 0, width: 1200, height: 600), display: mac, scale: 2) {
            check("long edge capped at 1092", p.width == 1092 && p.height == 546, "\(p)")
            check("pxPerPoint = w / points", abs(p.pxPerPoint - 1092.0 / 1200.0) < 1e-9, "\(p.pxPerPoint)")
        } else { check("big box plans", false) }

        // Tall box: the height is the long edge.
        if let p = CaptureMath.plan(rect: CGRect(x: 10, y: 10, width: 300, height: 900), display: mac, scale: 2) {
            check("tall box: height capped", p.height == 1092 && p.width == 364, "\(p)")
        } else { check("tall box plans", false) }

        // Never over 1092 for any size.
        var over = 0
        for w in stride(from: 5, through: 1512, by: 37) {
            for h in stride(from: 5, through: 982, by: 41) {
                if let p = CaptureMath.plan(rect: CGRect(x: 0, y: 0, width: w, height: h), display: mac, scale: 2),
                   max(p.width, p.height) > CaptureMath.maxEdge || p.width < 1 || p.height < 1 { over += 1 }
            }
        }
        check("no plan exceeds 1092 or goes under 1 px", over == 0, "\(over) bad")

        // Margin grows the box, then the display clamps it.
        if let p = CaptureMath.plan(rect: CGRect(x: 100, y: 100, width: 200, height: 100), margin: 0.15, display: mac, scale: 2) {
            check("15% margin on each side", p.global == CGRect(x: 70, y: 85, width: 260, height: 130), "\(p.global)")
        } else { check("margin plans", false) }
        if let p = CaptureMath.plan(rect: CGRect(x: -50, y: 900, width: 200, height: 200), display: mac, scale: 2) {
            check("clamped to the display", p.global == CGRect(x: 0, y: 900, width: 150, height: 82), "\(p.global)")
        } else { check("clamp plans", false) }
        if let p = CaptureMath.plan(rect: CGRect(x: 0, y: 0, width: 100, height: 100), margin: 9, display: mac, scale: 1) {
            check("margin capped at 0.5", p.global == CGRect(x: 0, y: 0, width: 150, height: 150), "\(p.global)")
        } else { check("big margin plans", false) }

        // Fractional points snap outward to whole points.
        if let p = CaptureMath.plan(rect: CGRect(x: 10.4, y: 20.6, width: 99.2, height: 50.1), display: mac, scale: 2) {
            check("snapped to whole points", p.global == CGRect(x: 10, y: 20, width: 100, height: 51), "\(p.global)")
        } else { check("fractional plans", false) }

        // A second display to the left (negative origin) and above: local is relative to its top-left.
        let left = CGRect(x: -1920, y: -200, width: 1920, height: 1080)
        if let p = CaptureMath.plan(rect: CGRect(x: -1000, y: 0, width: 400, height: 300), display: left, scale: 1) {
            check("second display: local offset", p.local == CGRect(x: 920, y: 200, width: 400, height: 300), "\(p.local)")
            check("1x display: 1 px per point", p.width == 400 && p.height == 300 && p.pxPerPoint == 1, "\(p)")
        } else { check("second display plans", false) }

        // Rejections.
        check("empty box rejected", CaptureMath.plan(rect: CGRect(x: 0, y: 0, width: 0, height: 10), display: mac, scale: 2) == nil)
        check("tiny box rejected", CaptureMath.plan(rect: CGRect(x: 0, y: 0, width: 2, height: 2), display: mac, scale: 2) == nil)
        check("off-display box rejected", CaptureMath.plan(rect: CGRect(x: 3000, y: 0, width: 100, height: 100), display: mac, scale: 2) == nil)
        check("NaN box rejected", CaptureMath.plan(rect: CGRect(x: CGFloat.nan, y: 0, width: 100, height: 100), display: mac, scale: 2) == nil)
        check("bad scale rejected", CaptureMath.plan(rect: CGRect(x: 0, y: 0, width: 100, height: 100), display: mac, scale: 0) == nil)

        // Crop pixels back to screen points.
        if let p = CaptureMath.plan(rect: CGRect(x: 0, y: 0, width: 1200, height: 600), display: mac, scale: 2) {
            let c = CaptureMath.toScreen(p, px: 546, py: 273)
            check("crop center maps to the box center", abs(c.x - 600) < 1e-6 && abs(c.y - 300) < 1e-6, "\(c)")
            let o = CaptureMath.toScreen(p, px: -40, py: 99999)
            check("toScreen clamps to the crop", o.x == 0 && abs(o.y - 600) < 1e-6, "\(o)")
        }

        // Which display: displayId 0 (the app's "the display under the region") on a second display with a negative
        // origin, a display that is gone, and boxes that hang off the screens.
        let displays = [DisplayFrame(id: 1, frame: mac), DisplayFrame(id: 2, frame: left)]
        let onLeft = CGRect(x: -1000, y: 0, width: 400, height: 300)
        let id0 = CaptureMath.resolveDisplay(requested: 0, rect: onLeft, displays: displays, main: 1)
        check("displayId 0 -> the display under the box (negative origin)", id0 == 2, "\(id0)")
        if let d = displays.first(where: { $0.id == id0 }), let p = CaptureMath.plan(rect: onLeft, display: d.frame, scale: 1) {
            check("displayId 0: planned on that display", p.local == CGRect(x: 920, y: 200, width: 400, height: 300), "\(p.local)")
            let c = CaptureMath.toScreen(p, px: 200, py: 150)
            check("displayId 0: crop center maps back onto the second display", c == CGPoint(x: -800, y: 150), "\(c)")
        } else { check("displayId 0 plans", false) }
        check("displayId 0 uses `under` first (CGGetDisplaysWithPoint)",
              CaptureMath.resolveDisplay(requested: 0, rect: onLeft, displays: displays, main: 1, under: { _ in 2 }) == 2)
        check("`under` finding nothing falls back to the frames",
              CaptureMath.resolveDisplay(requested: 0, rect: onLeft, displays: displays, main: 1, under: { _ in nil }) == 2)
        check("a display that is gone -> the one under the box",
              CaptureMath.resolveDisplay(requested: 7, rect: onLeft, displays: displays, main: 1) == 2)
        check("an empty frame counts as gone",
              CaptureMath.resolveDisplay(requested: 3, rect: onLeft, displays: displays + [DisplayFrame(id: 3, frame: .zero)], main: 1) == 2)
        check("a connected display that was asked for is kept",
              CaptureMath.resolveDisplay(requested: 1, rect: onLeft, displays: displays, main: 1) == 1)
        check("displayId 0 on the main display -> main",
              CaptureMath.resolveDisplay(requested: 0, rect: CGRect(x: 100, y: 80, width: 300, height: 200), displays: displays, main: 1) == 1)
        check("center off every screen -> the display the box overlaps most",
              CaptureMath.resolveDisplay(requested: 0, rect: CGRect(x: -100, y: -300, width: 140, height: 160), displays: displays, main: 1) == 2)
        check("box off every screen -> main",
              CaptureMath.resolveDisplay(requested: 0, rect: CGRect(x: 5000, y: 5000, width: 10, height: 10), displays: displays, main: 1) == 1)
        check("NaN box -> main",
              CaptureMath.resolveDisplay(requested: 0, rect: CGRect(x: CGFloat.nan, y: 0, width: 10, height: 10), displays: displays, main: 1) == 1)
        if let p = CaptureMath.plan(rect: CGRect(x: 70, y: 85, width: 260, height: 130), display: mac, scale: 2) {
            let c = CaptureMath.toScreen(p, px: 0, py: 0)
            check("crop origin maps to the box origin", c == CGPoint(x: 70, y: 85), "\(c)")
        }

        // Ids.
        check("ids: token ok", CaptureMath.validId("cap-1.a:b_c"))
        check("ids: empty, spaces, slash, too long rejected",
              !CaptureMath.validId("") && !CaptureMath.validId("a b") && !CaptureMath.validId("../x") && !CaptureMath.validId(String(repeating: "a", count: 65))
              && !CaptureMath.validId("é"))

        print(failed.isEmpty ? "\nALL PASSED" : "\n\(failed.count) FAILED: \(failed.joined(separator: ", "))")
        exit(failed.isEmpty ? 0 : 1)
    }
}
