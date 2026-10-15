"""Recursive reply collector started in the last 2017 commit.

The original class extended the list it was iterating and treated every
search hit as a reply, so nested replies were duplicated and mentions
were walked as if they were replies. Collection now goes through
``collect_replies``, which keeps a tweet only when it replies to the
parent and records each id once.
"""

from __future__ import annotations

from threadedtweets.collect import MAX_DEPTH, ReplySearch, collect_replies
from threadedtweets.model import Tweet, coerce_tweet
from twitter_handler import TwitterHandler


class TweetProcessor:
    def __init__(self, handler: ReplySearch | None = None):
        self.handler = handler if handler is not None else TwitterHandler()

    def get_required_tweets(
        self,
        tweet: object,
        max_depth: int = MAX_DEPTH,
    ) -> list[Tweet]:
        root = coerce_tweet(tweet)
        return collect_replies(root, self.handler, max_depth=max_depth)


tweet_processor = TweetProcessor
