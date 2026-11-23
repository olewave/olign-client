# olign-client

Olign is a forced alignment API for English speech. You send a recording, with
its transcript if you have one. Olign tells you where every word starts and
ends, in seconds, and on request where every phone does.

This repo holds `olign`, the Python package and command line for the API, with
examples and tests. This README is the documentation: the command line, the
Python package, the HTTP API ([curl](#curl)), [the result](#the-result) and
[errors](#errors).

## Quickstart

Install the package. It runs on Python 3.9 or later and needs nothing beyond
the standard library.

```bash
pip install olign
```

It installs the `olign` package and command from this repo.

Sign up at [dashboard.olewave.com](https://dashboard.olewave.com/#signup). No invitation
code is needed, and a new account starts with 300 free credits. Save a card under
**Billing** for 3,000 more: 1,000 minutes of audio at the launch promotion's price.
Saving it charges nothing. Then create an API
key under **Profile → API keys**.

The key is shown once and it identifies your account. Keep it in an environment
variable, out of code you share. The package reads it from `OLIGN_KEY`.

```bash
read -rsp 'olign key: ' OLIGN_KEY && export OLIGN_KEY && echo
```

Align your first recording.

```bash
olign align talk.mp3 --textgrid
```

The command uploads `talk.mp3` and waits for the job. Then it writes
`talk.TextGrid`. Open it in [Praat](https://www.fon.hum.uva.nl/praat/) to see a
words and a pauses tier. Add `--timestamps phone` for a phones tier too.

## Command line

Add `--transcript` when you have the text. Without it, Olign transcribes the
audio first and then aligns the words it heard.

```bash
olign align examples/short1.wav --transcript examples/short1.txt --srt --vtt --json
```

Every output flag takes an optional file name. A flag on its own names the file
after the audio, so `--srt` writes `short1.srt` here. Progress goes to stderr.
A short summary goes to stdout.

```
short1.wav: 4.48 s of audio, 7 words aligned to your transcript, 4 pauses, 2 phrases
wrote short1.srt
wrote short1.vtt
wrote short1.json
```

| flag | writes |
|---|---|
| `--textgrid` | a Praat TextGrid with a words and a pauses tier, and a phones tier with `--timestamps phone` |
| `--srt` | SubRip subtitles with one cue per phrase |
| `--vtt` | WebVTT subtitles with a timestamp on every word |
| `--csv` | one row per word |
| `--json` | the result in the API's shape |

With no output flag, `olign align` saves the JSON.

Three options change what Olign does. `--word-edges audible` times words the way a
listener hears them, for dubbing and subtitles (see
[Word edges](#word-edges-phonetic-or-audible)). `--align-untranscribed` also
aligns the speech your transcript leaves out, such as fillers and repeats.
`--timestamps phone` also returns each word's phones, at twice the price (see
[Word or phone timestamps](#word-or-phone-timestamps)).

```bash
olign align voiceover.wav --transcript voiceover.txt --word-edges audible --srt
```

`olign export` turns a saved result into more formats without a second upload,
so you pay for the audio once. Try it on the sample result in this repo. It
needs no account.

```bash
olign export examples/sample_v1_result.json --textgrid --csv
```

Press Ctrl-C while `olign align` waits and the job keeps running on the server.
`olign get` picks it up later by the id that `align` printed.

```bash
olign get 6abb52b92239acba --textgrid
```

## Python

`olign.Client` submits the job and polls it until the words are ready.

```python
import olign

client = olign.Client()  # reads OLIGN_KEY
result = client.align("examples/short1.wav", transcript="what is better a fruit or hamburger")

for w in result.words:
    print(f"{w.word:<10} {w.begin:5.2f} {w.end:5.2f}")

result.to_textgrid("short1.TextGrid")
```

Each line is a word with its start and end in seconds.

```
what        0.47  0.80
is          0.82  1.13
better      1.21  2.02
a           2.17  2.42
fruit       2.42  3.02
or          3.02  3.57
hamburger   3.57  4.13
```

Pass the transcript as a string, or as a `pathlib.Path` to a UTF-8 text file.
Leave it out and Olign transcribes the audio. `word_edges="audible"`,
`align_untranscribed=True` and `timestamps="phone"` are the three options of
the upload.

```python
result = client.align("voiceover.wav", transcript=pathlib.Path("voiceover.txt"), word_edges="audible")
for phrase in result.phrases:
    print(f"{phrase.begin:5.2f} {phrase.end:5.2f}", " ".join(w.word for w in result.phrase_words(phrase)))
print([round(p.seconds, 2) for p in result.pauses])
```

Every exporter returns the text. Give it a path and it writes the file too.

| method | gives you |
|---|---|
| `to_textgrid()` | a Praat TextGrid with a words and a pauses tier, and a phones tier when the result has phones |
| `to_srt()` | SubRip subtitles with one cue per phrase, or per word with `max_words=1` |
| `to_vtt()` | WebVTT subtitles with a timestamp tag on every word |
| `to_csv()` | one row per word, or one per phone with `phones=True` (a result aligned with `timestamps="phone"`) |
| `to_json()` | the result in the API's shape, which `olign.Result.load()` reads back |

A long recording takes a while. Pass `poll=False` to get the job back as soon
as it is accepted, and call `wait()` when you want the words.

```python
job = client.align("lecture.ogg", poll=False)
print(job.job_id)  # keep it, and come back later
result = client.wait(job.job_id)
```

## curl

The API takes two calls. You upload the audio and get a job id back. Then you
poll the job until it is done. Every request carries your key in the
`X-API-Key` header.

```bash
curl https://api.olewave.com/olign/v1 \
  -H "X-API-Key: $OLIGN_KEY" \
  -F audio=@examples/short1.wav \
  -F transcript=@examples/short1.txt
# 202 {"job_id":"6abb52b92239acba"}
```

The upload is `multipart/form-data`.

| part | required | what to send |
|---|---|---|
| `audio` | yes | The recording in any common audio format. At most 3 hours and 100 MB. |
| `transcript` | no | Plain UTF-8 text of what is said. |
| `align_untranscribed` | no | `1` to also align speech your transcript leaves out, such as fillers and repeats. Recordings of 15 s or less ignore it. |
| `word_edges` | no | `phonetic` (the default) or `audible`; see [Word edges](#word-edges-phonetic-or-audible). |
| `timestamps` | no | `word` (the default) or `phone`; see [Word or phone timestamps](#word-or-phone-timestamps). |

Ask for the job every 5 to 10 seconds until its `state` is `done` or `failed`.

```bash
curl https://api.olewave.com/olign/v1/6abb52b92239acba -H "X-API-Key: $OLIGN_KEY"
```

A 4.5-second clip with a transcript takes about a second. A 28-minute recording
takes about 4 minutes. At busy times a job also waits a while as `queued`.

Leave the transcript out and Olign transcribes the audio first. The job then
says `"transcript_source": "asr"`.

```bash
curl https://api.olewave.com/olign/v1 -H "X-API-Key: $OLIGN_KEY" -F audio=@examples/short1.wav
```

One upload carries at most 100 MB. Compress long recordings to Opus. At
32 kbit/s mono an hour takes about 14 MB.

```bash
ffmpeg -i lecture.wav -ac 1 -c:a libopus -b:a 32k lecture.ogg
```

Send your own `User-Agent` header. Cloudflare sits in front of the API and turns
away some library defaults with `403`. Python's `urllib` is one of them. The
`olign` package names itself, so it never meets this.

[`examples/v1_client.py`](examples/v1_client.py) makes both calls with the
standard library alone, if you would rather not install the package.

### Word edges: phonetic or audible

By default (`word_edges=phonetic`) Olign times words the way phoneticians do. A
word that starts with p, t, k, b, d or g starts when the lips or tongue close,
and that closure is silent. Send `word_edges=audible` to time words the way a
listener hears them, as dubbing and subtitles need. That silence then stays
outside the word and comes back as a gap, and a breath before a word is left
outside it too. Scores do not change.

It needs a clean recording, where the silences are quiet: a voiceover, a studio
or a quiet room. Where background noise or music fills the silences, the words
keep their default timing. Before v1.0.10 this option was the part
`closure_as_silence=1`, and that still works.

### Word or phone timestamps

By default (`timestamps=word`) each word comes back with its `begin`, `end` and
`score`. Send `timestamps=phone` and each word also carries its phones, each
with its own `begin`, `end` and `score`. Word timing is the same either way. A
phone-level job costs twice as much, and the job's `timestamps` field says which
one it is. Any other value gets `400` and costs nothing. Before Olign v1.2.1
every job returned phones, so code that reads them now sends `timestamps=phone`
(`timestamps="phone"` in Python, `--timestamps phone` on the command line).

### Billing headers

The dashboard keeps your balance in credits. A minute of audio is 3 credits
during the launch promotion and 3.5 after it, and 1,000 credits cost $1. With
`timestamps=phone` a minute is 6 credits during the promotion and 7 after it. Every
metered response carries two headers in that unit. `X-Credits-Charged` is what
the call cost. `X-Credits-Balance` is what your account has left. The
4.5-second clip above is billed at the 10-second minimum, so on a fresh account
during the promotion they read as follows.

```
X-Credits-Charged: 0.5
X-Credits-Balance: 2999.5
```

## The result

Once `state` is `done`, the same response carries `result`. Here is the answer
for `examples/short1.wav` sent with `timestamps=phone`, its words cut to the
first two. Without it the words come back the same, without their `phones`.

```json
{
  "job_id": "6b0167d8f3956c2d",
  "state": "done",
  "audio_seconds": 4.48,
  "transcript_source": "client",
  "timestamps": "phone",
  "result": {
    "words": [
      {"word": "what", "begin": 0.47, "end": 0.798, "score": 55.0, "phones": [
        {"ph": "w", "begin": 0.47, "end": 0.518, "score": 0},
        {"ph": "ah", "begin": 0.518, "end": 0.708, "score": 62},
        {"ph": "t", "begin": 0.708, "end": 0.798, "score": 72}
      ]},
      {"word": "is", "begin": 0.818, "end": 1.133, "score": 83.0, "phones": [
        {"ph": "ih", "begin": 0.818, "end": 1.053, "score": 76},
        {"ph": "z", "begin": 1.053, "end": 1.133, "score": 86}
      ]}
    ],
    "pauses": [
      {"begin": 0.0, "end": 0.47},
      {"begin": 1.133, "end": 1.213},
      {"begin": 2.018, "end": 2.173},
      {"begin": 4.133, "end": 4.48}
    ],
    "phrases": [
      {"begin": 0.47, "end": 2.018, "words": [0, 2]},
      {"begin": 2.173, "end": 4.133, "words": [3, 6]}
    ]
  }
}
```

The job carries these fields.

| field | what it holds |
|---|---|
| `job_id` | The id the upload returned. |
| `state` | `queued`, `running`, `done` or `failed`. |
| `audio_seconds` | The length of your audio after decoding. Usage is metered on it. |
| `transcript_source` | `client` when you sent a transcript. `asr` when Olign made one. |
| `timestamps` | `word` or `phone`, as you asked. |
| `result` | The alignment, once `state` is `done`. |
| `error` | Why the job failed, once `state` is `failed`. |

`result` has three lists: `words`, `pauses` and `phrases`.

`result.words` holds every word of your transcript, in order. Each word has
these fields.

| field | what it holds |
|---|---|
| `word` | The word as your transcript spells it. |
| `begin`, `end` | Where the word starts and ends, in seconds from the start of the file. |
| `score` | How sure Olign is of this word's alignment, from 0 to 100. |
| `phones` | Only with `timestamps=phone`: the word's phones in order, each with `ph`, `begin`, `end` and `score`. |

Phones are ARPAbet symbols in lower case. The word "what" above is `w`, `ah`,
`t`.

`score` is alignment confidence. A low score marks a word worth a second look.
In this clip "what" scored 55, and every other word scored 83 or more. The score
makes no claim about pronunciation. A phone's `score` is `null` when Olign has
none for it.

Three flags mark special words. Each one appears only when it applies.

A word you wrote that nobody said comes back with `"spoken": false`. It has zero
length and sits at the end of the word before it.

```json
{"word": "really", "begin": 2.428, "end": 2.428, "spoken": false}
```

A `[bracketed]` tag in your transcript keeps its place with `"annotation": true`.
A tag is never spoken, so it has zero length and no phones.

```json
{"word": "[laughter]", "begin": 5.12, "end": 5.12, "spoken": false, "annotation": true}
```

A word your transcript left out has `"untranscribed": true`. You get these only
when you send `align_untranscribed=1`.

```json
{"word": "um", "begin": 7.3, "end": 7.52, "score": 71.0, "untranscribed": true}
```

`result.pauses` lists, in order, every stretch of 0.05 s or more that no word
covers: silence, a breath, a noise. The stretch before the first word and the
one after the last are included; the last one ends at `audio_seconds`.

`result.phrases` splits the words at every pause of 0.1 s or more. Each phrase
has a `begin` and an `end`, where its speech starts and stops, and `words`, the
positions in `result.words` of its first and last word, both included. The clip
above is two phrases: "what is better" (words 0 to 2) and "a fruit or
hamburger" (words 3 to 6). To cut phrases at a different length, group the
words at the pauses yourself.

Every response carries two version headers. `X-Olign-API-Version` is the version
of this contract. `X-Olign-Version` is the Olign release that did the work.
Timings and scores can change between releases, so store `X-Olign-Version` with
any result you keep. The package keeps both in the JSON it saves.

```
X-Olign-API-Version: v1.1.5
X-Olign-Version: v1.1.5
```

[`examples/sample_v1_result.json`](examples/sample_v1_result.json) is the whole
answer for this clip, saved from Olign v1.1.5 with its version headers.

## Errors

A request Olign cannot take gets an HTTP error at once. The body is JSON with
the reason.

```json
{"error": "Content-Length required"}
```

| code | when |
|---|---|
| `400` | The file is empty or is not audio Olign can decode. |
| `401` | The API key is missing, invalid or revoked. |
| `402` | Your credits are used up, or the recording is longer than they pay for. Add a card or buy more on the dashboard under **Billing**. |
| `403` | Cloudflare refused the request. Send your own `User-Agent`. |
| `404` | The job id is unknown or belongs to another key. A job still running when the service restarted also answers `404`, so submit it again. |
| `411` | The upload has no `Content-Length`, as a chunked upload does. |
| `413` | The upload is over 100 MB or the audio is over 3 hours. The body's `audio_seconds` gives the recording's length. |
| `415` | The body is not `multipart/form-data`. |
| `422` | No part is named `audio`. |
| `429` | You reached the monthly limit you set under **Settings**. `Retry-After` gives the seconds until the 1st of the month, 00:00 UTC. |

A job that was accepted can still end with `"state": "failed"`. Its `error` is
one of four sentences. They are the whole list, so you can match on them.

```json
{
  "job_id": "6ab8c7afc0598012",
  "state": "failed",
  "audio_seconds": 12.4,
  "transcript_source": "client",
  "error": "the transcript does not match the audio"
}
```

| `error` | what you can do |
|---|---|
| `no speech found in the audio` | Check that the file holds speech. |
| `the transcript has no words` | Send a transcript with words in it. Or leave it out, and Olign transcribes the audio. |
| `the transcript does not match the audio` | Check that the transcript belongs to this recording. Or leave it out, and Olign transcribes the audio. |
| `internal error; retry, and contact support with the job id if it repeats` | Submit the job again. If it fails again, write to info@olewave.com with the job id. |

In Python every error raises a subclass of `olign.OlignError`. Its message is
the API's own, followed by a hint on what to do.

```python
try:
    result = client.align("lecture.ogg")
except olign.PaymentRequiredError as e:
    print(e)  # HTTP 402, the API's message and a hint
except olign.JobFailedError as e:
    print(e)  # the job's error sentence
```

| exception | when |
|---|---|
| `AuthenticationError` | `401` |
| `PaymentRequiredError` | `402` |
| `AudioTooLargeError` | `413` |
| `UsageLimitError` | `429`. `e.retry_after` gives the seconds until your monthly limit resets. |
| `APIError` | any other HTTP error |
| `JobFailedError` | The job was accepted and then failed. The message carries its `error`. |
| `ConnectionFailedError` | The API could not be reached. |

## Pricing

You pay for the length of the audio you send. Olign costs $0.21 an hour. During
the launch promotion it costs $0.18 an hour.

A 45-minute lecture costs about 14 cents at the launch price.

Save a card and you get 3,000 free credits, 1,000 minutes at the launch price.
Saving it charges nothing. That covers 22 lectures of that length.

Each job is metered on its `audio_seconds`, rounded up to the second. A job is
billed for at least 10 seconds. A job that fails costs nothing, and its credits
go back to your balance.

You can set a monthly limit under **Settings** on the dashboard. Once your usage
reaches it, new jobs get `429` until the 1st of the month. The **Usage** page
shows what you sent per day and per API key.

## Limits

| | |
|---|---|
| languages | US and UK English. |
| length | Up to 3 hours per file. |
| size | 100 MB per upload. Compress long recordings to Opus as above. |
| repeat runs | The same file can come back slightly different between submissions. Speech recognition runs on a GPU and is not bit-for-bit repeatable. |
| your data | Olewave keeps each job's inputs and result for your account, as the beta testing agreement says. Write to info@olewave.com to have them deleted. |

## Score Olign with FA-Bench

FA-Bench runs the current Olign through this API, one job per utterance, in two modes.

| FA-Bench recipe | sends | FA-Bench track |
|---|---|---|
| `olign_v1` | the audio and its reference transcript (`transcript_source` is `client`) | 1, alignment given the words |
| `olign_v1_asr` | the audio alone (`transcript_source` is `asr`). Olign recognizes the words and then aligns them. | 2, Olign's own recognizer and then its aligner |

1. **Set up FA-Bench** as [its README](https://github.com/olewave/fa-bench#readme)
   describes. The corpora are licensed separately.
2. **Put your key** in FA-Bench's untracked `.fabench.env` as
   `OLIGN_API_KEY=<key>`.
3. **Align and score** with `evals/run_evals.sh olign_v1` or
   `evals/run_evals.sh olign_v1_asr`. Add `--use-noisy-dataset` for the four
   degraded conditions.

Every response is cached, so a restart or a rescore sends nothing again. A full
sweep covers every split of both corpora, clean and degraded. That is 47,805
jobs and 34.1 hours of audio per mode. The utterances are a few seconds each, so
nearly every job is billed at the 10-second minimum. Plan on about 133 billed
hours per mode, around $24 at the launch price.

---

## API v0.9, the FA-Bench paper's API

> This section is for reproducing the Olign numbers in the
> [FA-Bench paper](https://arxiv.org/abs/2609.32396). For your own recordings,
> use API v1 above.

| You want to | Use | Endpoint | Access |
|---|---|---|---|
| **reproduce Olign's results in the FA-Bench paper** | **v0.9** | `https://api.olewave.com/olign/v0.9` | a service token from Olewave (info@olewave.com) |
| **get the latest Olign results** for your own recordings, or score the current Olign with FA-Bench | **v1** | `https://api.olewave.com/olign/v1` | an API key from [dashboard.olewave.com](https://dashboard.olewave.com/#signup) |

API v0.9 serves **Olign 0.9**, the version behind every Olign number in the
FA-Bench paper. It takes one clip and its text per request and answers in the
same call. The paper's first arXiv version calls it "Olign 1.0" in a table
caption; the revised paper and FA-Bench's records name it Olign 0.9. Since
2026-10-11 the endpoint serves Olign 0.9.1; see
[Reproduce the FA-Bench numbers](#reproduce-the-fa-bench-numbers).

### Set up

Ask Olewave at info@olewave.com for a Cloudflare Access service token. Every
request sends it as two headers. Without them the answer is `403`.

```bash
export CF_ACCESS_CLIENT_ID=<id>.access CF_ACCESS_CLIENT_SECRET=<secret>
```

### Call it

POST the audio as the raw request body. Everything else goes in the query
string.

```bash
curl -X POST --data-binary @examples/short1.wav \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  "https://api.olewave.com/olign/v0.9?ref_text=what%20is%20better%20a%20fruit%20or%20hamburger&core_type=en.word.score&rank=100&accent=2&show_phone_details=1"
```

[`examples/rest_client.sh`](examples/rest_client.sh) reads the two variables
and prints a summary.

```bash
./examples/rest_client.sh --url https://api.olewave.com/olign/v0.9 --core-type en.word.score \
  --wav examples/short1.wav --ref-text "what is better a fruit or hamburger"
```

| query parameter | default | values |
|---|---|---|
| `ref_text` | *(required)* | What the speaker was supposed to say, URL-encoded. |
| `core_type` | `en.sent.score` | `en.word.score`, `en.sent.score`, `en.sent.child`, `en.pred.exam`, `en.phone.align` |
| `rank` | `100` | The score scale. `100` means scores run from 0 to 100. |
| `accent` | `2` | `1` is UK, `2` is US. |
| `show_phone_details` | `1` | `1` includes the per-phone breakdown. |

The body is any common audio format, up to **50 MB**.

### Handle the result

The response is one JSON object.

```jsonc
{
  "versions": {"api": "v0.9.0"},
  "errId": 0,              // must be 0; otherwise read "error" and ignore "result"
  "error": "",
  "result": {
    "overall": 87,         // the headline score, 0..rank
    "wavetime": 4480,      // audio scored, in milliseconds
    "details": [           // one entry per word of ref_text, in order
      {"char": "what", "score": 55, "begin": 470, "end": 750, "dur": 280,   // milliseconds
       "phone": [{"char": "w", "score": 0, "begin": 470, "end": 513, "dur": 43}]}
    ]
  }
}
```

- **Check `errId` as well as the HTTP status.** It can be non-zero on a `200`.
- **All times are in milliseconds.** `begin: 470` is 0.47 s.
- `details[]` has one entry per word of `ref_text`, even words the speaker never
  said. A near-zero `score` means the word was mispronounced *or* skipped.
- **Keep `versions` with any score you store.** It holds the same values as the
  `X-Olign-*-Version` headers. Answers from before 2026-10-11 23:46 UTC don't
  have it; take the versions from their headers instead.

```python
d = response.json()
if d["errId"] != 0:
    raise RuntimeError(d["error"])
for w in d["result"]["details"]:
    print(w["char"], w["score"], w["begin"] / 1000, w["end"] / 1000)
```

| code | when |
|---|---|
| `200` | Parse the body, then check `errId`. |
| `400` | The audio cannot be decoded. |
| `403` | The service token is missing or invalid. |
| `411` | No `Content-Length` (a chunked upload). |
| `413` | The body is over 50 MB. |
| `422` | `ref_text` is missing. |

### Reproduce the FA-Bench numbers

FA-Bench makes exactly this call. It sends one request per utterance with the
whole audio, several in parallel.

1. **Set up FA-Bench** as [its README](https://github.com/olewave/fa-bench#readme)
   describes. The corpora are licensed separately, and FA-Bench works from your
   own copies.
2. **Point its Olign aligner here** in FA-Bench's untracked `.fabench.env`.

   ```bash
   OLIGN_BASE_URL=https://api.olewave.com/olign/v0.9
   CF_ACCESS_CLIENT_ID=<id>.access
   CF_ACCESS_CLIENT_SECRET=<secret>
   ```

3. **Align and score** with `evals/run_evals.sh olign`.

Check the version first. The paper's Olign numbers are **Olign 0.9**'s, which
this endpoint serves through API v0.9. Every response carries its versions in
`X-Olign-*-Version` headers and, since 2026-10-11, in the body's `versions`.

**Since 2026-10-11 this endpoint serves Olign 0.9.1.** The paper's current
version reports **Olign 0.9.0**, which is no longer served. Olign 0.9.1's word
and phone times differ from 0.9.0's, so a run today won't match the table below
exactly; a later version of the paper will report Olign 0.9.1. The table stays
as the record of 0.9.0.

What 0.9.0 gave: the paper's alignments were made in August 2026 on a
pre-release server. The public build moved individual boundaries by a few
milliseconds, 8.9 ms median per utterance. The totals agree. Here is Buckeye
test (clean), scored with FA-Bench's current scorer.

| Buckeye test, clean | paper | public build `98728396` (0.9.0) |
|---|---|---|
| word MAE (ms) | 22.5 | 22.3 |
| word F1 @20 ms | 0.744 | 0.747 |
| phone MAE (ms) | 12.7 | 12.3 |
| PER (%) | 28.2 | 28.2 |
| phone F1 @20 ms | 0.522 | 0.526 |

The public build gave identical timings for the same file on every run. Allow
about 0.1 ms and 0.002 for scorer drift. The current scorer gives the paper's
own alignments 22.6 ms word MAE and 0.524 phone F1. Only Buckeye test (clean)
has been re-measured so far.

---

## Tests

| test | needs | checks |
|---|---|---|
| `python3 -m unittest tests.test_olign_package -v` | nothing | The `olign` package. Its exporters and CLI run on the sample result, with and without scores. A full upload-and-poll round trip runs against a stand-in API on 127.0.0.1. |
| `python3 -m unittest tests.test_v1_offline -v` | nothing | `examples/v1_process.py` on the sample result. It checks the CSVs and the TextGrid it writes. |
| `python3 -m unittest tests.test_v1_live -v` | `OLIGN_KEY` | Every clip in `test-data/` goes through the v1 API. Each word and phone must come back in order, inside the audio, with a score from 0 to 100. It takes about a minute and sends 5.5 minutes of audio in four jobs, about 2 cents at the launch price. |
| the `rest_client.sh` call above | the service token | The v0.9 endpoint. `short1.wav` with `en.word.score` must give `overall=87  words=7  wavetime=4480 (ms)`. |

[`test-data/`](test-data/) holds three LibriSpeech recordings with their
transcripts, 11 s of FLAC and 56 s and 3.4 min of Opus. Their sources and
licenses are in [`test-data/README.md`](test-data/README.md).
[`test-data/cases.json`](test-data/cases.json) lists what the live test sends
and expects.

## License

Copyright 2026 Olewave, LLC (https://www.olewave.com). The code and
documentation here are licensed under the [Apache License 2.0](LICENSE). The
recordings in [`test-data/`](test-data/) are from LibriSpeech and keep their own
license, CC BY 4.0. See [`test-data/README.md`](test-data/README.md).
