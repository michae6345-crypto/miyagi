import Foundation

// Pure unit tests for Tail.swift (no audio, no Speech, no key tap). Built and run by test-tail.sh (main.swift: the file with top-level code).
var failures = 0
func check(_ name: String, _ ok: Bool) {
    print((ok ? "PASS " : "FAIL ") + name)
    if !ok { failures += 1 }
}

/// One tail, the way Session runs it: the final the moment it comes, else at the cap the best text then.
/// changes: (ms after the tail began, the recognizer's whole text then). -> (ms the words went, was it the final, words).
func replay(textAtStart: String, changes: [(Int, String)], finalMs: Int?, finalText: String, backlogMs: Int = 0) -> (Int, Bool, String) {
    let cap = Tail.capMs(backlogMs: backlogMs)
    if let f = finalMs, f <= cap { return (f, true, Tail.pick(final: finalText, best: "", lastPartial: "") ?? "") }
    let best = changes.filter { $0.0 <= cap }.last?.1 ?? textAtStart
    return (cap, false, Tail.pick(final: nil, best: best, lastPartial: textAtStart) ?? "")
}

check("limits: 1000 ms warm cap, 1500 ms ceiling", Tail.maxMs == 1000 && Tail.ceilingMs == 1500)
check("the tailMs knob is kept within 300...1500", Tail.clamp(-5) == 300 && Tail.clamp(700) == 700 && Tail.clamp(5000) == 1500)
check("cap: 1000 ms warm; a flushed backlog adds a quarter of it, at most 1500",
      Tail.capMs(backlogMs: 0) == 1000 && Tail.capMs(backlogMs: 1200) == 1300 && Tail.capMs(backlogMs: 8000) == 1500
      && Tail.capMs(backlogMs: -50) == 1000 && Tail.capMs(backlogMs: 0, maxMs: 400) == 400)
check("backlog: flushed audio less the time since, never negative",
      Tail.backlogMs(flushedMs: 1500, sinceFlushMs: 0) == 1500 && Tail.backlogMs(flushedMs: 1500, sinceFlushMs: 400) == 1100
      && Tail.backlogMs(flushedMs: 300, sinceFlushMs: 2000) == 0)

// Measured (ACCURACY.md "Release tail"): the text at release lacks the end; the final comes about 65 ms later.
var r = replay(textAtStart: "why is my tensor flow", changes: [(30, "why is my tensor flow loss nan")], finalMs: 65,
               finalText: "Why is my TensorFlow loss NaN?")
check("warm, typical: the final goes the moment it comes (65 ms)", r.0 == 65 && r.1 && r.2 == "Why is my TensorFlow loss NaN?")

// A busy Mac: the last words come only with a 600 ms final. The first cut (300 ms flat) sent "...with".
r = replay(textAtStart: "how do I install scikit learn with", changes: [], finalMs: 600, finalText: "How do I install scikit-learn with pip?")
check("warm, the last word only in a 600 ms final: kept", r.1 && r.0 == 600 && r.2.hasSuffix("pip?"))

// A text that moved and then held still is not a reason to go early: the final can still add words (36 of 189 runs).
r = replay(textAtStart: "how do I", changes: [(40, "how do I enfor")], finalMs: 450, finalText: "How do I import numpy?")
check("warm, a settled partial that the final rewrites: the final wins", r.1 && r.2 == "How do I import numpy?")

// The final never comes in time: the best text at the cap, with what the partials brought during the tail.
r = replay(textAtStart: "what does this", changes: [(200, "what does this error mean")], finalMs: nil, finalText: "")
check("no final by the 1 s cap: the best text then", !r.1 && r.0 == 1000 && r.2 == "what does this error mean")

// Cold start: 2.4 s queued while the recognizer started, flushed at once: the cap grows to 1.6 s -> 1.5 s ceiling.
r = replay(textAtStart: "", changes: [], finalMs: 1250, finalText: "What is the difference between a list and a tuple?", backlogMs: 2400)
check("cold start: a 1250 ms final after the flush is waited for (the warm cap would have lost it)", r.1 && r.0 == 1250)
r = replay(textAtStart: "", changes: [], finalMs: 1250, finalText: "What is the difference between a list and a tuple?", backlogMs: 0)
check("(the same with no backlog: the 1 s cap comes first, with nothing to send)", !r.1 && r.0 == 1000 && r.2 == "")

check("the recognizer's final wins when it has words",
      Tail.pick(final: " how do I import numpy ", best: "how do I import", lastPartial: "how do I") == "how do I import numpy")
check("an empty final falls back to everything recognised so far",
      Tail.pick(final: "", best: "how do I import", lastPartial: "how do I") == "how do I import")
check("the cap came first (no final): the best text so far",
      Tail.pick(final: nil, best: "what is this error", lastPartial: "what is this") == "what is this error")
check("nothing from the recognizer object: the last partial",
      Tail.pick(final: nil, best: "", lastPartial: "what is this") == "what is this")
check("nothing worth sending: nil (cancelled empty)", Tail.pick(final: nil, best: " ", lastPartial: "a") == nil)
check("isMeaningful needs two letters or digits", isMeaningful("ok") && !isMeaningful("a.") && !isMeaningful(""))

exit(failures == 0 ? 0 : 1)
