"""The olign API v1 client: submit a recording, poll the job, get a Result.

Standard library only, so ``pip install olign`` pulls in nothing else.
"""

from __future__ import annotations

import json
import os
import pathlib
import time
import urllib.error
import urllib.request
import uuid
from typing import Callable, List, Optional, Tuple, Union

from . import __version__
from .errors import BY_STATUS, APIError, ConnectionFailedError, JobFailedError, OlignError, UsageLimitError
from .result import PathLike, Result

API = "https://api.olewave.com/olign/v1"
# Cloudflare fronts the API and turns away some library defaults (HTTP 403,
# "error code: 1010" for Python-urllib), so the client names itself.
USER_AGENT = f"olign-python/{__version__}"

Transcript = Union[str, bytes, "os.PathLike[str]", None]
Progress = Callable[[Result], None]


class Client:
    """A client for the olign API v1.

    ``api_key`` defaults to the ``OLIGN_KEY`` environment variable and
    ``base_url`` to ``OLIGN_API_URL``, then to the public API.
    """

    def __init__(self, api_key: Optional[str] = None, *, base_url: Optional[str] = None,
                 poll_interval: float = 5.0, timeout: float = 300.0):
        key = api_key or os.environ.get("OLIGN_KEY")
        if not key:
            raise OlignError("no API key: set OLIGN_KEY, or pass Client(api_key=...). "
                             "Create one under Profile > API keys on https://tycho.olewave.com")
        self.api_key = key
        self.base_url = (base_url or os.environ.get("OLIGN_API_URL") or API).rstrip("/")
        self.poll_interval = poll_interval
        self.timeout = timeout

    def __repr__(self) -> str:
        return f"Client(base_url={self.base_url!r})"

    # -- the three calls -----------------------------------------------------

    def align(self, audio_path: PathLike, transcript: Transcript = None, poll: bool = True,
              on_progress: Optional[Progress] = None, *, word_edges: Optional[str] = None,
              align_untranscribed: bool = False) -> Result:
        """Align a recording and return its words.

        ``transcript`` is optional. Pass the text as a ``str``, or a
        ``pathlib.Path`` to a UTF-8 text file. Without it, olign transcribes
        the audio first, then aligns. With ``poll=False`` the call returns as
        soon as the job is accepted, and :meth:`wait` finishes it.

        ``word_edges`` is ``"phonetic"`` (the API's default) or ``"audible"``:
        words then start and end where a listener hears them, as dubbing and
        subtitles need (the silence before a p, t, k, b, d or g stays outside
        its word; for clean recordings). ``align_untranscribed=True`` also
        aligns the speech your transcript leaves out; those words come back
        with ``untranscribed`` set.
        """
        job = self.submit(audio_path, transcript, word_edges=word_edges,
                          align_untranscribed=align_untranscribed)
        if on_progress:
            on_progress(job)
        return self.wait(job.job_id, on_progress=on_progress) if poll else job

    def submit(self, audio_path: PathLike, transcript: Transcript = None, *,
               word_edges: Optional[str] = None, align_untranscribed: bool = False) -> Result:
        """Upload the audio and return the accepted job, still queued.
        Takes the options of :meth:`align`."""
        if word_edges not in (None, "phonetic", "audible"):
            raise ValueError(f"word_edges must be 'phonetic' or 'audible', not {word_edges!r}")
        audio = pathlib.Path(audio_path)
        fields: List[Tuple[str, Optional[str], bytes]] = [("audio", audio.name, audio.read_bytes())]
        if transcript is not None:
            fields.append(("transcript", "transcript.txt", _transcript_bytes(transcript)))
        if word_edges:
            fields.append(("word_edges", None, word_edges.encode()))
        if align_untranscribed:
            fields.append(("align_untranscribed", None, b"1"))
        body, ctype = _multipart(fields)
        d, headers = self._call("POST", self.base_url, body, ctype)
        if not d.get("job_id"):
            raise APIError(f"the API accepted the upload but sent no job_id: {str(d)[:200]}")
        d.setdefault("state", "queued")
        return Result.from_dict(d, headers)

    def get(self, job_id: str) -> Result:
        """One look at a job: queued, running, done or failed."""
        d, headers = self._call("GET", f"{self.base_url}/{job_id}")
        d.setdefault("job_id", job_id)
        return Result.from_dict(d, headers)

    def wait(self, job_id: str, on_progress: Optional[Progress] = None) -> Result:
        """Poll a job until it is done. Raises :class:`JobFailedError` if it fails."""
        misses = 0
        while True:
            try:
                r = self.get(job_id)
                misses = 0
            except (ConnectionFailedError, APIError) as e:
                # A long job outlives a brief network or gateway hiccup.
                transient = isinstance(e, ConnectionFailedError) or (e.status or 0) >= 500
                misses += 1
                if not transient or misses > 3:
                    raise
                time.sleep(self.poll_interval * misses)
                continue
            if on_progress:
                on_progress(r)
            if r.state == "done":
                return r
            if r.state == "failed":
                raise JobFailedError(job_id, r.error)
            time.sleep(self.poll_interval)

    # -- HTTP ----------------------------------------------------------------

    def _call(self, method: str, url: str, body: Optional[bytes] = None,
              ctype: Optional[str] = None) -> Tuple[dict, dict]:
        headers = {"X-API-Key": self.api_key, "User-Agent": USER_AGENT, "Accept": "application/json"}
        if ctype:
            headers["Content-Type"] = ctype
        req = urllib.request.Request(url, data=body, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as r:
                return _json(r.read()), dict(r.headers.items())
        except urllib.error.HTTPError as e:
            raise _http_error(e) from None
        except (urllib.error.URLError, OSError) as e:
            reason = getattr(e, "reason", e)
            raise ConnectionFailedError(f"could not reach {url}: {reason}") from None


def _http_error(e: urllib.error.HTTPError) -> OlignError:
    raw = e.read()
    body = _json(raw, strict=False)
    message = _message(body) or raw.decode("utf-8", "replace").strip()[:300] or (e.reason or "")
    cls = BY_STATUS.get(e.code, APIError)
    if cls is UsageLimitError:
        retry = e.headers.get("Retry-After") if e.headers else None
        try:
            retry_after = float(retry) if retry else None
        except ValueError:
            retry_after = None
        return UsageLimitError(message, e.code, body, retry_after=retry_after)
    return cls(message, e.code, body)


def _message(body: dict) -> str:
    """The API's own words: FastAPI puts them in ``detail``, other layers in
    ``error`` or ``message``."""
    for key in ("detail", "error", "message"):
        v = body.get(key)
        if isinstance(v, str) and v:
            return v
        if isinstance(v, list) and v:  # validation errors: a list of {"msg": ...}
            return "; ".join(str(x.get("msg", x)) if isinstance(x, dict) else str(x) for x in v)
    return ""


def _json(raw: bytes, strict: bool = True) -> dict:
    try:
        d = json.loads(raw or b"{}")
    except ValueError:
        if strict:
            raise APIError(f"the API sent something that is not JSON: {raw[:200]!r}") from None
        return {}
    return d if isinstance(d, dict) else {}


def _transcript_bytes(t: Transcript) -> bytes:
    if isinstance(t, bytes):
        return t
    if isinstance(t, str):
        return t.encode("utf-8")
    return pathlib.Path(t).read_bytes()


def _multipart(fields: List[Tuple[str, Optional[str], bytes]]) -> Tuple[bytes, str]:
    """A multipart/form-data body with a known length: the API refuses chunked
    uploads. A field without a filename is a plain form value."""
    boundary = uuid.uuid4().hex
    body = bytearray()
    for name, filename, data in fields:
        if filename is None:
            body += f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'.encode()
            body += data + b"\r\n"
            continue
        filename = filename.replace('"', "_").replace("\r", "_").replace("\n", "_")
        body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                 f'filename="{filename}"\r\nContent-Type: application/octet-stream\r\n\r\n').encode()
        body += data + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return bytes(body), f"multipart/form-data; boundary={boundary}"
