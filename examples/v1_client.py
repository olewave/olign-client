#!/usr/bin/env python3
"""Submit a recording to olign API v1 and wait for its word and phone timings.

    export OLIGN_KEY=gvk_...        # https://dashboard.olewave.com -> Profile -> API keys
    python3 v1_client.py short1.wav --transcript short1.txt -o result.json

The transcript is optional: without it, olign transcribes the audio itself.
--word-edges audible times words as a listener hears them (dubbing, subtitles;
needs a clean recording); --align-untranscribed also aligns the speech your
transcript leaves out (fillers, repeats).
Uploads are capped at 100 MB, so compress long recordings first (Opus at
32 kbit/s is about 14 MB an hour):

    ffmpeg -i lecture.wav -ac 1 -c:a libopus -b:a 32k lecture.ogg

Standard library only (Python 3.8+). The saved JSON is the API's final status
response, with `result` inside, plus the X-Olign-*-Version headers under
`_versions`: keep those with any score you store, scores change between
model versions. Turn it into tables with v1_process.py.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import sys
import time
import urllib.error
import urllib.request
import uuid

API = "https://api.olewave.com/olign/v1"
# Cloudflare fronts the API and rejects some library defaults as bots
# (HTTP 403 "error code: 1010" for Python-urllib), so name the client.
USER_AGENT = "olign-client-example/1.2"


def multipart(fields: list[tuple[str, str | None, bytes]]) -> tuple[bytes, str]:
    """Build a multipart/form-data body. urllib sends it with a Content-Length,
    which the API requires (it refuses chunked uploads). A field with no
    filename is a plain form value, such as word_edges=audible."""
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, filename, data in fields:
        if filename is None:
            body += f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n".encode()
        else:
            body += (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"; "
                     f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
        body += data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"


def call(req: urllib.request.Request) -> tuple[dict, dict]:
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            versions = {k: v for k, v in r.headers.items() if k.lower().startswith("x-olign-")}
            return json.loads(r.read()), versions
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")[:300]
        hint = {401: " (check OLIGN_KEY)", 402: " (add a card or buy more minutes: Billing on https://dashboard.olewave.com)",
                403: " (blocked by Cloudflare: send a User-Agent header)",
                404: " (unknown job: the service may have restarted; resubmit)",
                429: " (your monthly limit: Settings on https://dashboard.olewave.com)"}.get(e.code, "")
        sys.exit(f"HTTP {e.code}{hint}: {detail}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("audio", help="any common format: wav, mp3, m4a, flac, ogg/opus, webm")
    ap.add_argument("--transcript", help="plain UTF-8 text of what is said (optional)")
    ap.add_argument("--word-edges", choices=("phonetic", "audible"),
                    help="phonetic (the server's default) or audible: the silence before a p, t, k, b, d or g "
                         "stays outside its word, as dubbing and subtitles need (clean recordings)")
    ap.add_argument("--align-untranscribed", action="store_true",
                    help="also align the speech your transcript leaves out; those words come back "
                         "marked \"untranscribed\": true")
    ap.add_argument("--timestamps", choices=("word", "phone"),
                    help="word (the server's default) or phone: each word also carries its phones "
                         "(twice the price)")
    ap.add_argument("-o", "--out", default="result.json")
    ap.add_argument("--api", default=API)
    ap.add_argument("--every", type=float, default=5.0, help="poll interval, seconds")
    a = ap.parse_args()

    key = os.environ.get("OLIGN_KEY") or sys.exit("set OLIGN_KEY (https://dashboard.olewave.com -> Profile -> API keys)")
    fields = [("audio", os.path.basename(a.audio), pathlib.Path(a.audio).read_bytes())]
    if a.transcript:
        fields.append(("transcript", os.path.basename(a.transcript), pathlib.Path(a.transcript).read_bytes()))
    if a.word_edges:
        fields.append(("word_edges", None, a.word_edges.encode()))
    if a.align_untranscribed:
        fields.append(("align_untranscribed", None, b"1"))
    if a.timestamps:
        fields.append(("timestamps", None, a.timestamps.encode()))
    body, ctype = multipart(fields)

    sub, _ = call(urllib.request.Request(a.api, data=body, method="POST",
                                         headers={"X-API-Key": key, "Content-Type": ctype, "User-Agent": USER_AGENT}))
    job = sub["job_id"]
    print(f"job {job}", file=sys.stderr)

    last = None
    while True:
        st, versions = call(urllib.request.Request(f"{a.api}/{job}", headers={"X-API-Key": key, "User-Agent": USER_AGENT}))
        line = st["state"]
        if line != last:
            print(f"  {line}", file=sys.stderr)
            last = line
        if st["state"] in ("done", "failed"):
            break
        time.sleep(a.every)
    if st["state"] == "failed":
        sys.exit(f"job failed: {st.get('error') or 'the API gave no reason'}")

    st["_versions"] = versions
    pathlib.Path(a.out).write_text(json.dumps(st, indent=1))
    r = st["result"]
    print(f"{st['audio_seconds']:.2f} s of audio, {len(r['words'])} words, "
          f"{len(r.get('pauses', []))} pauses, {len(r.get('phrases', []))} phrases "
          f"({versions.get('X-Olign-Version', '?')}) -> {a.out}")


if __name__ == "__main__":
    main()
