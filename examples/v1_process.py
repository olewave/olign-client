#!/usr/bin/env python3
"""Turn an olign API v1 result into something you can read, sort and open.

    python3 v1_process.py sample_v1_result.json                 # summary + weakest words
    python3 v1_process.py sample_v1_result.json --csv out/      # out/words.csv, out/phones.csv
    python3 v1_process.py sample_v1_result.json --textgrid out/result.TextGrid   # open in Praat

Input is what v1_client.py saves (the API's final status response). Times are
seconds from the start of the file; scores are 0-100. A word that was not
spoken has "spoken": false and zero duration; a [bracketed] tag has
"annotation": true. Standard library only.
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
    unspoken = [w for w in words if w.get("spoken") is False]
    print(f"audio      {st['audio_seconds']:.2f} s   transcript from {st.get('transcript_source')}")
    print(f"words      {len(spoken)} spoken, {len(unspoken)} not spoken, "
          f"{len(r['sentence_scores'])} sentence(s)")
    print(f"overall    {r['stats']['overall_mean']}   (mean segment score, 0-100)")
    for s in r["sentence_scores"]:
        print(f"sentence {s['sent_id']}: score {s['sent_score']}  word avg {s['word_avg']}  lowest {s['word_min']}")
    if spoken:
        speech = sum(w["end"] - w["begin"] for w in spoken)
        print(f"rate       {len(spoken) / max(speech, 1e-9) * 60:.0f} words per minute of speech")
    print(f"\nweakest {min(weakest, len(spoken))} word(s):")
    for w in sorted(spoken, key=lambda w: w["score"])[:weakest]:
        low = min(w.get("phones") or [{"ph": "-", "score": w["score"]}], key=lambda p: p["score"])
        print(f"  {w['word']:<16} {w['begin']:7.2f}-{w['end']:7.2f} s  score {w['score']:5.1f}"
              f"   weakest phone: {low['ph']} ({low['score']})")


def write_csv(st: dict, out: pathlib.Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    words = st["result"]["words"]
    with open(out / "words.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["index", "word", "begin_s", "end_s", "score", "sentence", "spoken", "annotation"])
        for i, x in enumerate(words):
            w.writerow([i, x["word"], x["begin"], x["end"], x["score"], x.get("sent_id"),
                        x.get("spoken", True), x.get("annotation", False)])
    with open(out / "phones.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["word_index", "word", "phone", "begin_s", "end_s", "score"])
        for i, x in enumerate(words):
            for p in x.get("phones") or []:
                w.writerow([i, x["word"], p["ph"], p["begin"], p["end"], p["score"]])
    print(f"wrote {out / 'words.csv'} and {out / 'phones.csv'}")


def write_textgrid(st: dict, path: pathlib.Path) -> None:
    """Praat TextGrid with a words tier and a phones tier. Gaps between labelled
    intervals are filled with empty ones, which Praat requires."""
    xmax = float(st["audio_seconds"])
    words = [w for w in st["result"]["words"] if w["end"] > w["begin"]]
    tiers = {
        "words": [(w["begin"], w["end"], w["word"]) for w in words],
        "phones": [(p["begin"], p["end"], p["ph"]) for w in words for p in w.get("phones") or []
                   if p["end"] > p["begin"]],
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
