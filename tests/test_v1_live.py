"""Live checks against the olign API v1: each clip in test-data/cases.json goes
through examples/v1_client.py and the answer is checked. Needs a key:

    export OLIGN_KEY=gvk_...            # https://tycho.olewave.com -> Profile -> API key
    python3 -m unittest tests.test_v1_live -v

Skipped without OLIGN_KEY. The four jobs run one after another on the server;
allow about three minutes. One run sends 5.5 minutes of audio, which counts
against the account's 60 minutes a day.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
DATA = ROOT / "test-data"
CLIENT = ROOT / "examples" / "v1_client.py"
PROCESS = ROOT / "examples" / "v1_process.py"
CASES = json.loads((DATA / "cases.json").read_text())


@unittest.skipUnless(os.environ.get("OLIGN_KEY"), "set OLIGN_KEY to run the live tests")
class LiveV1(unittest.TestCase):
    def run_case(self, name: str) -> dict:
        case = CASES[name]
        out = pathlib.Path(tempfile.mkdtemp()) / f"{name}.json"
        cmd = [sys.executable, str(CLIENT), str(DATA / case["audio"]), "-o", str(out)]
        if case.get("transcript"):
            cmd += ["--transcript", str(DATA / case["transcript"])]
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=900)
        if r.returncode and "HTTP 429" in r.stderr:
            self.skipTest("the account's 60 minutes for today are used up: " + r.stderr.strip().splitlines()[-1])
        self.assertEqual(r.returncode, 0, r.stderr)
        st = json.loads(out.read_text())

        self.assertEqual(st["state"], "done")
        self.assertEqual(st["transcript_source"], "client" if case.get("transcript") else "asr")
        self.assertAlmostEqual(st["audio_seconds"], case["seconds"], delta=0.25)
        r = st["result"]
        words = [w for w in r["words"] if not w.get("annotation")]
        if case.get("words"):
            self.assertGreaterEqual(len(words), 0.9 * case["words"], "most transcript words come back")
            spoken = sum(w.get("spoken", True) for w in words)
            self.assertGreaterEqual(spoken, 0.9 * len(words), "clean read speech: nearly every word is spoken")
        else:
            self.assertGreater(len(words), 0, "ASR found speech")
        last = 0.0
        for w in words:
            self.assertLessEqual(0.0, w["begin"]); self.assertLessEqual(w["begin"], w["end"])
            self.assertLessEqual(w["end"], st["audio_seconds"] + 0.05)
            self.assertGreaterEqual(w["begin"] + 1e-6, last, f"words out of order at {w['word']}")
            last = w["begin"]
            self.assertTrue(0 <= w["score"] <= 100)
            phones = w.get("phones") or []
            for p in phones:
                self.assertTrue(0 <= p["score"] <= 100, p)
                # Every phone sits inside its word, including one olign could
                # not place: zero length, where it falls in order.
                self.assertTrue(w["begin"] - 0.01 <= p["begin"] <= p["end"] <= w["end"] + 0.01, p)
            starts = [p["begin"] for p in phones]
            self.assertEqual(starts, sorted(starts), f"phones out of order in {w['word']!r}")
        self.assertTrue(0 <= r["stats"]["overall_mean"] <= 100)
        self.assertIn("x-olign-api-version", {k.lower() for k in st["_versions"]})

        tg = out.with_suffix(".TextGrid")
        subprocess.run([sys.executable, str(PROCESS), str(out), "--csv", str(out.parent), "--textgrid", str(tg)],
                       check=True, capture_output=True)
        self.assertTrue(tg.exists() and (out.parent / "words.csv").exists())
        return st

    def test_short_flac_with_transcript(self):
        self.run_case("short_flac_with_transcript")

    def test_medium_opus_with_transcript(self):
        self.run_case("medium_opus_with_transcript")

    def test_medium_opus_without_transcript(self):
        self.run_case("medium_opus_without_transcript")

    def test_long_opus_with_transcript(self):
        self.run_case("long_opus_with_transcript")


if __name__ == "__main__":
    unittest.main()
