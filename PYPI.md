# olign

`olign` is the Python package and command line for Olign, the forced alignment
API from Olewave. You send English speech, with its transcript if you have one.
Olign tells you where every word and every phone starts and ends, in seconds.
Without a transcript, Olign transcribes the audio first and then aligns it.

On [FA-Bench](https://github.com/olewave/fa-bench), an open benchmark for word
timestamps, Qwen3 transcripts aligned by Olign 0.9 rank first of 28 pipelines.
Olign 1.0 numbers, audio-only mode included, are coming soon.

## Install

The package runs on Python 3.9 or later and needs nothing beyond the standard
library.

```bash
pip install olign
```

Sign up at [tycho.olewave.com](https://tycho.olewave.com/#signup). No invitation
code is needed. Save a card under **Billing**. Saving it charges nothing, and
during the launch promotion it unlocks 1,000 free minutes. Then create an API
key under **Profile → API keys** and put it in `OLIGN_KEY`.

```bash
export OLIGN_KEY=gvk_your_key
```

## Command line

One line uploads a recording and writes a Praat TextGrid with a words tier and
a phones tier.

```bash
olign align talk.mp3 --transcript talk.txt --textgrid
```

Leave out `--transcript` and Olign transcribes the audio first. Swap
`--textgrid` for `--srt` or `--vtt` to get subtitles instead.

## Python

`olign.Client` submits the job and polls it until the words are ready. This
example aligns
[short1.wav](https://github.com/olewave/olign-client/blob/main/examples/short1.wav),
a 4.5-second clip from the repo.

```python
import olign

client = olign.Client()  # reads OLIGN_KEY
result = client.align("short1.wav", transcript="what is better a fruit or hamburger")

for w in result.words:
    print(f"{w.word:<10} {w.begin:5.2f} {w.end:5.2f}")

result.to_srt("short1.srt")
```

Each line is a word with its start and end in seconds. Here are the first
three.

```
what        0.47  0.75
is          0.84  1.13
better      1.21  1.89
```

## Pricing

Olign costs $0.18 an hour of audio during the launch promotion and $0.21 an hour
after it. Save a card and your first 1,000 minutes are free during the
promotion.

## Learn more

The documentation lives at
[developers.olewave.com](https://developers.olewave.com). The
[leaderboard](https://developers.olewave.com/leaderboard/) ranks every pipeline
on FA-Bench. The source, with more examples, is on
[GitHub](https://github.com/olewave/olign-client).
