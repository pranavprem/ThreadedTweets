#!/usr/bin/env python3
"""Print replies to one tweet as line-oriented JSON.

This is the archive interface the 2017 script's docstring described
(``replies.py tweets.json > replies.json``). The root tweet is not
printed. Each reply is one JSON object.

    python3 replies.py --file examples/thread.jsonl > replies.jsonl
    python3 replies.py TWEET_ID > replies.jsonl
"""

from __future__ import annotations

import sys

from threadedtweets.cli import load_conversation, parse_args
from threadedtweets.model import dump_tweet
from threadedtweets.x_client import XApiError


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv, prog="replies.py")
    try:
        _root, replies = load_conversation(args)
    except (XApiError, ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 2
    for reply in replies:
        print(dump_tweet(reply))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
