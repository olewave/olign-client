#!/usr/bin/env bash
# Assess a whole audio file over REST. One request, no dependencies.
#
# The body is the raw audio bytes in ANY container/codec -- the server
# transcodes with FFmpeg. (gRPC/WebSocket, by contrast, require 16 kHz mono
# int16 PCM.) Everything else is a query parameter.
#
#   # direct (default path /v1/assess)
#   ./examples/rest_client.sh --host localhost:8080 \
#       --wav examples/short1.wav --ref-text "what is better a fruit or hamburger"
#
#   # any other endpoint (public API, or a server started with --http-base-path)
#   ./examples/rest_client.sh --url https://api.olewave.com/olign/v0.9 \
#       --wav examples/short1.wav --ref-text "what is better a fruit or hamburger"
#
#   # the public API is behind Cloudflare Access: pass a service token, either
#   # via these env vars or --client-id/--client-secret
#   export CF_ACCESS_CLIENT_ID=<id>.access CF_ACCESS_CLIENT_SECRET=<secret>
set -euo pipefail

HOST=localhost:8080
URL=            # full endpoint; overrides --host
# Cloudflare Access service token (public API). Env by default so secrets stay
# out of shell history / process lists.
CLIENT_ID=${CF_ACCESS_CLIENT_ID:-}
CLIENT_SECRET=${CF_ACCESS_CLIENT_SECRET:-}
WAV=
REF_TEXT=
CORE_TYPE=en.sent.score
RANK=100
ACCENT=2
SHOW_PHONE_DETAILS=1

usage() { sed -n '2,14p' "$0" | sed 's/^# \?//'; exit "${1:-0}"; }
while [ $# -gt 0 ]; do
  case "$1" in
    --host)      HOST=$2; shift 2;;
    --url)       URL=$2; shift 2;;
    --client-id)     CLIENT_ID=$2; shift 2;;
    --client-secret) CLIENT_SECRET=$2; shift 2;;
    --wav)       WAV=$2; shift 2;;
    --ref-text)  REF_TEXT=$2; shift 2;;
    --core-type) CORE_TYPE=$2; shift 2;;
    --rank)      RANK=$2; shift 2;;
    --accent)    ACCENT=$2; shift 2;;
    --no-phone-details) SHOW_PHONE_DETAILS=0; shift;;
    -h|--help)   usage 0;;
    *) echo "unknown option: $1" >&2; usage 1;;
  esac
done
[ -n "$WAV" ] && [ -n "$REF_TEXT" ] || { echo "--wav and --ref-text are required" >&2; usage 1; }
[ -f "$WAV" ] || { echo "no such file: $WAV" >&2; exit 1; }

# ref_text must be URL-encoded (it has spaces, and may have apostrophes).
urlencode() {
  local s=$1 out= c
  for (( i=0; i<${#s}; i++ )); do
    c=${s:i:1}
    case "$c" in
      [a-zA-Z0-9.~_-]) out+="$c";;
      *) out+=$(printf '%%%02X' "'$c");;
    esac
  done
  printf '%s' "$out"
}

# --url wins; otherwise the direct default endpoint on --host.
BASE=${URL:-http://${HOST}/v1/assess}
FULL="${BASE}?ref_text=$(urlencode "$REF_TEXT")&core_type=${CORE_TYPE}&rank=${RANK}&accent=${ACCENT}&show_phone_details=${SHOW_PHONE_DETAILS}"

# Cloudflare Access service token, when the endpoint is protected.
AUTH=()
if [ -n "$CLIENT_ID" ] && [ -n "$CLIENT_SECRET" ]; then
  AUTH=(-H "CF-Access-Client-Id: ${CLIENT_ID}" -H "CF-Access-Client-Secret: ${CLIENT_SECRET}")
fi

# Declare which client this is. The server compares MAJOR.MINOR and rejects a
# real mismatch (0.9 vs 1.0) with 400 + an explanatory body; a patch difference
# is fine. Sending it is optional -- omit the header and the server just serves.
CLIENT_VERSION=$(tr -d ' \r\n' < "$(dirname "$0")/../OLIGN_VERSION" 2>/dev/null) || CLIENT_VERSION=
VERSION_HDR=()
[ -n "$CLIENT_VERSION" ] && VERSION_HDR=(-H "X-Olign-Client-Version: ${CLIENT_VERSION}")

# Deliberately NOT curl -f: -f throws the response body away, which would hide
# the server's explanation (version mismatch, missing ref_text, ...) and leave
# you guessing. Capture the status and print the body on any non-2xx.
tmp=$(mktemp); trap 'rm -f "$tmp"' EXIT
code=$(curl -sS -X POST --data-binary "@${WAV}" \
        -H 'Content-Type: application/octet-stream' \
        "${VERSION_HDR[@]}" "${AUTH[@]}" \
        -o "$tmp" -w '%{http_code}' "$FULL") || {
  echo "request failed (network/DNS/TLS)" >&2; exit 1; }

if [ "$code" -lt 200 ] || [ "$code" -ge 300 ]; then
  echo "HTTP $code" >&2
  cat "$tmp" >&2; echo >&2
  case "$code" in
    400) echo "(400 => see the message above; an API version mismatch reads 'client targets X, server serves Y')" >&2;;
    403) echo "(403 => missing/invalid CF Access service token?)" >&2;;
  esac
  exit 1
fi

if ! command -v python3 >/dev/null 2>&1; then
  cat "$tmp"; echo   # no python -> raw JSON
  exit 0
fi
# heredoc (not -c '...') so the Python can use quotes freely
python3 - "$tmp" <<'PY'
import json, sys
j = json.load(open(sys.argv[1]))
r = j.get("response", j)
if r.get("errId"):
    print(f"error {r['errId']}: {r.get('error')}", file=sys.stderr)
    sys.exit(1)
res = r.get("result", {})
print(f"overall={res.get('overall')}  words={len(res.get('details', []))}  "
      f"wavetime={res.get('wavetime')} (ms)  is_en={res.get('is_en')}")
for w in res.get("details", []):
    print(f"  {w['char']:<16} {w['score']:>3}   "
          f"{w['begin']/1000:.2f}-{w['end']/1000:.2f}s")
PY
