#!/usr/bin/env python3
"""Turn an olign API v1 result into something you can read, sort and open.

    python3 v1_process.py sample_v1_result.json                 # summary + least certain words
    python3 v1_process.py sample_v1_result.json --csv out/      # out/words.csv, phones.csv, pauses.csv
    python3 v1_process.py sample_v1_result.json --textgrid out/result.TextGrid   # open in Praat

Input is what v1_client.py saves (the API's final status response). Times are
seconds from the start of the file; a score (0-100) is how sure olign is of the
alignment. A word that was not spoken has "spoken": false and zero duration; a
[bracketed] tag has "annotation": true; a word your transcript left out (sent
with align_untranscribed=1) has "untranscribed": true. `pauses` lists every
stretch of 0.05 s or more that no word covers; `phrases` groups the words
between pauses of 0.1 s or more. Standard library only.
"""

from __future__ import annotations

import argparse
import csv
import json
import pathlib


def summary(st: dict, weakest: int) -> None:
    r = st["result"]
    words = r["words"]
    spoken = [w for w in words if w.get("spoken", True) and not w.get("annotation")]
    unspoken = [w for w in words if w.get("spoken") is False and not w.get("annotation")]
    added = [w for w in words if w.get("untranscribed")]
    pauses, phrases = r.get("pauses", []), r.get("phrases", [])
    versions = st.get("_versions", {})
    print(f"audio      {st['audio_seconds']:.2f} s   transcript from {st.get('transcript_source')}"
          f"   olign {versions.get('X-Olign-Version', '?')}")
    print(f"words      {len(spoken)} spoken, {len(unspoken)} not spoken"
          + (f", {len(added)} untranscribed" if added else ""))
    inner = [p for p in pauses if p["begin"] > 0 and p["end"] < st["audio_seconds"]]
    print(f"pauses     {len(pauses)} ({len(inner)} between words), {len(phrases)} phrase(s)")
    for ph in phrases:
        a, b = ph["words"]
        print(f"  {ph['begin']:7.2f}-{ph['end']:7.2f} s  " + " ".join(w["word"] for w in words[a:b + 1]))
    if spoken:
        speech = sum(w["end"] - w["begin"] for w in spoken)
        print(f"rate       {len(spoken) / max(speech, 1e-9) * 60:.0f} words per minute of speech")
    scored = [w for w in spoken if w.get("score") is not None]
    print(f"\nleast certain {min(weakest, len(scored))} word(s):")
    for w in sorted(scored, key=lambda w: w["score"])[:weakest]:
        ph = [p for p in w.get("phones") or [] if p.get("score") is not None]
        low = min(ph, key=lambda p: p["score"]) if ph else {"ph": "-", "score": "-"}
        print(f"  {w['word']:<16} {w['begin']:7.2f}-{w['end']:7.2f} s  score {w['score']:5.1f}"
              f"   least certain phone: {low['ph']} ({low['score']})")


def write_csv(st: dict, out: pathlib.Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    words = st["result"]["words"]
    with open(out / "words.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["index", "word", "begin_s", "end_s", "score", "spoken", "annotation", "untranscribed"])
        for i, x in enumerate(words):
            w.writerow([i, x["word"], x["begin"], x["end"], x.get("score"),
                        x.get("spoken", True), x.get("annotation", False), x.get("untranscribed", False)])
    with open(out / "phones.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["word_index", "word", "phone", "begin_s", "end_s", "score"])
        for i, x in enumerate(words):
            for p in x.get("phones") or []:
                w.writerow([i, x["word"], p["ph"], p["begin"], p["end"], p["score"]])
    with open(out / "pauses.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["begin_s", "end_s", "seconds"])
        for p in st["result"].get("pauses", []):
            w.writerow([p["begin"], p["end"], round(p["end"] - p["begin"], 3)])
    print(f"wrote {out / 'words.csv'}, {out / 'phones.csv'} and {out / 'pauses.csv'}")


def write_textgrid(st: dict, path: pathlib.Path) -> None:
    """Praat TextGrid with a words tier, a phones tier and a pauses tier. Gaps
    between labelled intervals are filled with empty ones, which Praat requires."""
    xmax = float(st["audio_seconds"])
    words = [w for w in st["result"]["words"] if w["end"] > w["begin"]]
    tiers = {
        "words": [(w["begin"], w["end"], w["word"]) for w in words],
        "phones": [(p["begin"], p["end"], p["ph"]) for w in words for p in w.get("phones") or []
                   if p["end"] > p["begin"]],
        "pauses": [(p["begin"], p["end"], "pause") for p in st["result"].get("pauses", [])],
    }

    def filled(spans):
        out, t = [], 0.0
        for b, e, label in sorted(spans):
            b, e = max(b, t), min(e, xmax)
            if e <= b:
                continue
            if b > t:
                out.append((t, b, ""))
            out.append((b, e, label))
            t = e
        if t < xmax:
            out.append((t, xmax, ""))
        return out

    lines = ['File type = "ooTextFile"', 'Object class = "TextGrid"', "", "xmin = 0", f"xmax = {xmax}",
             "tiers? <exists>", f"size = {len(tiers)}", "item []:"]
    for n, (name, spans) in enumerate(tiers.items(), 1):
        iv = filled(spans)
        lines += [f"    item [{n}]:", '        class = "IntervalTier"', f'        name = "{name}"',
                  "        xmin = 0", f"        xmax = {xmax}", f"        intervals: size = {len(iv)}"]
        for k, (b, e, label) in enumerate(iv, 1):
            text = label.replace('"', '""')
            lines += [f"        intervals [{k}]:", f"            xmin = {b}", f"            xmax = {e}",
                      f'            text = "{text}"']
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n")
    print(f"wrote {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("result", help="JSON saved by v1_client.py")
    ap.add_argument("--weakest", type=int, default=5, help="how many low-scoring words to list")
    ap.add_argument("--csv", type=pathlib.Path, metavar="DIR", help="write words.csv and phones.csv here")
    ap.add_argument("--textgrid", type=pathlib.Path, metavar="FILE", help="write a Praat TextGrid")
    a = ap.parse_args()
    st = json.loads(pathlib.Path(a.result).read_text())
    summary(st, a.weakest)
    if a.csv:
        write_csv(st, a.csv)
    if a.textgrid:
        write_textgrid(st, a.textgrid)


if __name__ == "__main__":
    main()
