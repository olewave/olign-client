#!/usr/bin/env python3
"""Stream a wav at olign over WebSocket and print the assessment.

Protocol on GET /v1/assess/stream:
  1. first TEXT frame   -> the config JSON
  2. BINARY frames      -> headerless little-endian int16 PCM, 16 kHz mono
  3. final TEXT frame   -> {"event":"end"} asks for the result
  4. server replies with a TEXT frame: the result JSON

The server may answer EARLY: with vad_enable the decoder endpoints at the end of
speech and sends the result itself. Once that arrives we stop sending -- pushing
audio at a finished session is pointless (the server ignores it).

    pip install websocket-client
    python3 examples/ws_client.py --url ws://localhost:8080/v1/assess/stream \
        --wav examples/short1.wav --ref-text "what is better a fruit or hamburger"
"""
import argparse
import json
import sys
import wave

try:
    import websocket  # websocket-client
except ImportError:
    raise SystemExit("pip install websocket-client")

SAMPLE_RATE = 16000
CHANNELS = 1
SAMPLE_BYTES = 2
CORE_TYPES = ("en.word.score", "en.sent.score", "en.sent.child",
              "en.pred.exam", "en.phone.align")


def open_wav(path):
    try:
        wf = wave.open(str(path), "rb")
    except (wave.Error, FileNotFoundError) as err:
        raise SystemExit(f"{path}: not a readable wav ({err})")
    if (wf.getframerate(), wf.getnchannels(), wf.getsampwidth()) != \
            (SAMPLE_RATE, CHANNELS, SAMPLE_BYTES):
        raise SystemExit(
            f"{path}: need 16 kHz mono 16-bit, got {wf.getframerate()} Hz / "
            f"{wf.getnchannels()} ch / {wf.getsampwidth()*8}-bit. "
            "Resample it, or use the REST door which transcodes.")
    return wf


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
        print(f"  {w['char']:<16} {w['score']:>3}   "
              f"{w['begin']/1000:.2f}-{w['end']/1000:.2f}s")
    return 0


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--url", default="ws://localhost:8080/v1/assess/stream")
    ap.add_argument("--wav", required=True)
    ap.add_argument("--ref-text", required=True)
    ap.add_argument("--core-type", default="en.word.score", choices=CORE_TYPES)
    ap.add_argument("--rank", type=int, default=100)
    ap.add_argument("--accent", type=int, default=2, choices=(1, 2))
    ap.add_argument("--chunk-ms", type=int, default=100)
    args = ap.parse_args()

    wf = open_wav(args.wav)
    config = json.dumps({
        "audio": {"audio_type": "wav", "sample_rate": SAMPLE_RATE,
                  "channel": CHANNELS, "sample_bytes": SAMPLE_BYTES},
        "app": {"user_id": "olign-client", "application_id": "olign-client"},
        "request": {"core_type": args.core_type, "ref_text": args.ref_text,
                    "rank": args.rank, "accent": args.accent,
                    "result": {"details": {"raw": 1, "sym": 0, "phone": 1}}},
        "vad": {"vad_enable": 1},
    })

    ws = websocket.create_connection(args.url, timeout=30)
    try:
        ws.send(config)                       # 1. config as TEXT
        ws.settimeout(0.01)
        frames = SAMPLE_RATE * args.chunk_ms // 1000
        result = None
        while result is None:
            chunk = wf.readframes(frames)
            if not chunk:
                break
            ws.send_binary(chunk)             # 2. PCM as BINARY
            # Did the server endpoint and answer already? (non-blocking peek)
            try:
                result = ws.recv()
            except websocket.WebSocketTimeoutException:
                pass
        if result is None:
            ws.settimeout(30)
            ws.send('{"event":"end"}')        # 3. ask for the result
            result = ws.recv()                # 4. result JSON
        return report(result)
    finally:
        wf.close()
        try:
            ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    sys.exit(main())
