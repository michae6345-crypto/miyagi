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
