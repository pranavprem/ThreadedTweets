"""X API client: pagination, auth, and failures that stay off the network."""

import io
import json
import urllib.error

import pytest

from threadedtweets.x_client import (
    MAX_PAGES,
    MISSING_TOKEN,
    XApiError,
    XClient,
    client_from_env,
)


class Response:
    def __init__(self, payload):
        self._raw = json.dumps(payload).encode()

    def read(self):
        return self._raw

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def http_error(status, body=b"{}", headers=None):
    return urllib.error.HTTPError(
        "https://api.x.com/2/tweets/search/recent",
        status,
        "error",
        headers or {},
        io.BytesIO(body if isinstance(body, bytes) else body.encode()),
    )


def test_missing_token_explains_the_retired_endpoint():
    with pytest.raises(XApiError) as caught:
        client_from_env({})
    message = str(caught.value)
    assert message == MISSING_TOKEN
    assert "X_BEARER_TOKEN" in message
    assert "search/recent" in message


def test_legacy_oauth_variables_are_called_out():
    with pytest.raises(XApiError) as caught:
        client_from_env({"CONSUMER_KEY": "old-app-key", "X_BEARER_TOKEN": "  "})
    message = str(caught.value)
    assert "not read" in message
    assert "old-app-key" not in message


def test_token_is_stripped_and_kept_out_of_the_url():
    seen = {}

    def opener(request, timeout):
        seen["url"] = request.full_url
        seen["auth"] = request.get_header("Authorization")
        seen["timeout"] = timeout
        return Response({"data": [], "meta": {"result_count": 0}})

    client = client_from_env({"X_BEARER_TOKEN": "  super-secret-token  "})
    client._opener = opener
    assert client.search("ada", 100) == []
    assert seen["auth"] == "Bearer super-secret-token"
    assert "super-secret-token" not in seen["url"]
    assert "query=to%3Aada" in seen["url"]
    assert "since_id=100" in seen["url"]
    assert "max_results=100" in seen["url"]


def test_short_page_does_not_wait_for_100_hits():
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        return Response(
            {
                "data": [
                    {
                        "id": "101",
                        "text": "reply",
                        "author_id": "7",
                        "referenced_tweets": [{"type": "replied_to", "id": "100"}],
                    }
                ],
                "includes": {"users": [{"id": "7", "username": "grace"}]},
                "meta": {"result_count": 1},
            }
        )

    tweets = XClient("tok", opener=opener, sleep=lambda _seconds: None).search(
        "ada", 100
    )
    assert len(calls) == 1
    assert tweets[0].id == 101
    assert tweets[0].screen_name == "grace"
    assert tweets[0].in_reply_to_status_id == 100


def test_pagination_follows_next_token_and_stops_at_the_cap():
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        return Response(
            {
                "data": [{"id": str(1000 + len(calls)), "text": "x", "author_id": "1"}],
                "includes": {"users": [{"id": "1", "username": "ada"}]},
                "meta": {"next_token": f"page-{len(calls)}"},
            }
        )

    tweets = XClient("tok", opener=opener, sleep=lambda _seconds: None).search(
        "ada", 50
    )
    assert len(calls) == MAX_PAGES
    assert len(tweets) == MAX_PAGES
    assert "next_token=page-1" in calls[1]


def test_http_403_is_explained_and_not_retried():
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        raise http_error(403, b'{"detail":"Credits required"}')

    sleeps = []
    client = XClient("super-secret-token", opener=opener, sleep=sleeps.append)
    with pytest.raises(XApiError) as caught:
        client.search("ada", 100)
    assert caught.value.status == 403
    assert "HTTP 403" in str(caught.value)
    assert "Credits required" in str(caught.value)
    assert "super-secret-token" not in str(caught.value)
    assert sleeps == []
    assert len(calls) == 1


def test_token_in_an_error_body_is_redacted():
    def opener(request, timeout):
        raise http_error(401, b'{"detail":"bad super-secret-token"}')

    client = XClient("super-secret-token", opener=opener)
    with pytest.raises(XApiError) as caught:
        client.get_tweet(100)
    assert "super-secret-token" not in str(caught.value)
    assert "[redacted]" in str(caught.value)
    assert caught.value.status == 401


def test_429_retries_then_succeeds():
    attempts = {"n": 0}

    def opener(request, timeout):
        attempts["n"] += 1
        if attempts["n"] < 3:
            raise http_error(429, b"{}", {"Retry-After": "0"})
        return Response(
            {
                "data": {
                    "id": "100",
                    "text": "root",
                    "author_id": "7",
                },
                "includes": {"users": [{"id": "7", "username": "ada"}]},
            }
        )

    sleeps = []
    tweet = XClient("tok", opener=opener, sleep=sleeps.append).get_tweet(100)
    assert tweet.screen_name == "ada"
    assert sleeps == [0.0, 0.0]


def test_429_gives_up_after_the_retry_budget():
    def opener(request, timeout):
        raise http_error(429, b'{"detail":"slow down"}')

    sleeps = []
    client = XClient("tok", opener=opener, sleep=sleeps.append, max_retries=2)
    with pytest.raises(XApiError) as caught:
        client.search("ada", 100)
    assert caught.value.status == 429
    assert len(sleeps) == 2
    assert "slow down" in str(caught.value)


def test_unreachable_host_and_non_json_body():
    def refuse(request, timeout):
        raise urllib.error.URLError("name resolution failed")

    with pytest.raises(XApiError, match="Could not reach the X API"):
        XClient("tok", opener=refuse).search("ada", 100)

    def garbage(request, timeout):
        class Body:
            def read(self):
                return b"<!DOCTYPE html>"

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

        return Body()

    with pytest.raises(XApiError, match="not JSON"):
        XClient("tok", opener=garbage).search("ada", 100)


def test_username_that_could_change_the_query_is_rejected_before_the_request():
    def opener(request, timeout):
        raise AssertionError("request should not be sent")

    client = XClient("tok", opener=opener)
    with pytest.raises(XApiError, match="username"):
        client.search("ada OR from:someone", 100)


def test_api_error_object_without_data():
    def opener(request, timeout):
        return Response({"errors": [{"message": "invalid query"}]})

    with pytest.raises(XApiError, match="invalid query"):
        XClient("tok", opener=opener).search("ada", 100)
