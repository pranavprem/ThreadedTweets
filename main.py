#!/usr/bin/env python3
"""Print replies to one tweet as an indented thread.

Offline, from an archive:

    python main.py --file examples/thread.jsonl

Live, when X_BEARER_TOKEN can call recent search:

    python main.py TWEET_ID
"""

from __future__ import annotations

import sys

from threadedtweets.cli import load_conversation, parse_args
from threadedtweets.model import build_thread, render_thread
from threadedtweets.x_client import XApiError


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv, prog="main.py")
    try:
        root, replies = load_conversation(args)
    except (XApiError, ValueError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 2
    print(render_thread(build_thread(root, replies)), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
