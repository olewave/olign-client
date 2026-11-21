"""Exceptions raised by the olign client.

Every error the API returns becomes an :class:`OlignError` subclass whose
message starts with the HTTP status and the API's own words, then says what
you can do about it.
"""

from __future__ import annotations

from typing import Optional

DASHBOARD = "https://dashboard.olewave.com"


class OlignError(Exception):
    """Base class. ``status`` is the HTTP status, or None for errors that are
    not HTTP answers (a failed job, an unreachable server)."""

    hint = ""

    def __init__(self, message: str, status: Optional[int] = None, body: Optional[dict] = None):
        self.status = status
        self.api_message = message
        self.body = body or {}
        text = f"HTTP {status}: {message}" if status else message
        if self.hint:
            text += f" ({self.hint})"
        super().__init__(text)


class APIError(OlignError):
    """Any HTTP error without a more specific class below."""


class AuthenticationError(OlignError):
    """401. The API key is missing, wrong or revoked."""

    hint = f"check OLIGN_KEY, or create a key under Profile > API keys on {DASHBOARD}"


class PaymentRequiredError(OlignError):
    """402. Your balance does not cover this recording."""

    hint = f"add a card or buy more minutes under Billing on {DASHBOARD}"


class AudioTooLargeError(OlignError):
    """413. The upload is over the size limit, or the audio is over 3 hours."""

    hint = "split the recording, or compress it with ffmpeg -i in.wav -ac 1 -c:a libopus -b:a 32k out.ogg"


class UsageLimitError(OlignError):
    """429. Your own monthly limit is reached. ``retry_after`` is the number of
    seconds until it resets, when the API says."""

    hint = f"raise or remove the limit under Settings on {DASHBOARD}"

    def __init__(self, message: str, status: Optional[int] = None, body: Optional[dict] = None,
                 retry_after: Optional[float] = None):
        self.retry_after = retry_after
        super().__init__(message, status, body)


class JobFailedError(OlignError):
    """The job was accepted but ended in the ``failed`` state."""

    def __init__(self, job_id: str, reason: Optional[str] = None):
        self.job_id = job_id
        super().__init__(f"job {job_id} failed: {reason or 'the API gave no reason'}")


class ConnectionFailedError(OlignError):
    """The API could not be reached."""


BY_STATUS = {
    401: AuthenticationError,
    402: PaymentRequiredError,
    413: AudioTooLargeError,
    429: UsageLimitError,
}
