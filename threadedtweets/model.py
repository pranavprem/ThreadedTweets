"""Tweet records and the indented thread built from them."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True, slots=True)
class Tweet:
    """One status, reduced to the fields the thread walk uses.

    Ids stay Python ints. They are wider than JavaScript's safe integer
    range; ``json.dumps`` still writes them as exact digits.
    """

    id: int
    screen_name: str
    text: str
    in_reply_to_status_id: int | None = None
    created_at: str | None = None

    @property
    def url(self) -> str:
        if self.screen_name:
            return f"https://twitter.com/{self.screen_name}/status/{self.id}"
        return f"https://twitter.com/i/web/status/{self.id}"


@dataclass
class ThreadNode:
    tweet: Tweet
    children: list[ThreadNode] = field(default_factory=list)


def parse_id(value: object, field_name: str = "id") -> int:
    """Parse a tweet id from an int or a digit string."""
    if isinstance(value, str):
        value = value.strip()
        if not value.isdigit():
            raise ValueError(f"{field_name} must be a positive integer")
        number = int(value)
    elif isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{field_name} must be a positive integer")
    else:
        number = value
    if number <= 0:
        raise ValueError(f"{field_name} must be a positive integer")
    return number


def parse_optional_id(value: object, field_name: str) -> int | None:
    if value is None:
        return None
    if isinstance(value, str) and not value.strip():
        return None
    return parse_id(value, field_name)


def tweet_from_obj(obj: object) -> Tweet:
    """Accept v1.1 status JSON, a flat object, or one v2 tweet object."""
    if not isinstance(obj, dict):
        raise ValueError("each tweet must be a JSON object")
    user = obj.get("user") if isinstance(obj.get("user"), dict) else {}
    parent = _first(obj, "in_reply_to_status_id_str", "in_reply_to_status_id")
    if parent is None:
        parent = _replied_to_id(obj.get("referenced_tweets"))
    created = obj.get("created_at")
    if created is not None and not isinstance(created, str):
        created = str(created)
    return Tweet(
        id=parse_id(_first(obj, "id_str", "id"), "id"),
        screen_name=_screen_name(
            obj.get("screen_name"),
            obj.get("username"),
            user.get("screen_name"),
            user.get("username"),
        ),
        text=_text(obj.get("full_text"), obj.get("text")),
        in_reply_to_status_id=parse_optional_id(parent, "in_reply_to_status_id"),
        created_at=created,
    )


def tweets_from_payload(payload: dict[str, Any]) -> list[Tweet]:
    """Read a v2 response, joining ``includes.users`` onto each tweet."""
    includes = (
        payload.get("includes") if isinstance(payload.get("includes"), dict) else {}
    )
    usernames: dict[str, str] = {}
    for user in includes.get("users") or []:
        if isinstance(user, dict) and user.get("id") is not None:
            usernames[str(user["id"])] = _screen_name(
                user.get("username"), user.get("screen_name")
            )
    data = payload.get("data") or []
    if isinstance(data, dict):
        data = [data]
    if not isinstance(data, list):
        return []
    tweets: list[Tweet] = []
    for item in data:
        if not isinstance(item, dict) or item.get("id") is None:
            continue
        merged = dict(item)
        author_id = item.get("author_id")
        if author_id is not None and str(author_id) in usernames:
            merged["username"] = usernames[str(author_id)]
        tweets.append(tweet_from_obj(merged))
    return tweets


def coerce_tweet(obj: object) -> Tweet:
    """Build a Tweet from a Tweet, a dict, or a status-like object."""
    if isinstance(obj, Tweet):
        return obj
    if isinstance(obj, dict):
        return tweet_from_obj(obj)
    user = getattr(obj, "user", None)
    parent = getattr(obj, "in_reply_to_status_id_str", None)
    if parent is None:
        parent = getattr(obj, "in_reply_to_status_id", None)
    created = getattr(obj, "created_at", None)
    if created is not None and not isinstance(created, str):
        created = str(created)
    return Tweet(
        id=parse_id(getattr(obj, "id_str", None) or getattr(obj, "id", None), "id"),
        screen_name=_screen_name(
            getattr(obj, "screen_name", None),
            getattr(obj, "username", None),
            getattr(user, "screen_name", None) if user is not None else None,
            getattr(user, "username", None) if user is not None else None,
        ),
        text=_text(getattr(obj, "full_text", None), getattr(obj, "text", None)),
        in_reply_to_status_id=parse_optional_id(parent, "in_reply_to_status_id"),
        created_at=created,
    )


def tweet_to_json(tweet: Tweet) -> dict[str, Any]:
    """Line format ``replies.py`` writes and ``--file`` reads back."""
    payload: dict[str, Any] = {
        "id": tweet.id,
        "text": tweet.text,
        "in_reply_to_status_id": tweet.in_reply_to_status_id,
        "user": {"screen_name": tweet.screen_name},
    }
    if tweet.created_at:
        payload["created_at"] = tweet.created_at
    return payload


def dump_tweet(tweet: Tweet) -> str:
    return json.dumps(tweet_to_json(tweet), ensure_ascii=False)


def build_thread(root: Tweet, replies: list[Tweet]) -> ThreadNode:
    """Hang each reply off its parent. Duplicate ids attach once."""
    nodes = {root.id: ThreadNode(tweet=root)}
    ordered: list[Tweet] = []
    seen: set[int] = set()
    for reply in replies:
        if reply.id == root.id or reply.id in seen:
            continue
        seen.add(reply.id)
        ordered.append(reply)
        nodes[reply.id] = ThreadNode(tweet=reply)
    for reply in ordered:
        parent_id = reply.in_reply_to_status_id
        parent = nodes.get(parent_id) if parent_id is not None else None
        if parent is None or parent.tweet.id == reply.id:
            continue
        parent.children.append(nodes[reply.id])
    return nodes[root.id]


def render_thread(node: ThreadNode) -> str:
    """Indented transcript. Two spaces per reply level."""
    lines: list[str] = []

    def walk(current: ThreadNode, depth: int) -> None:
        pad = "  " * depth
        tweet = current.tweet
        name = tweet.screen_name or "unknown"
        lines.append(f"{pad}{name} ({tweet.id})")
        for line in tweet.text.splitlines() or [""]:
            lines.append(f"{pad}{line}")
        lines.append(f"{pad}{tweet.url}")
        lines.append("")
        for child in current.children:
            walk(child, depth + 1)

    walk(node, 0)
    rendered = "\n".join(lines).rstrip() + "\n"
    if not node.children:
        rendered += "\n(no replies in the search results)\n"
    return rendered


def _first(obj: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in obj and obj[key] is not None:
            return obj[key]
    return None


def _screen_name(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def _text(*values: object) -> str:
    for value in values:
        if isinstance(value, str) and value.strip():
            return value
    return ""


def _replied_to_id(refs: object) -> object:
    if not isinstance(refs, list):
        return None
    for ref in refs:
        if isinstance(ref, dict) and ref.get("type") == "replied_to":
            return ref.get("id")
    return None
