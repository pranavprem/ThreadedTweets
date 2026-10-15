"""Command entry points, including the failure path with no X credentials."""

import json
from pathlib import Path

import pytest

from main import main
from replies import main as replies_main
from threadedtweets.model import Tweet
from tweet_processor import TweetProcessor

EXAMPLE = Path(__file__).resolve().parents[1] / "examples" / "thread.jsonl"


def test_main_prints_the_sample_thread(capsys):
    assert main(["--file", str(EXAMPLE)]) == 0
    out = capsys.readouterr().out
    assert out.startswith("ada (100)\n")
    assert "grace (104)" in out
    assert "unrelated" not in out


def test_replies_prints_jsonl_without_the_root(capsys):
    assert replies_main(["--file", str(EXAMPLE)]) == 0
    lines = capsys.readouterr().out.splitlines()
    payloads = [json.loads(line) for line in lines]
    assert [item["id"] for item in payloads] == [101, 102, 104, 103]
    assert payloads[0]["user"]["screen_name"] == "grace"
    assert payloads[0]["in_reply_to_status_id"] == 100


def test_empty_thread_exits_cleanly(tmp_path, capsys):
    path = tmp_path / "root.jsonl"
    path.write_text(
        '{"id": 5, "text": "alone", "user": {"screen_name": "ada"}}\n',
        encoding="utf-8",
    )
    assert main(["--file", str(path)]) == 0
    assert "(no replies in the search results)" in capsys.readouterr().out
    assert replies_main(["--file", str(path)]) == 0
    assert capsys.readouterr().out == ""


def test_root_flag_and_a_missing_file(tmp_path, capsys):
    path = tmp_path / "two.jsonl"
    path.write_text(
        "\n".join(
            [
                '{"id": 1, "text": "a", "user": {"screen_name": "ada"}}',
                '{"id": 2, "text": "b", "user": {"screen_name": "grace"}}',
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    assert main(["--file", str(path)]) == 2
    assert "several possible roots" in capsys.readouterr().err
    assert main(["--file", str(path), "--root", "1"]) == 0
    assert replies_main(["--file", str(tmp_path / "nope.jsonl")]) == 2
    assert "not found" in capsys.readouterr().err


def test_usage_errors():
    with pytest.raises(SystemExit) as caught:
        main([])
    assert caught.value.code == 2
    with pytest.raises(SystemExit) as caught:
        main(["100", "--file", str(EXAMPLE)])
    assert caught.value.code == 2
    with pytest.raises(SystemExit) as caught:
        replies_main(["--root", "100"])
    assert caught.value.code == 2


def test_live_lookup_uses_the_injected_client(monkeypatch, capsys):
    class Fake:
        def get_tweet(self, tweet_id):
            assert tweet_id == 100
            return Tweet(100, "ada", "hello", None)

        def search(self, screen_name, since_id):
            if since_id == 100:
                return [Tweet(101, "grace", "a reply", 100)]
            return []

    monkeypatch.setattr("threadedtweets.cli.client_from_env", lambda env=None: Fake())
    assert main(["100"]) == 0
    assert "grace (101)" in capsys.readouterr().out
    assert replies_main(["100"]) == 0
    payload = json.loads(capsys.readouterr().out.strip())
    assert payload["id"] == 101


def test_live_without_a_token_exits_with_an_explanation(monkeypatch, capsys):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    monkeypatch.setenv("ACCESS_TOKEN", "legacy-token")
    assert main(["910002272825831425"]) == 2
    err = capsys.readouterr().err
    assert "X_BEARER_TOKEN" in err
    assert "not read" in err
    assert "legacy-token" not in err


def test_constructing_the_processor_does_not_touch_credentials(monkeypatch):
    monkeypatch.delenv("X_BEARER_TOKEN", raising=False)
    TweetProcessor()
