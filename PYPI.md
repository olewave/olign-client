# olign

`olign` is the Python package and command line for Olign, the forced alignment
API from Olewave. You send English speech, with its transcript if you have one.
Olign tells you where every word starts and ends, in seconds, and with
`timestamps="phone"` where every phone does.
Without a transcript, Olign transcribes the audio first and then aligns it.

Each result also lists the pauses between the words and the phrases they
form, and `word_edges="audible"` times words the way a listener hears them, for
dubbing and subtitles.

## Install

The package runs on Python 3.9 or later and needs nothing beyond the standard
library.

```bash
pip install olign
```

The package's version is the Olign release it was made with: Olign, its API
and this package share one version number.

Sign up at [dashboard.olewave.com](https://dashboard.olewave.com/#signup). No invitation
code is needed, and a new account starts with 300 free credits. Save a card under
**Billing** for 3,000 more: 1,000 minutes of audio at the launch promotion's price.
Saving it charges nothing. Then create an API
key under **Profile → API keys** and put it in `OLIGN_KEY`.

```bash
export OLIGN_KEY=gvk_your_key
```

## Command line

One line uploads a recording and writes a Praat TextGrid with a words and a
pauses tier. Add `--timestamps phone` (twice the price) for a phones tier too.

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

You pay in prepaid credits, and 1,000 credits cost $1. A minute of audio is 3 credits
during the launch promotion ($0.18 an hour) and 3.5 after it ($0.21 an hour).
Saving a card adds 3,000 free credits, and credits never expire.

## Learn more

The documentation, the source and more examples are on
[GitHub](https://github.com/olewave/olign-client).
