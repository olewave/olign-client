"""The ``olign`` command.

    olign align talk.mp3 --textgrid            # writes talk.TextGrid
    olign align talk.mp3 --transcript talk.txt --srt --vtt
    olign export talk.json --csv words.csv     # from a saved result, no upload
    olign get 6abb52b92239acba --srt           # a job you stopped waiting for

Progress goes to stderr and a short summary to stdout.
"""

from __future__ import annotations

import argparse
import pathlib
import sys
import time
from typing import List, Optional

from . import __version__
from .client import Client
from .errors import OlignError
from .result import Result

# flag -> (file suffix, Result method)
FORMATS = {
    "textgrid": (".TextGrid", "to_textgrid"),
    "srt": (".srt", "to_srt"),
    "vtt": (".vtt", "to_vtt"),
    "csv": (".csv", "to_csv"),
    "json": (".json", "to_json"),
}
AUTO = "\0auto"


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="olign", description="Word and phone timings for English speech, from the Olign API.",
        epilog="Set OLIGN_KEY to your API key (https://dashboard.olewave.com > Profile > API keys).")
    ap.add_argument("--version", action="version", version=f"olign {__version__}")
    sub = ap.add_subparsers(dest="command", metavar="COMMAND")

    al = sub.add_parser("align", help="align a recording and save the timings",
                        description="Upload a recording, wait for the job and save the timings. "
                                    "A flag given without a file name writes AUDIO's name with the "
                                    "format's extension in the current directory. With no output "
                                    "flag the result is saved as JSON.")
    al.add_argument("audio", type=pathlib.Path, help="the recording (wav, mp3, m4a, flac, ogg/opus or webm)")
    al.add_argument("--transcript", "-t", type=pathlib.Path, metavar="FILE",
                    help="UTF-8 text of what is said. Without it, olign transcribes the audio first")
    al.add_argument("--word-edges", choices=("phonetic", "audible"),
                    help="phonetic (the default) or audible: words start and end where a listener hears "
                         "them, as dubbing and subtitles need (clean recordings)")
    al.add_argument("--align-untranscribed", action="store_true",
                    help="also align the speech the transcript leaves out (fillers, repeats)")
    _add_outputs(al, with_json=True)
    al.add_argument("--api", metavar="URL", help="API base URL (default $OLIGN_API_URL, else the public API)")
    al.add_argument("--every", type=float, default=5.0, metavar="SECONDS", help="poll interval (default 5)")
    al.add_argument("--quiet", "-q", action="store_true", help="no progress on stderr")

    gt = sub.add_parser("get", help="wait for a job you already submitted and save it",
                        description="Fetch a job by its id, wait until it is done and save it. "
                                    "Useful after you stop 'olign align' while it waits. "
                                    "With no output flag the result is saved as JSON.")
    gt.add_argument("job_id", help="the id 'olign align' printed")
    _add_outputs(gt, with_json=True)
    gt.add_argument("--api", metavar="URL", help="API base URL (default $OLIGN_API_URL, else the public API)")
    gt.add_argument("--every", type=float, default=5.0, metavar="SECONDS", help="poll interval (default 5)")
    gt.add_argument("--quiet", "-q", action="store_true", help="no progress on stderr")

    ex = sub.add_parser("export", help="convert a saved JSON result, without calling the API",
                        description="Write subtitles, a TextGrid or a CSV from a result saved by "
                                    "'olign align --json'.")
    ex.add_argument("result", type=pathlib.Path, help="a JSON result saved by olign")
    _add_outputs(ex, with_json=False)
    return ap


def _add_outputs(p: argparse.ArgumentParser, with_json: bool) -> None:
    help_ = {"textgrid": "Praat TextGrid, a words, a phones and a pauses tier",
             "srt": "SubRip subtitles", "vtt": "WebVTT subtitles with a timestamp on every word",
             "csv": "one row per word", "json": "the full result, readable by 'olign export'"}
    for name in FORMATS:
        if name == "json" and not with_json:
            continue
        p.add_argument(f"--{name}", nargs="?", const=AUTO, metavar="FILE", type=str, help=help_[name])


def outputs(args: argparse.Namespace, stem: str) -> List[tuple]:
    """[(path, method name)] for every format flag that was given."""
    out = []
    for name, (suffix, method) in FORMATS.items():
        value = getattr(args, name, None)
        if value is not None:
            out.append((pathlib.Path(stem + suffix) if value == AUTO else pathlib.Path(value), method))
    return out


def main(argv: Optional[List[str]] = None) -> int:
    ap = build_parser()
    args = ap.parse_args(argv)
    if not args.command:
        ap.print_help(sys.stderr)
        return 2
    run = {"align": run_align, "get": run_get, "export": run_export}[args.command]
    try:
        return run(args)
    except OlignError as e:
        print(f"olign: error: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print(file=sys.stderr)
        return 130


def _say(args: argparse.Namespace):
    return (lambda *_: None) if args.quiet else (lambda m: print(f"olign: {m}", file=sys.stderr, flush=True))


def run_align(args: argparse.Namespace) -> int:
    say = _say(args)
    for f in (args.audio, args.transcript):
        if f is not None and not f.is_file():
            raise OlignError(f"no such file: {f}")
    targets = outputs(args, args.audio.stem) or [(pathlib.Path(args.audio.stem + ".json"), "to_json")]

    client = Client(base_url=args.api, poll_interval=args.every)
    size = args.audio.stat().st_size / 1e6
    say(f"uploading {args.audio.name} ({size:.1f} MB)"
        + ("" if args.transcript else ", no transcript, so olign transcribes it first"))
    t0 = time.monotonic()
    job = client.align(args.audio, transcript=args.transcript, poll=False, word_edges=args.word_edges,
                       align_untranscribed=args.align_untranscribed)
    say(f"job {job.job_id} {job.state}")
    return _wait_and_save(client, job.job_id, job.state, args, targets, args.audio.name, t0)


def run_get(args: argparse.Namespace) -> int:
    client = Client(base_url=args.api, poll_interval=args.every)
    targets = outputs(args, args.job_id) or [(pathlib.Path(args.job_id + ".json"), "to_json")]
    return _wait_and_save(client, args.job_id, "", args, targets, args.job_id, time.monotonic())


def _wait_and_save(client: Client, job_id: str, state: str, args: argparse.Namespace, targets: List[tuple],
                   name: str, t0: float) -> int:
    say = _say(args)
    seen = [state]

    def progress(r: Result) -> None:
        line = r.state + (f" {r.progress:.0%}" if r.progress is not None and r.state == "running" else "")
        if line != seen[0]:
            say(line)
            seen[0] = line

    try:
        result = client.wait(job_id, on_progress=progress)
    except KeyboardInterrupt:
        print(f"\nolign: stopped waiting. Job {job_id} keeps running, and "
              f"'olign get {job_id}' saves it later.", file=sys.stderr)
        return 130
    say(f"done in {time.monotonic() - t0:.0f} s")
    _summary(result, name)
    _write(result, targets)
    return 0


def run_export(args: argparse.Namespace) -> int:
    if not args.result.is_file():
        raise OlignError(f"no such file: {args.result}")
    try:
        result = Result.load(args.result)
    except (ValueError, KeyError, TypeError) as e:
        raise OlignError(f"{args.result} is not an olign result: {e}") from None
    targets = outputs(args, args.result.stem)
    if not targets:
        raise OlignError("name an output with --textgrid, --srt, --vtt or --csv")
    _summary(result, args.result.name)
    _write(result, targets)
    return 0


def _summary(r: Result, name: str) -> None:
    timed = sum(1 for _ in r.timed_words())
    source = {"client": "aligned to your transcript", "asr": "transcribed by olign"}.get(
        r.transcript_source or "", "aligned")
    length = f"{r.audio_seconds:.2f} s of audio, " if r.audio_seconds is not None else ""
    pauses = f", {len(r.pauses)} pauses, {len(r.phrases)} phrases" if r.pauses or r.phrases else ""
    print(f"{name}: {length}{timed} words {source}{pauses}")


def _write(r: Result, targets: List[tuple]) -> None:
    for path, method in targets:
        getattr(r, method)(path)
        print(f"wrote {path}")


if __name__ == "__main__":
    sys.exit(main())
