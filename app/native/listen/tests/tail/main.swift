import Foundation

// Pure unit tests for Tail.swift (no audio, no Speech, no key tap). Built and run by test-tail.sh (main.swift: the file with top-level code).
var failures = 0
func check(_ name: String, _ ok: Bool) {
    print((ok ? "PASS " : "FAIL ") + name)
    if !ok { failures += 1 }
}

check("tail is at most 300 ms", Tail.maxMs == 300)
check("clamp keeps 0...300", Tail.clamp(-5) == 0 && Tail.clamp(120) == 120 && Tail.clamp(300) == 300 && Tail.clamp(1500) == 300)
check("the recognizer's final wins when it has words",
      Tail.pick(final: " how do I import numpy ", best: "how do I import", lastPartial: "how do I") == "how do I import numpy")
check("an empty final falls back to everything recognised so far",
      Tail.pick(final: "", best: "how do I import", lastPartial: "how do I") == "how do I import")
check("the tail ran out (no final): the best text so far",
      Tail.pick(final: nil, best: "what is this error", lastPartial: "what is this") == "what is this error")
check("nothing from the recognizer object: the last partial",
      Tail.pick(final: nil, best: "", lastPartial: "what is this") == "what is this")
check("nothing worth sending: nil (cancelled empty)", Tail.pick(final: nil, best: " ", lastPartial: "a") == nil)
check("isMeaningful needs two letters or digits", isMeaningful("ok") && !isMeaningful("a.") && !isMeaningful(""))

exit(failures == 0 ? 0 : 1)
