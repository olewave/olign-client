"""Offline checks for examples/v1_process.py, on the saved real result.

No account, no network:  python3 -m unittest discover -s tests -v
"""

from __future__ import annotations

import csv
import json
import pathlib
import re
import subprocess
import sys
import tempfile
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SAMPLE = ROOT / "examples" / "sample_v1_result.json"
PROCESS = ROOT / "examples" / "v1_process.py"


def textgrid_tiers(text: str) -> dict[str, list[tuple[float, float, str]]]:
    tiers, name = {}, None
    for m in re.finditer(r'name = "([^"]*)"|xmin = ([\d.]+)\s+xmax = ([\d.]+)\s+text = "((?:[^"]|"")*)"', text):
        if m.group(1) is not None:
            name = m.group(1); tiers[name] = []
        else:
            tiers[name].append((float(m.group(2)), float(m.group(3)), m.group(4)))
    return tiers


class ProcessSampleResult(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = json.loads(SAMPLE.read_text())
        cls.tmp = pathlib.Path(tempfile.mkdtemp())
        cls.out = subprocess.run(
            [sys.executable, str(PROCESS), str(SAMPLE), "--csv", str(cls.tmp),
             "--textgrid", str(cls.tmp / "sample.TextGrid")],
            capture_output=True, text=True, check=True).stdout

    def test_summary_names_the_audio_and_the_weakest_word(self):
        words = self.result["result"]["words"]
        self.assertIn(f"{len(words)} spoken", self.out)
        weakest = min(words, key=lambda w: w["score"])["word"]
        self.assertIn(weakest, self.out.split("weakest")[1])

    def test_csvs_hold_every_word_and_phone(self):
        words = self.result["result"]["words"]
        rows = list(csv.DictReader((self.tmp / "words.csv").read_text().splitlines()))
        self.assertEqual([r["word"] for r in rows], [w["word"] for w in words])
        phones = list(csv.DictReader((self.tmp / "phones.csv").read_text().splitlines()))
        self.assertEqual(len(phones), sum(len(w["phones"]) for w in words))

    def test_textgrid_tiers_cover_the_audio_without_gaps_or_overlaps(self):
        xmax = self.result["audio_seconds"]
        tiers = textgrid_tiers((self.tmp / "sample.TextGrid").read_text())
        self.assertEqual(set(tiers), {"words", "phones"})
        for name, iv in tiers.items():
            self.assertAlmostEqual(iv[0][0], 0.0, msg=name)
            self.assertAlmostEqual(iv[-1][1], xmax, msg=name)
            for (_, e1, _), (b2, _, _) in zip(iv, iv[1:]):
                self.assertAlmostEqual(e1, b2, msg=f"{name}: gap or overlap at {e1}")
        labelled = [t for _, _, t in tiers["words"] if t]
        self.assertEqual(labelled, [w["word"] for w in self.result["result"]["words"]])


if __name__ == "__main__":
    unittest.main()
