import AppKit
import ApplicationServices
import CoreGraphics
import Foundation

// `miyagi-listen --screens`: one JSON line with the geometry of every display, then exit 0. Reads NSScreen (and two permission preflights, below) only: no
// permissions, no key tap, no mic, no prompts. main/notch.ts turns it into the notch rect (display.id == NSScreenNumber).
//
//   {"screens":[{"id":1,"frame":{"x":0,"y":0,"w":1512,"h":982},"visible":{...},"safeTop":32,"auxLeft":661,"auxRight":661,
//                "scale":2,"builtin":true}]}
//
// Rects are NSScreen's own (points, origin at the bottom left of the primary display). auxLeft / auxRight are the widths of
// the two menu-bar areas beside the camera housing (null when the display has none).
//
// `perms` (additive): Screen Recording and Accessibility as THIS fresh process reads them, preflight only (never a
// prompt). macOS answers for the process it holds responsible, which is miyagi when miyagi spawned us. main/permissions.ts
// compares it with its own reads: a long-running process keeps saying "denied" for Screen Recording until it relaunches,
// so "granted" here and "denied" there means "switched on in System Settings, restart miyagi to use it".
//   "perms":{"screen":"granted"|"denied","accessibility":"granted"|"denied"}

enum Screens {
    static func rect(_ r: NSRect) -> [String: Any] {
        ["x": Double(r.origin.x), "y": Double(r.origin.y), "w": Double(r.size.width), "h": Double(r.size.height)]
    }

    static func run() -> Never {
        var list: [[String: Any]] = []
        for s in NSScreen.screens {
            guard let num = s.deviceDescription[NSDeviceDescriptionKey("NSScreenNumber")] as? NSNumber else { continue }
            let id = num.uint32Value
            var safeTop = 0.0
            var left: Any = NSNull()
            var right: Any = NSNull()
            if #available(macOS 12.0, *) {
                safeTop = Double(s.safeAreaInsets.top)
                if let l = s.auxiliaryTopLeftArea { left = Double(l.width) }
                if let r = s.auxiliaryTopRightArea { right = Double(r.width) }
            }
            list.append([
                "id": Int(id),
                "frame": rect(s.frame),
                "visible": rect(s.visibleFrame),
                "safeTop": safeTop,
                "auxLeft": left,
                "auxRight": right,
                "scale": Double(s.backingScaleFactor),
                "builtin": CGDisplayIsBuiltin(id) != 0
            ])
        }
        let perms: [String: Any] = [
            "screen": CGPreflightScreenCaptureAccess() ? "granted" : "denied",
            "accessibility": AXIsProcessTrusted() ? "granted" : "denied"
        ]
        let obj: [String: Any] = ["screens": list, "perms": perms]
        if let data = try? JSONSerialization.data(withJSONObject: obj, options: [.sortedKeys]),
           let text = String(data: data, encoding: .utf8) {
            print(text)
            exit(0)
        }
        FileHandle.standardError.write(Data("screens: could not encode\n".utf8))
        exit(1)
    }
}
