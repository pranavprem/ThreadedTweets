"""Archive parsing, the reply walk, and the indented transcript."""

import json
from pathlib import Path

import pytest

from threadedtweets.archive import FileSearchClient, infer_root, load_jsonl
from threadedtweets.collect import collect_replies
from threadedtweets.model import (
    Tweet,
    build_thread,
    coerce_tweet,
    dump_tweet,
    render_thread,
    tweet_from_obj,
    tweets_from_payload,
)
from tweet_processor import TweetProcessor

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "thread.jsonl"

EXPECTED = """\
ada (100)
What is the best way to read a long Twitter argument?
https://twitter.com/ada/status/100

  grace (101)
  Start at the root and indent the replies.
  https://twitter.com/grace/status/101

    ada (102)
    Like a comment tree.
    https://twitter.com/ada/status/102

      grace (104)
      This one replies to the nested reply.
      https://twitter.com/grace/status/104

  linus (103)
  Search only goes back about a week, though.
  https://twitter.com/linus/status/103
"""


def test_example_archive_renders_a_thread():
    tweets = load_jsonl(EXAMPLE)
    root = infer_root(tweets, None)
    replies = collect_replies(root, FileSearchClient(tweets))
    assert [tweet.id for tweet in replies] == [101, 102, 104, 103]
    assert render_thread(build_thread(root, replies)) == EXPECTED


def test_processor_matches_the_walk_and_keeps_each_reply_once():
    tweets = load_jsonl(EXAMPLE)
    root = infer_root(tweets, None)
    found = TweetProcessor(FileSearchClient(tweets)).get_required_tweets(root)
    assert [tweet.id for tweet in found] == [101, 102, 104, 103]


def test_mentions_and_quotes_are_not_replies():
    root = Tweet(1, "ada", "root", None)
    tweets = [
        root,
        Tweet(2, "grace", "real reply", 1),
        Tweet(3, "eve", "hello @ada", None),
        tweet_from_obj(
            {
                "id": "4",
                "text": "quoting",
                "username": "linus",
                "referenced_tweets": [{"type": "quoted", "id": "1"}],
            }
        ),
    ]
    found = collect_replies(root, FileSearchClient(tweets))
    assert [tweet.id for tweet in found] == [2]


def test_grandchild_on_the_parent_page_is_kept_when_its_parent_is_walked():
    root = Tweet(1, "ada", "root", None)
    child = Tweet(2, "grace", "child", 1)
    grand = Tweet(3, "ada", "grand", 2)

    class Paged:
        def search(self, screen_name, since_id):
            if since_id == 1:
                return [child, grand]
            if since_id == 2:
                return [grand]
            return []

    assert [tweet.id for tweet in collect_replies(root, Paged())] == [2, 3]


def test_cycles_stop():
    root = Tweet(1, "ada", "root", None)

    class Loop:
        def search(self, screen_name, since_id):
            return [
                Tweet(2, "grace", "child", 1),
                Tweet(3, "ada", "back", 2),
            ]

    assert [tweet.id for tweet in collect_replies(root, Loop())] == [2, 3]


def test_depth_limit():
    tweets = [Tweet(1, "ada", "root", None)]
    tweets.extend(Tweet(i, "ada", str(i), i - 1) for i in range(2, 8))
    found = collect_replies(tweets[0], FileSearchClient(tweets), max_depth=2)
    assert [tweet.id for tweet in found] == [2, 3]


def test_reply_with_a_lower_id_than_its_parent_is_outside_the_window():
    root = Tweet(10, "ada", "root", None)
    child = Tweet(12, "grace", "child", 10)
    older = Tweet(11, "linus", "id is below the parent", 12)
    found = collect_replies(root, FileSearchClient([root, child, older]))
    assert [tweet.id for tweet in found] == [12]


def test_duplicate_replies_attach_once():
    root = Tweet(1, "ada", "root", None)
    child = Tweet(2, "grace", "child", 1)
    tree = build_thread(root, [child, child])
    assert [node.tweet.id for node in tree.children] == [2]


def test_id_str_wins_over_a_rounded_id():
    tweet = tweet_from_obj(
        {
            "id": 1,
            "id_str": "910002272825831425",
            "full_text": "full text",
            "text": "truncated",
            "user": {"screen_name": "ada"},
            "in_reply_to_status_id_str": "909922763774861314",
        }
    )
    assert tweet.id == 910002272825831425
    assert tweet.text == "full text"
    assert tweet.in_reply_to_status_id == 909922763774861314


def test_v2_payload_joins_the_author():
    tweets = tweets_from_payload(
        {
            "data": [
                {
                    "id": "101",
                    "text": "reply",
                    "author_id": "42",
                    "created_at": "2017-09-18T23:31:07.000Z",
                    "referenced_tweets": [{"type": "replied_to", "id": "100"}],
                }
            ],
            "includes": {"users": [{"id": "42", "username": "grace"}]},
        }
    )
    assert tweets[0].screen_name == "grace"
    assert tweets[0].in_reply_to_status_id == 100
    assert tweets[0].created_at == "2017-09-18T23:31:07.000Z"


def test_coerce_status_like_object():
    class User:
        screen_name = "ada"

    class Status:
        id = 100
        user = User()
        full_text = "extended"
        text = "short"
        in_reply_to_status_id = None

    tweet = coerce_tweet(Status())
    assert tweet == Tweet(100, "ada", "extended", None)


def test_infer_root_requires_a_choice_when_several_exist():
    tweets = [Tweet(1, "ada", "one", None), Tweet(2, "grace", "two", None)]
    with pytest.raises(ValueError, match="several possible roots"):
        infer_root(tweets, None)
    assert infer_root(tweets, 2).id == 2


def test_missing_root_and_bad_json_name_the_line(tmp_path):
    path = tmp_path / "bad.jsonl"
    path.write_text('{"id": 1, "text": "ok", "user": {"screen_name": "ada"}}\n{nope}\n')
    with pytest.raises(ValueError, match=r"bad.jsonl:2:"):
        load_jsonl(path)
    with pytest.raises(ValueError, match="not found"):
        load_jsonl(tmp_path / "missing.jsonl")


def test_multiline_text_stays_indented():
    root = Tweet(1, "ada", "line one\nline two", None)
    rendered = render_thread(build_thread(root, []))
    assert "ada (1)\nline one\nline two\nhttps://twitter.com/ada/status/1\n" in rendered
    assert "(no replies in the search results)" in rendered


def test_round_trip_json():
    tweet = Tweet(101, "grace", "hi", 100, created_at="2017-09-18T00:00:00Z")
    loaded = tweet_from_obj(json.loads(dump_tweet(tweet)))
    assert loaded == tweet
