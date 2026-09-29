# Version map

Which **olign server release** each client release targets. The machine-readable
pin is [`OLIGN_VERSION`](OLIGN_VERSION); this table is the human summary.

| olign-client | olign server | API endpoint            | notes           |
|--------------|--------------|-------------------------|-----------------|
| **v1.0.0**   | API **v1.0.0** | `/olign/v1`           | jobs API (beta): whole recordings, transcript optional; still carries the v0.9 clients |
| **v0.9.0**   | **v0.9.0**   | `/olign/v0.9`           | first release   |

**v1.0 carries two APIs.** Its new client, `examples/v1_client.py`, speaks API
v1 (`/olign/v1`, jobs; the server answers `X-Olign-Api-Version: v1.0.0`). Its
v0.9 clients (REST, WebSocket, gRPC) still speak v0.9.0, so
[`OLIGN_VERSION`](OLIGN_VERSION) stays `v0.9.0`: `rest_client.sh` sends it as
`X-Olign-Client-Version`, and a v0.9 server rejects a MAJOR.MINOR mismatch with
`400`. The v1 API has no pin or handshake yet; `tests/test_v1_live.py` checks
the client against the live service.

## How the two repos stay in step

olign-client and olign are separate repos, so nothing structurally forces them
together. Three things keep them aligned, weakest to strongest:

1. **The `X.Y` is the API version.** The server serves its routes under
   `/olign/vX.Y`, so client release line `X.Y` targets server `X.Y` — the URL
   itself carries the contract version. Keep `X.Y` in lockstep; `Z` may differ
   (a client-only fix bumps only the client's `Z`). From v1.0 the client's `X.Y`
   follows the newest API it covers, and `OLIGN_VERSION` pins the v0.9 contract
   its older clients speak.

2. **The pin.** [`OLIGN_VERSION`](OLIGN_VERSION) records the exact olign release
   this branch was verified against, committed alongside the code and auditable
   in git — the same idea as olign pinning pkaldi via `PKALDI_VERSION`.

3. **The drift check** — `./tools/check_proto_sync.sh`. The `proto/` files here
   are a *vendored copy* of olign's `src/io/proto`, so they can silently drift.
   The script fetches olign at `OLIGN_VERSION` and diffs; drift is an error.
   Runs in CI (`proto-sync`) on every push and tag.

4. **The contract test** — CI job `contract-test` runs the actual
   `olign:$OLIGN_VERSION` image as a service and drives a real assessment
   through `examples/rest_client.sh`, asserting the scorecard (7 words, overall
   87, wavetime 4480). Text-identical protos can still hide a behavioural break; this catches
   that. It is the strongest of the four.

5. **The runtime handshake** — at request time the client sends
   `X-Olign-Client-Version` and the server answers with `X-Olign-Api-Version`.
   The server compares **MAJOR.MINOR only** and rejects a real mismatch with
   `400` naming both versions; a patch difference always passes, and the request
   header is optional so older clients keep working. This is the last line of
   defence: it catches a client pointed at the wrong deployment, which nothing
   at build time can see.

## Response headers

Every REST response carries four versions:

| header | example |
|---|---|
| `X-Olign-Api-Version` | `v0.9.0` (`v1.0.0` on `/olign/v1`), the wire contract you are talking to |
| `X-Olign-Extractor-Version` | `v1.0.0` |
| `X-Olign-Transducer-Version` | `v0.1.0` |
| `X-Olign-Analyzer-Version` | `v0.9.0` |

**Log all four alongside any score you store.** Scores move when Olign is
upgraded, and these are what let you tell *"the speaker changed"* from *"the
yardstick changed"*. They are reported
only: there is no way to request a particular version, and a given deployment
serves exactly one of each.

`X-Olign-Api-Version` is published in full but only `MAJOR.MINOR` is enforced,
so `v0.9.0` and `v0.9.1` interoperate.

> **Scores are not bit-reproducible across versions**, and historically were
> not reproducible even for identical input on one server. That is fixed as of
> `X-Olign-Extractor-Version` `v0.5.0`.

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
3. `./tools/check_proto_sync.sh` must pass.
4. Smoke-test the examples against the live API.
5. Update this table, commit, then branch/tag:
   `git checkout -b 1.0 main && git tag v1.0.0 && git push -u origin 1.0 v1.0.0`

Branch/tag layout mirrors olign: dev on `main`, a long-lived `X.Y` branch per
release line, and a `vX.Y.Z` tag per release.
