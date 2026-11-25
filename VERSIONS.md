# Version map

Since v1.1.4 the `olign` package, Olign and its API share **one version
number**: every Olign release ships a package release with the same number,
even when the client did not change. 1.2.0 is skipped: PyPI never reuses a
number, and a first upload with it was withdrawn.

| olign-client | Olign | API | endpoint | notes |
|--------------|-------|-----|----------|-------|
| **v1.2.2**   | **v1.2.2** | **v1.2.2** | `/olign/v1` | the package is unchanged; Olign times long recordings more closely, and reads stretches of exact digital silence with a faint noise floor; the sample result is Olign v1.2.2's: the same word times, and "what", right after the clip's 0.44 s of digital silence, has one phone edge 16 ms earlier and scores 90 (was 55) |
| v1.2.1       | v1.2.1 | v1.2.1 | `/olign/v1` | phones only on request: `timestamps=word\|phone` (word by default) in the package, the CLI and the example client; the TextGrid has a phones tier only when the result has phones; the sample result is Olign v1.2.1's, sent with `timestamps=phone` |
| v1.1.5       | v1.1.5 | v1.1.5 | `/olign/v1` | the dashboard is now dashboard.olewave.com (tycho.olewave.com redirects there); Olign's results are v1.1.4's; the sample result is Olign v1.1.5's |
| **v1.1.4**   | v1.1.4 | v1.1.4 | `/olign/v1` | first release on PyPI (`pip install olign`); `result.pauses` and `result.phrases`, `word_edges=phonetic\|audible` and `align_untranscribed` in the package, the CLI and the example client; the sample result is Olign v1.1.4's |
| **v1.0.0**   | v1.0.0 | v1.0.0 | `/olign/v1` | jobs API (beta): whole recordings, transcript optional; still carries the v0.9 clients |
| **v0.9.0**   | v0.9.0 | v0.9.0 | `/olign/v0.9` | first release |

**v1.x carries two APIs.** The `olign` package and `examples/v1_client.py`
speak API v1 (`/olign/v1`, jobs; the server answers `X-Olign-API-Version:
v1.2.1`). The v1 API changes were additive until v1.2.1: a v1.0.0 request still
works, and older clients read a newer result as long as they ignore fields they
do not know. v1.2.1 is the exception: a request without `timestamps=phone` gets
no phones, so an older package writes an empty phones tier, and code that reads
phones sends `timestamps=phone`. Its
v0.9 clients (REST, WebSocket, gRPC) still speak v0.9.0, so
[`OLIGN_VERSION`](OLIGN_VERSION) stays `v0.9.0`: `rest_client.sh` sends it as
`X-Olign-Client-Version`, and a v0.9 server rejects a MAJOR.MINOR mismatch with
`400`. The v1 API has no pin or handshake yet; `tests/test_v1_live.py` checks
the client against the live service.

## How the two repos stay in step

olign-client and olign are separate repos, so nothing structurally forces them
together. These keep them aligned, weakest to strongest:

1. **One version number.** From v1.1.4 a client release carries the number
   of the Olign release it was made with, which is also the API version the
   server reports. `OLIGN_VERSION` still pins the v0.9 contract the older
   clients speak.

2. **The pin.** [`OLIGN_VERSION`](OLIGN_VERSION) records the exact olign release
   this branch was verified against, committed alongside the code and auditable
   in git — the same idea as olign pinning pkaldi via `PKALDI_VERSION`.

3. **The drift check.** The `proto/` files here are a *vendored copy* of olign's
   protos, so they can silently drift. Olewave checks them against olign at
   `OLIGN_VERSION` before each release.

4. **The contract test.** `examples/rest_client.sh` against the live v0.9
   endpoint must give the known scorecard for `examples/short1.wav` (7 words,
   overall 87, wavetime 4480; see the README's Tests). Text-identical protos can
   still hide a behavioural break; this catches it.

5. **The runtime handshake** — at request time the client sends
   `X-Olign-Client-Version` and the server answers with `X-Olign-Api-Version`.
   The server compares **MAJOR.MINOR only** and rejects a real mismatch with
   `400` naming both versions; a patch difference always passes, and the request
   header is optional so older clients keep working. This is the last line of
   defence: it catches a client pointed at the wrong deployment, which nothing
   at build time can see.

## Response headers

Every REST response carries its API version, and a `/olign/v1` response also
names the Olign release that did the work. A v0.9 answer also carries its
versions in its body, as `versions`, since 2026-10-11:

| header | example |
|---|---|
| `X-Olign-Api-Version` | `v0.9.0` (`v1.1.5` on `/olign/v1`), the wire contract you are talking to |
| `X-Olign-Version` | `v1.1.5`, the Olign release; `/olign/v1` only |

**Log the release alongside any score you store.** Scores move when Olign is
upgraded, and the release is what lets you tell *"the speaker changed"* from
*"the yardstick changed"*. On `/olign/v1` that is `X-Olign-Version`; the
`olign` package saves both headers under `_versions` in the JSON it writes.
`/olign/v0.9` doesn't send it, so log the API version and the date; the README
says which release that endpoint served when. Versions are reported only: there
is no way to request a particular one.

`X-Olign-Api-Version` is published in full but only `MAJOR.MINOR` is enforced,
so `v0.9.0` and `v0.9.1` interoperate.

**Why vendor the protos instead of using a git submodule?** olign-client is for
external developers who do not have access to the private olign server repo. A
submodule would make the client unusable for them. Vendoring keeps the client
self-contained; the drift check is what buys back the safety a submodule would
have given.

## Cutting a client release

1. Confirm the server release exists (e.g. olign `v1.0.0`) and is deployed.
2. Update `OLIGN_VERSION` if the v0.9 contract moved (it stays `v0.9.0` for
   v1.0, see above), re-copy `proto/` if the server's changed, re-run
   `./gen_stubs.sh`, update the endpoint/URL in `README.md` if `X.Y` moved.
3. Check `proto/` against olign at the pinned release.
4. Smoke-test the examples against the live API.
5. Update this table, commit, then branch/tag:
   `git checkout -b 1.0 main && git tag v1.0.0 && git push -u origin 1.0 v1.0.0`

Branch/tag layout mirrors olign: dev on `main`, a long-lived `X.Y` branch per
release line, and a `vX.Y.Z` tag per release.
