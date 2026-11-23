import Foundation

// ---------------------------------------------------------------------------------------------------------------------
// The release tail (pure: no audio, no Speech, no clock; unit-tested by test-tail.sh, measured by measure-tail.sh).
//
// On release the helper ends the recognizer's input and waits for its final; the final goes out the moment it comes.
// Only if it has not come by the cap does the best text so far go instead:
//
//   cap = maxMs (1000 ms), plus a quarter of the audio that was queued while the recognizer was starting and flushed at
//         once just before the tail (a cold start), at most ceilingMs (1500 ms, the old fixed wait).
//
// Why not send early on a quiet or settled text (measured offline, ACCURACY.md "Release tail"): SpeechAnalyzer's final
// came 62 to 68 ms after release (median; at most 140 ms) on 189 runs, so waiting for it costs nothing. But its text is
// behind the audio until then (incomplete at release in 187 of 189 runs), and in 36 runs the final still added or fixed
// words that no partial had. Replayed on a Mac 3 to 10 times slower after release, every early rule lost words that
// waiting for the final kept: a flat 300 ms tail (the first cut of this lane) lost 8 to 606 of 606 words, "300 ms, then
// once the text held still 150 ms" lost 8 to 108; "the final, else the cap" lost at most 1 up to 8x, 8 at 10x warm
// (0 after a cold-start flush, whose cap is longer).
// The app's safety net (features/ptt/tail.ts) waits ceilingMs + 400 ms, so it never races this tail.
// ---------------------------------------------------------------------------------------------------------------------
enum Tail {
    /** The cap while the recognizer was ready before release (warm). */
    static let maxMs = 1000
    /** The longest a tail can be (a cold-start flush); features/ptt/tail.ts HELPER_TAIL_MAX_MS mirrors it. */
    static let ceilingMs = 1500
    /** The shortest cap the `tailMs` test knob may set. */
    static let floorMs = 300

    /// The cap for this tail. backlogMs: audio flushed into the recognizer at once so recently that it may still be
    /// working through it (0 when it was ready before release). maxMs: the warm cap (Config.tailMs).
    static func capMs(backlogMs: Int, maxMs: Int = Tail.maxMs) -> Int {
        min(ceilingMs, clamp(maxMs) + max(0, backlogMs) / 4)
    }

    /// The audio still to work through: what was flushed, less the time since (the recognizer runs faster than real
    /// time, so this over-estimates, which only waits longer).
    static func backlogMs(flushedMs: Int, sinceFlushMs: Int) -> Int { max(0, flushedMs - max(0, sinceFlushMs)) }

    /// A configured warm cap (the `tailMs` test knob), kept within floorMs...ceilingMs.
    static func clamp(_ ms: Int) -> Int { min(max(ms, floorMs), ceilingMs) }

    /// The text to send, or nil when there is nothing worth sending (the session then ends `cancelled empty`).
    /// final: what the recognizer's finish() returned (nil when the cap came first).
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
