"""Reply walk shared by the live client and the JSONL archive."""

from __future__ import annotations

from typing import Protocol

from threadedtweets.model import Tweet

MAX_DEPTH = 25


class ReplySearch(Protocol):
    """One search for posts directed at ``screen_name`` and newer than ``since_id``."""

    def search(self, screen_name: str, since_id: int) -> list[Tweet]:
        """Return candidate posts. The caller decides which are real replies."""


def collect_replies(
    root: Tweet,
    client: ReplySearch,
    *,
    max_depth: int = MAX_DEPTH,
) -> list[Tweet]:
    """Return replies to ``root``, including replies to those replies.

    A candidate is kept only when ``in_reply_to_status_id`` is the parent
    being walked. Search hits that merely mention the author are dropped.
    ``seen`` cuts cycles; it does not drop a tweet that showed up early in
    an ancestor's page but is a direct reply to a later parent.
    """
    if max_depth < 1:
        return []
    seen = {root.id}
    found: list[Tweet] = []

    def walk(parent: Tweet, depth: int) -> None:
        if depth > max_depth:
            return
        children: list[Tweet] = []
        for candidate in client.search(parent.screen_name, since_id=parent.id):
            if candidate.id in seen:
                continue
            if candidate.in_reply_to_status_id != parent.id:
                continue
            seen.add(candidate.id)
            children.append(candidate)
        for child in children:
            found.append(child)
            walk(child, depth + 1)

    walk(root, 1)
    return found
