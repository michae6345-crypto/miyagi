import Foundation

// ---------------------------------------------------------------------------------------------------------------------
// The release tail (pure: no audio, no Speech, no clock; unit-tested by test-tail.sh).
//
// Before: on release the helper ended the recognizer's input and waited for its final, up to finalWaitMs = 1500 ms.
// Now: it waits at most `Tail.maxMs` (300 ms) after release (or after the recognizer is ready, if that is later), then
// sends the best text it has: the recognizer's final if it came back with words, else everything recognised so far
// (finals + the volatile partial), else the last partial it emitted. The app has the same rule (features/ptt/tail.ts).
// ---------------------------------------------------------------------------------------------------------------------
enum Tail {
    /** The longest the words wait after release. */
    static let maxMs = 300

    /** A configured tail, kept within 0...maxMs. */
    static func clamp(_ ms: Int) -> Int { min(max(ms, 0), maxMs) }

    /// The text to send, or nil when there is nothing worth sending (the session then ends `cancelled empty`).
    /// final: what the recognizer's finish() returned (nil when the tail ran out first).
    /// best: everything recognised so far. lastPartial: the last partial emitted.
    static func pick(final: String?, best: String, lastPartial: String) -> String? {
        for candidate in [final ?? "", best, lastPartial] {
            let t = candidate.trimmingCharacters(in: .whitespacesAndNewlines)
            if isMeaningful(t) { return t }
        }
        return nil
    }
}

/// True when the text is worth sending: at least two letters or digits.
func isMeaningful(_ text: String) -> Bool {
    text.unicodeScalars.filter { CharacterSet.alphanumerics.contains($0) }.count >= 2
}
