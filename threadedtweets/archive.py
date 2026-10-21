"""JSONL archives, the offline stand-in for a search call."""

from __future__ import annotations

import json
from pathlib import Path

from threadedtweets.model import Tweet, tweet_from_obj


class FileSearchClient:
    """Search an in-memory archive the way v1.1 ``since_id`` did.

    Archived lines have no record of the ``to:username`` query, so this
    returns every stored tweet with a greater id. ``collect_replies``
    still keeps only real replies. A reply whose id is lower than its
    parent's is outside that window, same as the 2017 script.
    """

    def __init__(self, tweets: list[Tweet]):
        self.tweets = list(tweets)

    def search(self, screen_name: str, since_id: int) -> list[Tweet]:
        # ``screen_name`` is part of the live-search signature. Archive lines
        # do not record who a post was addressed to, so the id window is the filter.
        return [tweet for tweet in self.tweets if tweet.id > since_id]


def load_jsonl(path: Path) -> list[Tweet]:
    """Load tweets. Blank lines and ``#`` comments are skipped.

    The first line wins when an id is repeated.
    """
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        raise ValueError(f"Tweet file not found: {path}") from None
    tweets: list[Tweet] = []
    seen: set[int] = set()
    for lineno, line in enumerate(raw.splitlines(), start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        try:
            payload = json.loads(stripped)
            tweet = tweet_from_obj(payload)
        except (json.JSONDecodeError, ValueError) as exc:
            raise ValueError(f"{path}:{lineno}: {exc}") from None
        if tweet.id in seen:
            continue
        seen.add(tweet.id)
        tweets.append(tweet)
    if not tweets:
        raise ValueError(f"{path} has no tweets.")
    return tweets


def infer_root(tweets: list[Tweet], root_id: int | None) -> Tweet:
    """Pick the conversation root, or use ``root_id`` when it is present."""
    by_id = {tweet.id: tweet for tweet in tweets}
    if root_id is not None:
        try:
            return by_id[root_id]
        except KeyError:
            raise ValueError(
                f"Root tweet {root_id} is not in the file. "
                "Add that status to the JSONL."
            ) from None
    ids = set(by_id)
    roots = [tweet for tweet in tweets if tweet.in_reply_to_status_id not in ids]
    if len(roots) == 1:
        return roots[0]
    if not roots:
        raise ValueError("Could not infer a root tweet from the file. Pass --root.")
    listed = ", ".join(str(tweet.id) for tweet in roots)
    raise ValueError(f"The file has several possible roots ({listed}). Pass --root.")
