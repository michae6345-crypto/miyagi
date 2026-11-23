# miyagi-listen: accuracy on technical questions

Measured Nov 21 2026 on macOS 26.6 (Apple silicon), en-US model, by `native/listen/test.sh --accuracy-only`.
Audio is synthetic: `say -o` (default voice, one clean speaker, no room noise), 15 phrases in `phrases.tsv`, 91 words.
Each file goes through `miyagi-listen --transcribe-file`, which feeds the same Transcriber the live mic uses
(AVAudioConverter to the analyzer format, volatile results, finalize). Word accuracy = 1 - word error rate,
case and punctuation ignored, `-` treated as a space. Nothing here uses the microphone.

| configuration | word accuracy | errors / words |
|---|---|---|
| no terms (SpeechTranscriber) | 76.9% | 21 / 91 |
| terms, SpeechTranscriber only (`--module speech`) | 76.9% | 21 / 91 |
| terms, default (DictationTranscriber) | **94.5%** | 5 / 91 |

## What this changed in the design

`AnalysisContext.contextualStrings` is **ignored by SpeechTranscriber** (identical output with and without terms,
whether set through `setContext` or the `SpeechAnalyzer` initializer). **DictationTranscriber honours it**: "matplotlib",
"pandas DataFrame", "TensorFlow loss NaN", "Jupyter", "softmax", "scikit-learn", "torch.no_grad" all come out right.
Without terms the two modules are about equally accurate, and SpeechTranscriber punctuates a little better. So
`AnalyzerSession` uses DictationTranscriber (with `.punctuation`) when the app has sent `context` terms and its model
for the locale is installed, and SpeechTranscriber otherwise. `--module speech|dictation` forces one for testing.

## Still wrong with terms (5 errors)

- "PyTorch" / "CUDA": "pie porch", "cut" (terms were given, the acoustic match is too far off).
- "PINN": "pin" (a term, but a real English word).
- "torch.no_grad": "torch.no_grad" for "no grad" was right with terms, wrong without.

## Caveats

- Synthetic TTS speech is easier than a laptop mic in a room, and the phrases skew toward words that are in the term
  list, so treat 94.5% as an upper bound. Real-mic accuracy is unmeasured until someone tests it on the Mac.
- Terms are only as good as the lesson context sent by the app (title, step title, library names).
- Re-run the numbers after a macOS update; the speech models change.

# Release tail: how long to wait for the final (Nov 22)

Measured Nov 22 2026 on macOS 26.6 (Apple silicon, idle), en-US SpeechTranscriber, no terms, by
`native/listen/measure-tail.sh`. 21 phrases (`phrases.tsv` plus the longer `tests/tailmeasure/long.tsv`, 2 to 6 s) in 3
`say -o` voices (Samantha, Daniel, Fred) = 63 clips, 606 words, each run 3 ways through the real Transcriber: warm (fed at
mic pace, release at the end of the audio), warm with 200 ms of silence before release, and cold (the whole hold queued
and flushed at once when the recognizer is ready, like `Session.sttStarted`). No mic, nothing played aloud.

| | warm | warm, 200 ms silence | cold flush |
|---|---|---|---|
| finish() (the final) after release / the flush: median, max | 67, 140 ms | 62, 125 ms | 68, 140 ms |
| text incomplete at release (the final has more or other words) | 62/63 | 62/63 | 63/63 |

- SpeechAnalyzer's volatile text runs well behind the audio: it comes in bursts (in a 5.7 s clip nothing past the first
  60% had shown at release). The rest arrives about 10 to 50 ms after the input ends, then the final.
- In 36 of 189 runs the final still added or fixed words that no partial had ("How do I enfor?" became "How do I enforce
  no peace?"). So only the final is complete; a text that has gone quiet is not.
- At this speed every policy loses 0 words, because the final always beats 300 ms. The difference is a slower Mac
  (busy, or the model still loading). Replaying the same timelines k times slower after release (`measure-tail.py`,
  a sensitivity check; nothing was run under load), words lost of 606 (warm / cold):

| policy | 3x | 5x | 8x | 10x |
|---|---|---|---|---|
| flat 300 ms (the lane's first cut) | 8 / 15 | 61 / 68 | 105 / 463 | 128 / 606 |
| 300 ms, then once the text held still 150 ms | 8 / 10 | 58 / 30 | 83 / 79 | 87 / 108 |
| 300 ms, then once the text held still 300 ms | 1 / 0 | 13 / 9 | 49 / 20 | 70 / 32 |
| the final, else 1000 ms (cold: + a quarter of the flushed audio, at most 1500 ms): **Tail.swift** | 0 / 0 | 0 / 0 | 1 / 0 | 8 / 0 |
| flat 1500 ms (before Nov 22) | 0 / 0 | 0 / 0 | 0 / 0 | 0 / 0 |

Chosen: the final the moment it comes (median wait 62 to 68 ms, the same as every policy at this speed), else the best
text at 1000 ms, up to 1500 ms after a cold-start flush. So the release-to-final time was never the 1.5 s cap on this
Mac: the cap only shapes the slow cases, and there a shorter one costs words. Caveats: synthetic voices, an idle Mac,
and "cold" here is a queued flush in a process whose speech service is already loaded; a first hold after login may be
slower still, which is what the 1.5 s ceiling is for. Re-run after a macOS update.
