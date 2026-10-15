"""Search seam that ``tweet_processor`` imported and the 2017 tree never had.

The class looks up replies for one author. Pagination stays inside the
client: v2 recent search follows ``next_token``, and the archive client
filters on id. The old ``max_id`` argument is accepted so the original
call shape still runs; v1.1 page cursors are not sent anywhere.
"""

from __future__ import annotations

from collections.abc import Mapping

from threadedtweets.collect import ReplySearch
from threadedtweets.model import Tweet
from threadedtweets.x_client import client_from_env


class TwitterHandler:
    def __init__(
        self,
        client: ReplySearch | None = None,
        env: Mapping[str, str] | None = None,
    ):
        self._client = client
        self._env = env

    def search(self, screen_name: str, since_id: int) -> list[Tweet]:
        return self._resolve().search(screen_name, since_id)

    def get_tweets(
        self,
        user: str,
        tweet_id: int,
        max_id: int | None = None,
    ) -> list[Tweet]:
        """Return candidates directed at ``user`` and newer than ``tweet_id``.

        ``max_id`` keeps the 2017 call ``get_tweets(user, tweet_id, max_id)``.
        v2 pages with ``next_token`` inside the client, so that cursor is not
        forwarded.
        """
        return self.search(str(user), since_id=int(tweet_id))

    def _resolve(self) -> ReplySearch:
        if self._client is None:
            self._client = client_from_env(self._env)
        return self._client


twitter_handler = TwitterHandler
