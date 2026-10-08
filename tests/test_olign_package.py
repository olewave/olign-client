"""Offline checks for the olign package (src/olign): the exporters on the saved
real result, the CLI's arguments, and a full submit-and-poll round trip
against a stand-in API on 127.0.0.1.

No account, no network:  python3 -m unittest tests.test_olign_package -v
"""

from __future__ import annotations

import contextlib
import copy
import io
import json
import os
import pathlib
import re
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import olign  # noqa: E402
from olign import cli  # noqa: E402

SAMPLE = ROOT / "examples" / "sample_v1_result.json"
AUDIO = ROOT / "examples" / "short1.wav"
TRANSCRIPT = ROOT / "examples" / "short1.txt"

# Fields the public response is losing (olign/docs/v1_result_trim.md). The
# client must work without every one of them.
DROPPED_JOB = ["stage", "stages", "log_tail"]
DROPPED_RESULT = ["core_type", "sentence_scores", "segments", "stats", "tagged_regions"]
DROPPED_WORD = ["sent_id", "tok", "unit", "score"]


def sample() -> dict:
    return json.loads(SAMPLE.read_text())


def trimmed() -> dict:
    """The sample as the trimmed API will send it, without any score."""
    d = sample()
    for k in DROPPED_JOB + ["_versions"]:
        d.pop(k, None)
    for k in DROPPED_RESULT:
        d["result"].pop(k, None)
    for w in d["result"]["words"]:
        for k in DROPPED_WORD:
            w.pop(k, None)
        for p in w["phones"]:
            p.pop("score", None)
    return d


def textgrid_tiers(text: str) -> dict:
    tiers, name = {}, None
    for m in re.finditer(r'name = "([^"]*)"|xmin = ([\d.]+)\s+xmax = ([\d.]+)\s+text = "((?:[^"]|"")*)"', text):
        if m.group(1) is not None:
            name = m.group(1)
            tiers[name] = []
        else:
            tiers[name].append((float(m.group(2)), float(m.group(3)), m.group(4)))
    return tiers


class Exporters(unittest.TestCase):
    def setUp(self):
        self.r = olign.Result.load(SAMPLE)
        self.words = sample()["result"]["words"]

    def test_load_reads_the_job_and_every_word(self):
        self.assertEqual(self.r.job_id, "6abb52b92239acba")
        self.assertTrue(self.r.done)
        self.assertEqual(self.r.audio_seconds, 4.48)
        self.assertEqual(self.r.transcript_source, "client")
        self.assertEqual(self.r.text, "what is better a fruit or hamburger")
        w = self.r.words[0]
        self.assertEqual((w.word, w.begin, w.end, w.score), ("what", 0.47, 0.75, 55.0))
        self.assertEqual([p.ph for p in w.phones], ["w", "ah", "t"])
        self.assertEqual(self.r.api_version, "v1.0.0")

    def test_textgrid_tiers_cover_the_audio_without_gaps_or_overlaps(self):
        tiers = textgrid_tiers(self.r.to_textgrid())
        self.assertEqual(list(tiers), ["words", "phones"])
        for name, iv in tiers.items():
            self.assertAlmostEqual(iv[0][0], 0.0, msg=name)
            self.assertAlmostEqual(iv[-1][1], 4.48, msg=name)
            for (_, e1, _), (b2, _, _) in zip(iv, iv[1:]):
                self.assertAlmostEqual(e1, b2, msg=f"{name}: gap or overlap at {e1}")
        self.assertEqual([t for _, _, t in tiers["words"] if t], [w["word"] for w in self.words])
        self.assertEqual(len([t for _, _, t in tiers["phones"] if t]), sum(len(w["phones"]) for w in self.words))

    def test_srt_groups_the_sentence_into_one_cue(self):
        self.assertEqual(self.r.to_srt(),
                         "1\n00:00:00,470 --> 00:00:04,360\nwhat is better a fruit or hamburger\n")

    def test_srt_one_word_per_cue(self):
        srt = self.r.to_srt(max_words=1)
        cues = srt.strip().split("\n\n")
        self.assertEqual(len(cues), 7)
        self.assertEqual(cues[1], "2\n00:00:00,840 --> 00:00:01,132\nis")

    def test_srt_breaks_on_length_and_pauses(self):
        self.assertEqual(len(self.r.cues(max_chars=10)), 4)  # "what is", "better a", "fruit or", "hamburger"
        self.assertEqual([len(c) for c in self.r.cues(max_gap=0.2)], [3, 4])  # 0.283 s pause after "better"

    def test_vtt_tags_every_word_after_the_first(self):
        vtt = self.r.to_vtt()
        self.assertTrue(vtt.startswith("WEBVTT\n\n00:00:00.470 --> 00:00:04.360\n"))
        tags = re.findall(r"<(\d\d:\d\d:\d\d\.\d\d\d)>", vtt)
        self.assertEqual(len(tags), 6)
        self.assertEqual(tags, sorted(tags))
        self.assertIn("what <00:00:00.840>is <00:00:01.213>better", vtt)
        self.assertNotIn("<0", self.r.to_vtt(word_timing=False))

    def test_csv_words_and_phones(self):
        rows = self.r.to_csv().splitlines()
        self.assertEqual(rows[0], "index,word,begin,end,score,spoken")
        self.assertEqual(rows[1], "0,what,0.47,0.75,55,true")
        self.assertEqual(len(rows), 1 + 7)
        phones = self.r.to_csv(phones=True).splitlines()
        self.assertEqual(phones[1], "0,what,w,0.47,0.513,0")
        self.assertEqual(len(phones), 1 + 23)

    def test_json_round_trip_keeps_only_public_fields(self):
        d = json.loads(self.r.to_json())
        self.assertEqual(set(d), {"job_id", "state", "audio_seconds", "transcript_source", "result", "_versions"})
        self.assertEqual(set(d["result"]), {"words"})
        back = olign.Result.from_dict(d)
        self.assertEqual(back.words, self.r.words)
        self.assertEqual(back.audio_seconds, 4.48)

    def test_exporters_write_files_when_given_a_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = pathlib.Path(tmp) / "sub" / "short1.srt"
            text = self.r.to_srt(p)
            self.assertEqual(p.read_text(), text)

    def test_trimmed_response_without_scores_still_exports(self):
        r = olign.Result.from_dict(trimmed())
        self.assertEqual(len(r.words), 7)
        self.assertIsNone(r.words[0].score)
        self.assertEqual(r.to_srt(), self.r.to_srt())
        self.assertEqual(textgrid_tiers(r.to_textgrid()), textgrid_tiers(self.r.to_textgrid()))
        self.assertEqual(r.to_csv().splitlines()[1], "0,what,0.47,0.75,,true")
        self.assertNotIn("score", r.to_json())

    def test_unspoken_words_and_tags_stay_off_the_timeline(self):
        d = sample()
        d["result"]["words"].insert(3, {"word": "really", "begin": 2.1, "end": 2.1, "spoken": False, "phones": []})
        d["result"]["words"].append({"word": "[laughter]", "begin": 4.36, "end": 4.45, "annotation": True,
                                     "phones": []})
        r = olign.Result.from_dict(d)
        self.assertEqual(len(r.words), 9)
        self.assertNotIn("really", r.to_srt())
        self.assertNotIn("laughter", r.to_vtt())
        self.assertNotIn("really", r.to_textgrid())
        self.assertIn("3,really,2.1,2.1,,false", r.to_csv())

    def test_clock_handles_hours(self):
        r = olign.Result(words=[olign.Word("late", 3 * 3600 - 1.5, 3 * 3600 - 0.75)])
        self.assertIn("02:59:58,500 --> 02:59:59,250", r.to_srt())


class Arguments(unittest.TestCase):
    def parse(self, *argv):
        return cli.build_parser().parse_args(list(argv))

    def test_a_bare_flag_names_the_file_after_the_audio(self):
        a = self.parse("align", "talks/talk.mp3", "--textgrid", "--srt", "subs/out.srt")
        self.assertEqual(cli.outputs(a, a.audio.stem),
                         [(pathlib.Path("talk.TextGrid"), "to_textgrid"), (pathlib.Path("subs/out.srt"), "to_srt")])
        self.assertIsNone(a.transcript)

    def test_transcript_and_every_format(self):
        a = self.parse("align", "talk.mp3", "-t", "talk.txt", "--vtt", "--csv", "--json", "r.json", "-q")
        self.assertEqual(a.transcript, pathlib.Path("talk.txt"))
        self.assertEqual([m for _, m in cli.outputs(a, "talk")], ["to_vtt", "to_csv", "to_json"])
        self.assertTrue(a.quiet)

    def test_get_names_files_after_the_job(self):
        a = self.parse("get", "abc123", "--vtt")
        self.assertEqual(cli.outputs(a, a.job_id), [(pathlib.Path("abc123.vtt"), "to_vtt")])

    def test_export_has_no_json_flag(self):
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            self.parse("export", "r.json", "--json")

    def test_version(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit) as e:
            self.parse("--version")
        self.assertEqual(e.exception.code, 0)
        self.assertEqual(out.getvalue().strip(), f"olign {olign.__version__}")

    def test_no_command_prints_help(self):
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            self.assertEqual(cli.main([]), 2)
        self.assertIn("align", err.getvalue())

    def test_export_from_the_sample(self):
        with tempfile.TemporaryDirectory() as tmp:
            out, srt = io.StringIO(), pathlib.Path(tmp) / "s.srt"
            with contextlib.redirect_stdout(out):
                self.assertEqual(cli.main(["export", str(SAMPLE), "--srt", str(srt)]), 0)
            self.assertIn("4.48 s of audio, 7 words aligned to your transcript", out.getvalue())
            self.assertIn("hamburger", srt.read_text())


class FakeAPI(BaseHTTPRequestHandler):
    """POST / takes a job, GET /<id> answers 'running' once, then the sample."""

    key = "test-key"
    polls: dict = {}
    uploads: list = []
    fail_with = None  # (status, body, headers) to answer the POST with
    final = None  # the done (or failed) status

    def log_message(self, *args):
        pass

    def send(self, code, body, headers=None):
        raw = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("X-Olign-Api-Version", "v1.1.0")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def authorized(self):
        if self.headers.get("X-API-Key") != self.key:
            self.send(401, {"detail": "invalid API key"})
            return False
        return True

    def do_POST(self):
        body = self.rfile.read(int(self.headers["Content-Length"]))
        if not self.authorized():
            return
        if FakeAPI.fail_with:
            self.send(*FakeAPI.fail_with)
            return
        FakeAPI.uploads.append({"ctype": self.headers["Content-Type"], "body": body,
                                "agent": self.headers.get("User-Agent")})
        self.send(202, {"job_id": "job1"})

    def do_GET(self):
        if not self.authorized():
            return
        job = self.path.rsplit("/", 1)[-1]
        if job != "job1":
            self.send(404, {"detail": "unknown job id"})
            return
        n = FakeAPI.polls[job] = FakeAPI.polls.get(job, 0) + 1
        if n == 1:
            self.send(200, {"job_id": job, "state": "running", "progress": 0.5})
        else:
            self.send(200, FakeAPI.final)


class RoundTrip(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeAPI)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.url = f"http://127.0.0.1:{cls.server.server_address[1]}/olign/v1"

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeAPI.polls, FakeAPI.uploads, FakeAPI.fail_with = {}, [], None
        FakeAPI.final = trimmed()
        self.client = olign.Client("test-key", base_url=self.url, poll_interval=0)

    def test_align_uploads_polls_and_returns_the_words(self):
        seen = []
        r = self.client.align(AUDIO, transcript=TRANSCRIPT, on_progress=lambda x: seen.append(x.state))
        self.assertEqual(r.text, "what is better a fruit or hamburger")
        self.assertEqual(r.job_id, "6abb52b92239acba")
        self.assertEqual(r.api_version, "v1.1.0")
        self.assertEqual(seen, ["queued", "running", "done"])
        up = FakeAPI.uploads[0]
        self.assertTrue(up["ctype"].startswith("multipart/form-data; boundary="))
        self.assertTrue(up["agent"].startswith("olign-python/"))
        self.assertIn(b'name="audio"; filename="short1.wav"', up["body"])
        self.assertIn(b'name="transcript"', up["body"])
        self.assertIn(TRANSCRIPT.read_bytes(), up["body"])
        self.assertIn(AUDIO.read_bytes()[:4096], up["body"])

    def test_transcript_as_text_and_no_transcript(self):
        self.client.align(AUDIO, transcript="what is better")
        self.assertIn(b"\r\n\r\nwhat is better\r\n", FakeAPI.uploads[0]["body"])
        FakeAPI.polls = {}
        self.client.align(AUDIO)
        self.assertNotIn(b'name="transcript"', FakeAPI.uploads[1]["body"])

    def test_poll_false_returns_the_queued_job(self):
        job = self.client.align(AUDIO, poll=False)
        self.assertEqual((job.job_id, job.state, job.words), ("job1", "queued", []))
        self.assertEqual(len(self.client.wait(job.job_id).words), 7)

    def test_errors_carry_the_api_message(self):
        cases = [
            (401, olign.AuthenticationError, "invalid API key", {}),
            (402, olign.PaymentRequiredError, "the recording is 61 min and your balance covers 12 min", {}),
            (413, olign.AudioTooLargeError, "audio over 100 MB", {}),
            (429, olign.UsageLimitError, "your monthly limit is reached", {"Retry-After": "3600"}),
        ]
        for status, cls, message, headers in cases:
            with self.subTest(status=status):
                FakeAPI.fail_with = (status, {"detail": message}, headers)
                client = self.client if status != 401 else olign.Client("wrong", base_url=self.url)
                with self.assertRaises(cls) as e:
                    client.align(AUDIO)
                self.assertEqual(e.exception.status, status)
                self.assertEqual(e.exception.api_message, message)
                self.assertIn(f"HTTP {status}: {message}", str(e.exception))
                self.assertIsInstance(e.exception, olign.OlignError)
        self.assertEqual(e.exception.retry_after, 3600.0)

    def test_failed_job_raises_with_its_reason(self):
        FakeAPI.final = {"job_id": "job1", "state": "failed", "error": "no speech found in the audio"}
        with self.assertRaises(olign.JobFailedError) as e:
            self.client.align(AUDIO)
        self.assertIn("no speech found in the audio", str(e.exception))

    def test_unknown_job_is_an_api_error(self):
        with self.assertRaises(olign.APIError) as e:
            self.client.get("nope")
        self.assertEqual(e.exception.status, 404)

    def test_unreachable_api(self):
        client = olign.Client("k", base_url="http://127.0.0.1:9/olign/v1")
        with self.assertRaises(olign.ConnectionFailedError):
            client.get("job1")

    def test_missing_key(self):
        with mock.patch.dict(os.environ, {}, clear=True), self.assertRaises(olign.OlignError) as e:
            olign.Client()
        self.assertIn("OLIGN_KEY", str(e.exception))

    def test_key_and_url_from_the_environment(self):
        with mock.patch.dict(os.environ, {"OLIGN_KEY": "test-key", "OLIGN_API_URL": self.url}):
            r = olign.Client(poll_interval=0).align(AUDIO)
        self.assertEqual(len(r.words), 7)

    def test_cli_align_writes_the_files_and_a_summary(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"OLIGN_KEY": "test-key", "OLIGN_API_URL": self.url}):
            out, err = io.StringIO(), io.StringIO()
            tg, js = pathlib.Path(tmp) / "a.TextGrid", pathlib.Path(tmp) / "a.json"
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
                code = cli.main(["align", str(AUDIO), "--transcript", str(TRANSCRIPT),
                                 "--textgrid", str(tg), "--json", str(js), "--every", "0"])
            self.assertEqual(code, 0, err.getvalue())
            self.assertEqual(out.getvalue(), "short1.wav: 4.48 s of audio, 7 words aligned to your transcript\n"
                                             f"wrote {tg}\nwrote {js}\n")
            self.assertIn("olign: job job1 queued", err.getvalue())
            self.assertIn("olign: running 50%", err.getvalue())
            self.assertEqual(textgrid_tiers(tg.read_text())["words"][1][2], "what")
            self.assertEqual(len(olign.Result.load(js).words), 7)

    def test_cli_get_saves_a_job_submitted_earlier(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.dict(os.environ, {"OLIGN_KEY": "test-key", "OLIGN_API_URL": self.url}):
            out, srt = io.StringIO(), pathlib.Path(tmp) / "late.srt"
            with contextlib.redirect_stdout(out), contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(cli.main(["get", "job1", "--srt", str(srt), "--every", "0"]), 0)
            self.assertIn("job1: 4.48 s of audio, 7 words", out.getvalue())
            self.assertIn("hamburger", srt.read_text())

    def test_cli_reports_api_errors_on_stderr(self):
        FakeAPI.fail_with = (402, {"detail": "out of minutes"}, {})
        with mock.patch.dict(os.environ, {"OLIGN_KEY": "test-key", "OLIGN_API_URL": self.url}):
            err = io.StringIO()
            with contextlib.redirect_stderr(err), contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(cli.main(["align", str(AUDIO), "-q"]), 1)
        self.assertIn("olign: error: HTTP 402: out of minutes", err.getvalue())


if __name__ == "__main__":
    unittest.main()
