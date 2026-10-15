"""Shared argument parsing for the text view and the JSONL view."""

from __future__ import annotations

import argparse
from pathlib import Path

from threadedtweets.archive import FileSearchClient, infer_root, load_jsonl
from threadedtweets.model import Tweet, parse_id
from threadedtweets.x_client import client_from_env
from tweet_processor import TweetProcessor
from twitter_handler import TwitterHandler


def parse_args(argv: list[str] | None = None, *, prog: str) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog=prog,
        description=(
            "Build a threaded view of replies to one tweet. "
            "Pass --file to stay offline, or a tweet id to query X recent search."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "examples:\n"
            "  python3 main.py --file examples/thread.jsonl\n"
            "  python3 replies.py --file examples/thread.jsonl > replies.jsonl\n"
            "  python3 main.py TWEET_ID\n"
        ),
    )
    parser.add_argument(
        "tweet_id",
        nargs="?",
        type=_positive_id,
        help="Id of the root tweet to look up with the X API",
    )
    parser.add_argument(
        "--file",
        type=Path,
        help="JSONL archive of tweets. Uses no network",
    )
    parser.add_argument(
        "--root",
        type=_positive_id,
        help="Root tweet id inside --file. Inferred when the archive has one root",
    )
    args = parser.parse_args(argv)
    if args.tweet_id is not None and args.file is not None:
        parser.error("Pass a tweet id or --file, not both.")
    if args.tweet_id is None and args.file is None:
        parser.error("Pass a tweet id, or --file with a JSONL archive of tweets.")
    if args.root is not None and args.file is None:
        parser.error("--root applies to --file archives.")
    return args


def load_conversation(
    args: argparse.Namespace,
    env: dict[str, str] | None = None,
) -> tuple[Tweet, list[Tweet]]:
    """Return the root tweet and the replies under it, depth-first."""
    if args.file is not None:
        tweets = load_jsonl(args.file)
        root = infer_root(tweets, args.root)
        handler = TwitterHandler(client=FileSearchClient(tweets))
        return root, TweetProcessor(handler).get_required_tweets(root)
    client = client_from_env(env)
    root = client.get_tweet(args.tweet_id)
    handler = TwitterHandler(client=client)
    return root, TweetProcessor(handler).get_required_tweets(root)


def _positive_id(value: str) -> int:
    try:
        return parse_id(value, "tweet id")
    except ValueError as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None
