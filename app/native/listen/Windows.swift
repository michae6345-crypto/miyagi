import CoreGraphics
import Foundation

// `miyagi-listen --windows [--pid N]... [--owner NAME]...`: one JSON line listing the on-screen-server's window entries
// that match any --pid or --owner (owner name compared case-insensitively, exact), then exit 0. Read-only diagnostics for
// main/features/islandDiag.ts: it answers "which layer is miyagi's overlay at, where is it, is it on screen, and what sits
// in front of it". CGWindowListCopyWindowInfo gives owner, pid, layer, bounds, alpha and on-screen state of every window
// WITHOUT Screen Recording permission; only window titles (kCGWindowName) need it, and this mode never reads them.
// No filter is an error (it would dump every window of every app). No prompts, no key tap, no mic, no UI.
//
//   {"windows":[{"id":41,"pid":812,"owner":"miyagi","layer":1000,"bounds":{"x":0,"y":0,"w":1728,"h":1117},
//                "onscreen":true,"alpha":1,"z":0}]}
//
// `z` is the entry's index in the system's list, which is ordered front to back for on-screen windows (0 = frontmost),
// so comparing two apps' `z` (same layer) tells who is drawn above whom. Bounds are CG's: points, origin top left of the
// primary display.

enum Windows {
    static func run(_ args: [String]) -> Never {
        var pids = Set<Int>()
        var owners = Set<String>()
        var i = 0
        while i < args.count {
            if args[i] == "--pid", i + 1 < args.count, let p = Int(args[i + 1]) { pids.insert(p); i += 1 }
            else if args[i] == "--owner", i + 1 < args.count { owners.insert(args[i + 1].lowercased()); i += 1 }
            i += 1
        }
        if pids.isEmpty && owners.isEmpty {
            FileHandle.standardError.write(Data("windows: pass at least one --pid N or --owner NAME\n".utf8))
            exit(2)
        }
        let raw = (CGWindowListCopyWindowInfo([.optionAll], kCGNullWindowID) as? [[String: Any]]) ?? []
        var list: [[String: Any]] = []
        for (z, w) in raw.enumerated() {
            let pid = (w[kCGWindowOwnerPID as String] as? NSNumber)?.intValue ?? -1
            let owner = (w[kCGWindowOwnerName as String] as? String) ?? ""
            guard pids.contains(pid) || owners.contains(owner.lowercased()) else { continue }
            let b = (w[kCGWindowBounds as String] as? [String: Any]) ?? [:]
            func n(_ k: String) -> Double { (b[k] as? NSNumber)?.doubleValue ?? 0 }
            list.append([
                "id": (w[kCGWindowNumber as String] as? NSNumber)?.intValue ?? -1,
                "pid": pid,
                "owner": owner,
                "layer": (w[kCGWindowLayer as String] as? NSNumber)?.intValue ?? 0,
                "bounds": ["x": n("X"), "y": n("Y"), "w": n("Width"), "h": n("Height")],
                "onscreen": (w[kCGWindowIsOnscreen as String] as? NSNumber)?.boolValue ?? false,
                "alpha": (w[kCGWindowAlpha as String] as? NSNumber)?.doubleValue ?? 1,
                "z": z
            ])
        }
        if let data = try? JSONSerialization.data(withJSONObject: ["windows": list], options: [.sortedKeys]),
           let text = String(data: data, encoding: .utf8) {
            print(text)
            exit(0)
        }
        FileHandle.standardError.write(Data("windows: could not encode\n".utf8))
        exit(1)
    }
}
