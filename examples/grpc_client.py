#!/usr/bin/env python3
"""Stream a wav at olign over gRPC and print the assessment.

Uses olign.Speech/Assess -- the service whose wire path (/olign.Speech/Assess)
a proxy can route with `^/olign\\.`, alongside `^/olign/` for REST+WS. (The
original olewave.olign.OlewaveSpeech/StreamingInference is still served for
existing clients; it takes the same messages and returns the same scores.)

It is a bidirectional stream:
  * the FIRST request carries the JSON config and no audio;
  * every later request carries a chunk of HEADERLESS little-endian int16 PCM
    at 16 kHz mono (the server accepts nothing else on this door);
  * responses come back as StreamingInferenceResponse.json_output.

Run ./gen_stubs.sh once first.

    python3 examples/grpc_client.py --host localhost:50051 \
        --wav examples/short1.wav --ref-text "what is better a fruit or hamburger"
"""
import argparse
import json
import sys
import wave
from pathlib import Path

import grpc

# The generated stubs import each other by bare module name, so each proto
# directory has to be importable.
_ROOT = Path(__file__).resolve().parent.parent
for _rel in ("proto/assessment", "proto/common", "proto"):
    sys.path.insert(0, str(_ROOT / _rel))

try:
    import services_pb2  # noqa: E402  (the messages: still package olewave.olign)
    import olign_service_pb2_grpc  # noqa: E402  (the service: package olign)
except ImportError:
    raise SystemExit("stubs missing -- run ./gen_stubs.sh first "
                     "(and pip install -r requirements.txt)")

# The server validates these and rejects anything else.
SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_BYTES = 2
CORE_TYPES = ("en.word.score", "en.sent.score", "en.sent.child",
              "en.pred.exam", "en.phone.align")


def open_wav(path):
    """Open + validate the wav BEFORE the RPC starts.

    gRPC drains the request iterator on its own thread, so raising from inside
    the chunk generator would kill that thread and hang the call instead of
    failing cleanly.
    """
    try:
        wf = wave.open(str(path), "rb")
    except (wave.Error, FileNotFoundError) as err:
        raise SystemExit(f"{path}: not a readable wav ({err})")
    if wf.getframerate() != SAMPLE_RATE:
        raise SystemExit(f"{path}: {wf.getframerate()} Hz, need {SAMPLE_RATE}. "
                         "Resample it, or use the REST door which transcodes.")
    if wf.getnchannels() != CHANNELS:
        raise SystemExit(f"{path}: {wf.getnchannels()} channels, need mono.")
    if wf.getsampwidth() != SAMPLE_BYTES:
        raise SystemExit(f"{path}: {wf.getsampwidth()*8}-bit, need 16-bit.")
    return wf


def build_config(ref_text, core_type, rank, accent, phone_details):
    return json.dumps({
        "audio": {"audio_type": "wav", "sample_rate": SAMPLE_RATE,
                  "channel": CHANNELS, "sample_bytes": SAMPLE_BYTES},
        "app": {"user_id": "olign-client", "application_id": "olign-client"},
        "request": {
            "core_type": core_type,
            "ref_text": ref_text,
            "rank": rank,
            "accent": accent,
            "result": {"details": {"raw": 1, "sym": 0,
                                   "phone": 1 if phone_details else 0}},
        },
        "vad": {"vad_enable": 1},
    })


def requests(config_json, wf, chunk_ms):
    """Config first, then ~chunk_ms of PCM per message (wave strips the header)."""
    yield services_pb2.StreamingInferenceRequest(
        assessment_config=services_pb2.StreamingAssessmentJsonConfig(
            json_config=config_json))
    frames = SAMPLE_RATE * chunk_ms // 1000
    while True:
        chunk = wf.readframes(frames)
        if not chunk:
            return
        yield services_pb2.StreamingInferenceRequest(audio_content=chunk)


def report(payload):
    j = json.loads(payload)
    r = j.get("response", j)
    if r.get("errId"):
        print(f"error {r['errId']}: {r.get('error')}", file=sys.stderr)
        return 1
    res = r.get("result", {})
    print(f"overall={res.get('overall')}  words={len(res.get('details', []))}  "
          f"wavetime={res.get('wavetime')} (ms)  is_en={res.get('is_en')}")
    for w in res.get("details", []):
        flags = [k.replace("is_", "").replace("_err", "")
                 for k, v in w.get("error_info", {}).items() if v]
        print(f"  {w['char']:<16} {w['score']:>3}   "
              f"{w['begin']/1000:.2f}-{w['end']/1000:.2f}s"
              f"{'   [' + ','.join(flags) + ']' if flags else ''}")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", default="localhost:50051")
    ap.add_argument("--wav", required=True)
    ap.add_argument("--ref-text", required=True,
                    help="what the speaker was supposed to say")
    ap.add_argument("--core-type", default="en.word.score", choices=CORE_TYPES)
    ap.add_argument("--rank", type=int, default=100)
    ap.add_argument("--accent", type=int, default=2, choices=(1, 2),
                    help="1=UK, 2=US")
    ap.add_argument("--no-phone-details", action="store_true")
    ap.add_argument("--chunk-ms", type=int, default=100,
                    help="PCM per message. ~100ms matches the online decoder; "
                         "larger chunks can shift endpointing and scores.")
    ap.add_argument("--tls", action="store_true",
                    help="use TLS. Required for the public API "
                         "(api.olewave.com:443); direct ports are plaintext.")
    args = ap.parse_args()

    wf = open_wav(args.wav)
    config = build_config(args.ref_text, args.core_type, args.rank,
                          args.accent, not args.no_phone_details)

    channel = (grpc.secure_channel(args.host, grpc.ssl_channel_credentials())
               if args.tls else grpc.insecure_channel(args.host))
    with channel:
        stub = olign_service_pb2_grpc.SpeechStub(channel)
        try:
            last = None
            for resp in stub.Assess(requests(config, wf, args.chunk_ms)):
                # The server may answer before we've sent everything: with VAD on
                # it endpoints at end-of-speech. gRPC lets us just stop reading;
                # the last json_output is the final result.
                if resp.json_output:
                    last = resp.json_output
            if last is None:
                print("no response from server", file=sys.stderr)
                return 1
            return report(last)
        except grpc.RpcError as err:
            print(f"rpc failed: {err.code().name}: {err.details()}",
                  file=sys.stderr)
            return 1
        finally:
            wf.close()


if __name__ == "__main__":
    sys.exit(main())
