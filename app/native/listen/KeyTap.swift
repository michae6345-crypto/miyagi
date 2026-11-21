import Foundation
import CoreGraphics

/// The listen-only key tap. It never swallows or alters an event. The callback stays trivial: it computes whether the
/// chord is down and forwards changes and keyDowns to the Controller (same thread, the main run loop).
final class KeyTap {
    var chord: Chord = .fnControl
    var onChord: ((Bool) -> Void)?
    var onKeyDown: ((Int) -> Void)?

    private var port: CFMachPort?
    private var source: CFRunLoopSource?
    fileprivate var chordDown = false

    var isRunning: Bool { port != nil }

    /// Exactly the chord's modifiers and no other (caps lock and the numeric-pad flag are ignored).
    static func isChord(_ flags: CGEventFlags, _ chord: Chord) -> Bool {
        let relevant: CGEventFlags = [.maskSecondaryFn, .maskControl, .maskAlternate, .maskShift, .maskCommand]
        let present = flags.intersection(relevant)
        switch chord {
        case .fnControl: return present == [.maskSecondaryFn, .maskControl]
        case .controlOption: return present == [.maskControl, .maskAlternate]
        }
    }

    /// Idempotent. Returns false when the tap couldn't be created (no Input Monitoring access, or the system refused).
    @discardableResult
    func start() -> Bool {
        if port != nil { return true }
        let mask: CGEventMask = (1 << CGEventType.flagsChanged.rawValue)
            | (1 << CGEventType.keyDown.rawValue)
            | (1 << CGEventType.keyUp.rawValue)
        let refcon = Unmanaged.passUnretained(self).toOpaque()
        guard let p = CGEvent.tapCreate(tap: .cgSessionEventTap, place: .headInsertEventTap, options: .listenOnly,
                                        eventsOfInterest: mask, callback: keyTapCallback, userInfo: refcon) else { return false }
        port = p
        source = CFMachPortCreateRunLoopSource(kCFAllocatorDefault, p, 0)
        CFRunLoopAddSource(CFRunLoopGetMain(), source, .commonModes)
        CGEvent.tapEnable(tap: p, enable: true)
        chordDown = false
        return true
    }

    func stop() {
        guard let p = port else { return }
        CGEvent.tapEnable(tap: p, enable: false)
        if let s = source { CFRunLoopRemoveSource(CFRunLoopGetMain(), s, .commonModes) }
        CFMachPortInvalidate(p)
        port = nil; source = nil
        if chordDown { chordDown = false; onChord?(false) }
    }

    fileprivate func reenable() {
        if let p = port { CGEvent.tapEnable(tap: p, enable: true) }
        // Events were dropped while the tap was off: resync the chord from the live modifier state.
        let flags = CGEventSource.flagsState(.combinedSessionState)
        update(flags)
    }

    fileprivate func update(_ flags: CGEventFlags) {
        let now = KeyTap.isChord(flags, chord)
        if now != chordDown { chordDown = now; onChord?(now) }
    }

    fileprivate func handle(type: CGEventType, event: CGEvent) {
        switch type {
        case .tapDisabledByTimeout, .tapDisabledByUserInput:
            reenable()
        case .flagsChanged:
            update(event.flags)
        case .keyDown:
            if chordDown { onKeyDown?(Int(event.getIntegerValueField(.keyboardEventKeycode))) }
        default:
            break  // keyUp: observed, nothing to do
        }
    }
}

private func keyTapCallback(proxy: CGEventTapProxy, type: CGEventType, event: CGEvent, refcon: UnsafeMutableRawPointer?) -> Unmanaged<CGEvent>? {
    if let refcon = refcon {
        Unmanaged<KeyTap>.fromOpaque(refcon).takeUnretainedValue().handle(type: type, event: event)
    }
    return Unmanaged.passUnretained(event)
}
