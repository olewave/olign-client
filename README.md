# olign-client

Examples, test data and tests for calling **olign**, Olewave's forced alignment
and pronunciation scoring for English speech. You send audio (and, optionally,
the text that was said); olign returns every word and phone with its start and
end time and a 0–100 score.

## Which version?

| You want to… | Use | Endpoint | Access |
|---|---|---|---|
| **reproduce olign's results in the [fa-bench](https://github.com/olewave/fa-bench) paper** | **v0.9** | `https://api.olewave.com/olign/v0.9` | a service token from Olewave (info@olewave.com) |
| **get the latest olign results** for your own recordings | **v1.0** | `https://api.olewave.com/olign/v1` | an API key, self-service with an invitation code |

- **v0.9** is the API behind the paper's "Olign 1.0" numbers: one clip and its
  text per request, answered in the same call.
- **v1.0** is the current API: upload a whole recording (the transcript is
  optional), then poll the job for word and phone timings.

---

## v1.0: whole recordings, as jobs

### Set up

1. **Get an invitation code** from Olewave (info@olewave.com).
2. **Sign up** at https://tycho.olewave.com: open the **Sign up** tab and enter
   your email, a password and the code.
3. **Create your API key** under **Profile → API key**. It is shown once and it
   identifies you, so keep it out of code you share:

   ```bash
   read -rsp 'olign key: ' OLIGN_KEY && export OLIGN_KEY && echo
   ```

### Call it

Two calls: submit, then poll until the job is done.

```bash
# submit: audio (any common format), transcript optional  ->  202 {"job_id": "..."}
curl -H "X-API-Key: $OLIGN_KEY" \
  -F audio=@examples/short1.wav -F transcript=@examples/short1.txt \
  https://api.olewave.com/olign/v1

# poll every 5-10 s until "state" is "done"; the result is in the same response
curl -H "X-API-Key: $OLIGN_KEY" https://api.olewave.com/olign/v1/<job_id>
```

Or let the example do both and save the result (Python standard library only):

```bash
python3 examples/v1_client.py examples/short1.wav --transcript examples/short1.txt -o result.json
```

Without a transcript, olign transcribes the audio itself and scores what it heard.

### Handle the result

Once `state` is `done`, the response holds:

| field | meaning |
|---|---|
| `audio_seconds` | length of your audio, as decoded; your daily usage is counted on it |
| `result.words[]` | every transcript word in order: `word`, `begin`, `end` (seconds), `score` (0–100), `sent_id`, and `phones[]` with `ph` (CMU/ARPAbet), `begin`, `end`, `score` |
| `result.sentence_scores[]` | per sentence: `sent_score`, `word_avg`, `word_min` |
| `result.stats.overall_mean` | the mean segment score; `n_err > 0` means some segments could not be scored |

- A word that was not spoken has `"spoken": false` and zero duration; a
  `[bracketed]` tag has `"annotation": true`.
- A phone with zero duration could not be placed; it sits inside its word, where
  it falls in order.
- Keep the `X-Olign-*-Version` response headers with any score you store (the
  example saves them under `_versions`): scores change between versions.

[`examples/v1_process.py`](examples/v1_process.py) turns a saved result into a
summary, spreadsheets and a Praat TextGrid.
[`examples/sample_v1_result.json`](examples/sample_v1_result.json) is a real
result for `examples/short1.wav`, so you can try it without an account:

```bash
python3 examples/v1_process.py examples/sample_v1_result.json --csv out/ --textgrid out/short1.TextGrid
```

This prints the overall score and the weakest words, and writes
`out/words.csv`, `out/phones.csv` and `out/short1.TextGrid`, which opens in
[Praat](https://www.fon.hum.uva.nl/praat/) as a words tier and a phones tier.

### Limits and errors

| | |
|---|---|
| daily allowance | **60 minutes of audio per account per day** (UTC). A job counts as soon as it is accepted, failed ones too |
| length | files up to 60 minutes; a job takes about 0.12× the audio length |
| size | 100 MB per upload. Compress long recordings, e.g. Opus at 32 kbit/s is ~14 MB an hour: `ffmpeg -i in.wav -ac 1 -c:a libopus -b:a 32k out.ogg` |
| queue | jobs run one at a time; yours may wait as `queued` |
| privacy | your audio is deleted as soon as the job finishes |
| User-Agent | send your own: Cloudflare rejects some HTTP-library defaults (`403`, `error code: 1010`, e.g. Python's `urllib`) |

| code | when |
|---|---|
| `202` | submitted; the body has `job_id` |
| `401` | missing or invalid API key |
| `404` | unknown job id, one submitted with another key, or forgotten after a service restart: resubmit |
| `411` | no `Content-Length` (a chunked upload) |
| `413` | over 100 MB, or longer than a day's allowance; `audio_seconds` in the body is the recording's length |
| `415` | not `multipart/form-data` |
| `422` | no part named `audio` |
| `429` | today's 60 minutes are used up, or the recording is longer than what is left of them; `Retry-After` gives the seconds until 00:00 UTC |

A job can also end with `"state": "failed"`; `log_tail` says why.

---

## v0.9: one clip per request (reproducing fa-bench)

### Set up

Ask Olewave (info@olewave.com) for a Cloudflare Access service token. Every
request sends it as two headers; without them the answer is `403`.

```bash
export CF_ACCESS_CLIENT_ID=<id>.access CF_ACCESS_CLIENT_SECRET=<secret>
```

### Call it

POST the audio as the raw request body; everything else goes in the query string.

```bash
curl -X POST --data-binary @examples/short1.wav \
  -H "CF-Access-Client-Id: $CF_ACCESS_CLIENT_ID" \
  -H "CF-Access-Client-Secret: $CF_ACCESS_CLIENT_SECRET" \
  "https://api.olewave.com/olign/v0.9?ref_text=what%20is%20better%20a%20fruit%20or%20hamburger&core_type=en.word.score&rank=100&accent=2&show_phone_details=1"
```

Or run [`examples/rest_client.sh`](examples/rest_client.sh), which reads the two
variables and prints a summary:

```bash
./examples/rest_client.sh --url https://api.olewave.com/olign/v0.9 --core-type en.word.score \
  --wav examples/short1.wav --ref-text "what is better a fruit or hamburger"
```

| query parameter | default | values |
|---|---|---|
| `ref_text` | *(required)* | what the speaker was supposed to say, URL-encoded |
| `core_type` | `en.sent.score` | `en.word.score`, `en.sent.score`, `en.sent.child`, `en.pred.exam`, `en.phone.align` |
| `rank` | `100` | score scale; `100` means scores are 0–100 |
| `accent` | `2` | `1` = UK, `2` = US |
| `show_phone_details` | `1` | `1` includes the per-phone breakdown |

The body is any common audio format, up to **50 MB**.

### Handle the result

The response is one JSON object:

```jsonc
{
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

- **Check `errId`, not just the HTTP status**: it can be non-zero on a `200`.
- **All times are milliseconds**: `begin: 470` is 0.47 s.
- `details[]` has one entry per word of `ref_text`, even words the speaker never
  said; a near-zero `score` means mispronounced *or* skipped.

```python
d = response.json()
if d["errId"] != 0:
    raise RuntimeError(d["error"])
for w in d["result"]["details"]:
    print(w["char"], w["score"], w["begin"] / 1000, w["end"] / 1000)
```

| code | when |
|---|---|
| `200` | parse the body, then check `errId` |
| `400` | audio that cannot be decoded |
| `403` | missing or invalid service token |
| `413` | body over 50 MB |
| `422` | `ref_text` missing |

### Reproduce the fa-bench numbers

fa-bench makes exactly this call: one request per utterance with the whole
audio, several in parallel.

1. **Set up fa-bench** as [its README](https://github.com/olewave/fa-bench#readme)
   describes. The corpora are licensed separately; fa-bench works from your own
   copies.
2. **Point its olign aligner here**, in fa-bench's `.fabench.env` (untracked):

   ```bash
   OLIGN_BASE_URL=https://api.olewave.com/olign/v0.9
   CF_ACCESS_CLIENT_ID=<id>.access
   CF_ACCESS_CLIENT_SECRET=<secret>
   ```

3. **Align and score:** `evals/run_evals.sh olign`.

Check the version first. The paper measures **Olign v1.0.0** ("Olign 1.0"),
which this endpoint serves through API v0.9; every response carries its versions
in `X-Olign-*-Version` headers, and for this build they read:

```
X-Olign-API-Version:        v0.9.0
X-Olign-Extractor-Version:  v1.0.0
X-Olign-Transducer-Version: v0.1.0
X-Olign-Analyzer-Version:   v0.9.0
```

What to expect: the paper's alignments were made in August 2026 on a pre-release
server, not on this public build, so individual boundaries differ by a few
milliseconds (8.9 ms median per utterance), but the totals agree. Buckeye test
(clean), scored with fa-bench's current scorer:

| Buckeye test, clean | paper | public build `98728396` |
|---|---|---|
| word MAE (ms) | 22.5 | 22.3 |
| word F1 @20 ms | 0.744 | 0.747 |
| phone MAE (ms) | 12.7 | 12.3 |
| PER (%) | 28.2 | 28.2 |
| phone F1 @20 ms | 0.522 | 0.526 |

The public build gives identical timings for the same file on every run. Allow
about 0.1 ms and 0.002 for scorer drift: the current scorer gives the paper's own
alignments 22.6 ms word MAE and 0.524 phone F1. Only Buckeye test (clean) has
been re-measured so far.

---

## Tests

| test | needs | checks |
|---|---|---|
| `python3 -m unittest tests.test_v1_offline -v` | nothing | `examples/v1_process.py` on the sample result: summary, CSVs, and TextGrid tiers with no gaps or overlaps |
| `python3 -m unittest tests.test_v1_live -v` | `OLIGN_KEY` | every clip in `test-data/` through the v1.0 API: the length, that nearly every word comes back spoken, times in order and inside the audio, every phone inside its word, scores 0–100, and that `v1_process.py` reads the result. About 3 minutes, and 5.5 minutes of your daily allowance |
| the `rest_client.sh` call above | the service token | the v0.9 endpoint: `short1.wav` with `en.word.score` must give `overall=87  words=7  wavetime=4480 (ms)` |

[`test-data/`](test-data/) holds three LibriSpeech recordings with their
transcripts (11 s of FLAC, 56 s and 3.4 min of Opus), credited in
[`test-data/README.md`](test-data/README.md); [`test-data/cases.json`](test-data/cases.json)
lists what the live test sends and expects.

## License

Copyright 2026 Olewave, LLC (https://www.olewave.com). The code and
documentation here are licensed under the [Apache License 2.0](LICENSE). The
recordings in [`test-data/`](test-data/) are from LibriSpeech and keep their own
license, CC BY 4.0; see [`test-data/README.md`](test-data/README.md).
