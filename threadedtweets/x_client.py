"""X API v2 recent search, with failures explained at the door.

The 2017 code called Twitter API v1.1 ``GET search/tweets``. That endpoint
was retired on 20 September 2023. The same ``to:username`` query now goes
to ``GET /2/tweets/search/recent``. Recent search is a paid read and covers
about seven days. This module does not scrape X and does not call any
unofficial host.
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from typing import Any

from threadedtweets.model import Tweet, tweets_from_payload

API_ROOT = "https://api.x.com/2"
USER_AGENT = "ThreadedTweets"
MAX_RESULTS = 100
MAX_PAGES = 10
TWEET_FIELDS = "author_id,created_at,referenced_tweets"
USERNAME = re.compile(r"^[A-Za-z0-9_]{1,15}$")
LEGACY_ENV_VARS = (
    "CONSUMER_KEY",
    "CONSUMER_SECRET",
    "ACCESS_TOKEN",
    "ACCESS_TOKEN_SECRET",
)

MISSING_TOKEN = (
    "X_BEARER_TOKEN is not set. Live reply lookup calls X API v2 recent "
    "search (GET /2/tweets/search/recent) and needs a bearer token with "
    "credit-metered read access. Twitter API v1.1 standard search, which "
    "this project called in 2017, was retired in September 2023. Offline "
    "mode needs no token: python3 main.py --file examples/thread.jsonl"
)
LEGACY_NOTE = (
    " CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, and ACCESS_TOKEN_SECRET "
    "are the 2017 v1.1 credentials and are not read."
)

Opener = Callable[..., Any]
Sleeper = Callable[[float], None]


class XApiError(RuntimeError):
    """A live lookup that did not return tweets, with a reason attached."""

    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


class XClient:
    """App-only client for one tweet lookup and recent ``to:username`` search."""

    def __init__(
        self,
        bearer_token: str,
        *,
        opener: Opener | None = None,
        sleep: Sleeper = time.sleep,
        timeout: float = 30,
        max_retries: int = 2,
        max_pages: int = MAX_PAGES,
    ):
        self.bearer_token = bearer_token
        self._opener = opener or urllib.request.urlopen
        self._sleep = sleep
        self.timeout = timeout
        self.max_retries = max_retries
        self.max_pages = max_pages

    def get_tweet(self, tweet_id: int) -> Tweet:
        payload = self._get(
            f"/tweets/{int(tweet_id)}",
            {
                "tweet.fields": TWEET_FIELDS,
                "expansions": "author_id",
                "user.fields": "username",
            },
        )
        tweets = tweets_from_payload(payload)
        if not tweets:
            raise XApiError(f"Tweet {tweet_id} was not found.", status=404)
        return tweets[0]

    def search(self, screen_name: str, since_id: int) -> list[Tweet]:
        if not USERNAME.fullmatch(screen_name):
            raise XApiError(
                "Recent search needs a username of 1-15 letters, digits, or "
                f"underscores. Cannot query replies for {screen_name!r}."
            )
        found: list[Tweet] = []
        next_token: str | None = None
        for _ in range(self.max_pages):
            params = {
                "query": f"to:{screen_name}",
                "since_id": str(since_id),
                "max_results": str(MAX_RESULTS),
                "tweet.fields": TWEET_FIELDS,
                "expansions": "author_id",
                "user.fields": "username",
            }
            if next_token:
                params["next_token"] = next_token
            payload = self._get("/tweets/search/recent", params)
            found.extend(tweets_from_payload(payload))
            meta = payload.get("meta") if isinstance(payload.get("meta"), dict) else {}
            token = meta.get("next_token")
            next_token = token if isinstance(token, str) and token else None
            if not next_token:
                break
        return found

    def _get(self, path: str, params: dict[str, str]) -> dict[str, Any]:
        url = f"{API_ROOT}{path}?{urllib.parse.urlencode(params)}"
        request = urllib.request.Request(
            url,
            headers={
                "Authorization": f"Bearer {self.bearer_token}",
                "User-Agent": USER_AGENT,
            },
            method="GET",
        )
        for attempt in range(self.max_retries + 1):
            try:
                with self._opener(request, timeout=self.timeout) as response:
                    raw = response.read()
            except urllib.error.HTTPError as exc:
                body = _read_error_body(exc)
                message = self._safe(explain_status(exc.code, body))
                if exc.code == 429 and attempt < self.max_retries:
                    self._sleep(_retry_delay(exc))
                    continue
                raise XApiError(message, status=exc.code) from exc
            except urllib.error.URLError as exc:
                reason = getattr(exc, "reason", exc)
                raise XApiError(
                    self._safe(f"Could not reach the X API ({reason}).")
                ) from exc
            except TimeoutError as exc:
                raise XApiError("The X API request timed out.") from exc
            except OSError as exc:
                raise XApiError(
                    self._safe(f"Could not reach the X API ({exc}).")
                ) from exc
            return self._decode(raw)
        raise XApiError(
            "X rate-limited the request (HTTP 429) and retries were exhausted.",
            status=429,
        )

    def _decode(self, raw: bytes) -> dict[str, Any]:
        try:
            payload = json.loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise XApiError("X API returned a response that was not JSON.") from exc
        if not isinstance(payload, dict):
            raise XApiError("X API returned a response that was not a JSON object.")
        if payload.get("errors") and not payload.get("data"):
            detail = _error_detail(json.dumps(payload))
            message = f"X API error: {detail}" if detail else "X API error."
            raise XApiError(self._safe(message))
        return payload

    def _safe(self, text: str) -> str:
        if self.bearer_token and self.bearer_token in text:
            return text.replace(self.bearer_token, "[redacted]")
        return text


def client_from_env(env: Mapping[str, str] | None = None) -> XClient:
    source: Mapping[str, str] = os.environ if env is None else env
    token = str(source.get("X_BEARER_TOKEN", "")).strip()
    if token:
        return XClient(token)
    message = MISSING_TOKEN
    if any(str(source.get(name, "")).strip() for name in LEGACY_ENV_VARS):
        message += LEGACY_NOTE
    raise XApiError(message)


def explain_status(status: int, body: str) -> str:
    detail = _error_detail(body)
    suffix = f" {detail}" if detail else ""
    if status == 401:
        return "X rejected the bearer token (HTTP 401). Check X_BEARER_TOKEN." + suffix
    if status == 402:
        return (
            "X returned HTTP 402. This token has no API credits left for the read."
            + suffix
        )
    if status == 403:
        return (
            "X refused the read (HTTP 403). Recent search is a paid, "
            "credit-metered endpoint, and this token cannot call it. "
            "The thread was not fetched." + suffix
        )
    if status == 404:
        return (
            "X returned HTTP 404. The tweet may be missing, or this "
            "endpoint is not available to the token." + suffix
        )
    if status == 429:
        return (
            "X rate-limited the request (HTTP 429) and retries were exhausted." + suffix
        )
    return f"X API request failed (HTTP {status})." + suffix


def _error_detail(body: str) -> str:
    text = body.strip()
    if not text:
        return ""
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        return " ".join(text.split())[:300]
    if isinstance(parsed, dict):
        for key in ("detail", "message", "title"):
            value = parsed.get(key)
            if isinstance(value, str) and value.strip():
                return " ".join(value.split())[:300]
        errors = parsed.get("errors")
        if isinstance(errors, list):
            for item in errors:
                if not isinstance(item, dict):
                    continue
                for key in ("message", "detail", "title"):
                    value = item.get(key)
                    if isinstance(value, str) and value.strip():
                        return " ".join(value.split())[:300]
    return " ".join(text.split())[:300]


def _read_error_body(exc: urllib.error.HTTPError) -> str:
    try:
        raw = exc.read()
    except Exception:
        return ""
    if isinstance(raw, str):
        return raw
    return raw.decode("utf-8", errors="replace")


def _retry_delay(exc: urllib.error.HTTPError) -> float:
    headers = getattr(exc, "headers", None)
    raw = None
    if headers is not None and hasattr(headers, "get"):
        raw = headers.get("Retry-After")
    try:
        delay = float(raw)
    except (TypeError, ValueError):
        return 2.0
    if delay < 0:
        return 0.0
    return min(delay, 30.0)
