# Agent guide

ThreadedTweets turns one root tweet plus its replies into an indented thread. The walk is the 2017 search heuristic. Read [README.md](README.md) for history and how to run it. This file is the working map.

## Architecture

- `threadedtweets/model.py` holds `Tweet`, JSON parsing, `build_thread`, and `render_thread`. Tweet ids are Python ints.
- `threadedtweets/collect.py` is the heuristic. `collect_replies` asks a `ReplySearch` client for candidates, keeps a tweet only when `in_reply_to_status_id` is the parent, then walks that reply. Depth stops at `MAX_DEPTH` (25).
- `threadedtweets/archive.py` is the offline client. `FileSearchClient.search` returns archive tweets with a greater id than `since_id`. It does not apply `to:username`, because a saved line does not record the search query.
- `threadedtweets/x_client.py` is the live client. `get_tweet` calls `GET /2/tweets/:id`. `search` calls `GET /2/tweets/search/recent?query=to:USERNAME` and follows `next_token` for at most `MAX_PAGES` (10) pages. Failures raise `XApiError` with a status and a short reason. The bearer token is stripped out of those messages.
- `twitter_handler.py` is the module the 2017 `tweet_processor` imported and never committed. `TwitterHandler.search` matches `ReplySearch`. With no client injected, the first search builds an `XClient` from the environment.
- `tweet_processor.py` is the class from the last 2017 commit. `TweetProcessor.get_required_tweets` coerces a dict, a `Tweet`, or a status-like object and returns a flat depth-first list. It returns `[]` when there are no replies.
- `threadedtweets/cli.py` parses arguments. `main.py` prints the indented thread. `replies.py` prints one JSON object per reply, root excluded.
- `examples/thread.jsonl` is the sample conversation. Tests and the README both use it.

Constructing `TweetProcessor` or importing `main` does not read credentials and does not open a socket. The network happens inside `XClient._get`.

## Commands

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
ruff format .
pytest
python3 main.py --file examples/thread.jsonl
python3 replies.py --file examples/thread.jsonl
```

CI (`.github/workflows/ci.yml`) installs `requirements-dev.txt` on Python 3.12 and runs `ruff check`, `ruff format --check`, and `pytest`. `pyproject.toml` sets `pythonpath = ["."]` so pytest can import `threadedtweets` and `main`.

There is no runtime dependency file. The program uses the standard library. Do not add a package unless a change truly needs it.

Live lookup, only with a token you are willing to spend credits on:

```bash
export X_BEARER_TOKEN=...
python3 main.py TWEET_ID
```

## Conventions

- Python 3.11 or newer. Type hints use `list[Tweet]` and `int | None`.
- Format and lint with ruff. Settings are in `pyproject.toml` (`E`, `F`, `I`, `UP`, `B`; line length 88).
- CLIs catch `XApiError`, `ValueError`, and `OSError`, print the message on stderr, and exit 2. Usage errors stay argparse's `SystemExit(2)`.
- Tests inject an opener or a fake search client. A test that calls `api.x.com` is a bug.
- Secrets stay in the environment. `.env` is gitignored. `.env.example` has an empty `X_BEARER_TOKEN`. The program does not load dotenv files.
- `X_BEARER_TOKEN` is the only credential that is read. `CONSUMER_KEY`, `CONSUMER_SECRET`, `ACCESS_TOKEN`, and `ACCESS_TOKEN_SECRET` are the 2017 v1.1 names and are ignored on purpose.
- Keep class names `TweetProcessor` and `TwitterHandler`. The lowercase aliases `tweet_processor` and `twitter_handler` exist so the old call shape still imports.

## X API boundary

Live reads go through `https://api.x.com/2` recent search and tweet lookup, with an app-only bearer token. Recent search is a paid, credit-metered read and covers about seven days. v1.1 `GET search/tweets` was retired on 20 September 2023.

When the token is missing or X rejects the call, explain that and stop. Offline `--file` mode is the supported way to run with no credentials.

Do not add scrapers, unofficial API hosts, browser automation, or a second search implementation. v2 also has a `conversation_id:` operator; this repo keeps the `to:username` plus `in_reply_to` filter so the original heuristic stays visible. Extending the query is a product change, not a drive-by fix.

A username is checked against `^[A-Za-z0-9_]{1,15}$` before it is placed in the query string.

## Gotchas

- `python-twitter`'s `GetSearch(raw_query=...)` ignored `since_id`, `max_id`, and `count`. The 2017 `replies.py` passed a raw `q=to:user` plus those kwargs, so the window and the page size never reached Twitter. The loop also compared `len(replies) != 100` while requesting `count=20`, so it never paginated, and a full page of 100 would have repeated forever. Pagination now follows `meta.next_token`. Do not restore the raw-query loop.
- The old `tweet_processor` extended the list it was iterating and did not check `in_reply_to_status_id`, so nested replies were duplicated and ordinary mentions were walked. `collect_replies` fixes both. A tweet seen on an ancestor's page is not marked seen unless it is accepted there; otherwise a grandchild returned early would be dropped when its real parent is walked.
- `seen` cuts cycles. Do not remove it.
- Archive mode ignores a reply whose id is lower than its parent's, because `since_id` meant "strictly newer." Sample files need increasing ids along each branch.
- Snowflake ids are wider than `2^53`. Prefer `id_str` over `id` when both are present. Keep ids as ints in Python and let `json` write them as digits.
- `max_id` on `TwitterHandler.get_tweets` is not forwarded. v2 does not use that cursor.
- The September 2017 status ids hardcoded in the old scripts (`909922763774861314`, `910002272825831425`) were sample tweets from the days the repo was written. Their search window closed that month. Do not hardcode them again.
- There is no GUI. The last commit's TODO was "make the GUI." Leave it as text output.
- Do not commit `env/`, `.venv/`, `*.pyc`, `replies.log`, or `.env`. The original repo committed a Python 2.7 virtualenv; that was removed.

## What was left alone

The heuristic, the two entry points (`main.py` for the thread, `replies.py` for JSONL), and the decision not to ship a GUI. No license file was added.
