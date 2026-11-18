"""Olign, the forced alignment API from Olewave, in Python.

    import olign

    client = olign.Client()                     # reads OLIGN_KEY
    result = client.align("talk.mp3", transcript="what is better a fruit or hamburger")
    for w in result.words:
        print(w.word, w.begin, w.end)
    result.to_textgrid("talk.TextGrid")
"""

__version__ = "1.2.0"

from .client import Client  # noqa: E402
from .errors import (  # noqa: E402
    APIError,
    AudioTooLargeError,
    AuthenticationError,
    ConnectionFailedError,
    JobFailedError,
    OlignError,
    PaymentRequiredError,
    UsageLimitError,
)
from .result import Pause, Phone, Phrase, Result, Word  # noqa: E402

__all__ = [
    "Client", "Result", "Word", "Phone", "Pause", "Phrase",
    "OlignError", "APIError", "AuthenticationError", "PaymentRequiredError", "AudioTooLargeError",
    "UsageLimitError", "JobFailedError", "ConnectionFailedError",
    "__version__",
]
