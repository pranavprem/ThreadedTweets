# ThreadedTweets

ThreadedTweets reconstructs the replies under one tweet and prints them as an indented thread, the way a comment tree reads on a forum. A second command prints the same replies as line-oriented JSON.

Pranav Prem wrote the project over three days in September 2017 ([pranavprem/ThreadedTweets](https://github.com/pranavprem/ThreadedTweets)). A long argument under a single post was hard to follow, and the README he left said the code was an attempt at "a threaded view like reddit for a root tweet." The last commit, on 20 September 2017, ends with `TODO: make the GUI`. The GUI was never started. Output is text.

## How it works

In 2017 the Twitter API had no call that meant "replies to this tweet." The usual workaround, and the one this repo still uses, is a search plus a filter:

1. Start from a root tweet.
2. Search recent posts directed at that author (`to:username`) with an id newer than the parent's.
3. Keep a post only when its reply target is that parent. Mentions and quote tweets drop out.
4. Repeat for each kept reply, so replies to replies are included.
5. Indent the result, two spaces per level.

That search, then and now, covers about the last seven days. Older branches are outside what a live run can see.

The first `replies.py` is [Ed Summers' script of the same name](https://gist.github.com/edsu/54e6f7d63df3866a87a15aed17b51eaf). Pranav committed it, then pointed `__main__` at one hardcoded status (`909922763774861314`, 18 September 2017, 23:31 UTC) instead of the JSONL file the docstring described. `main.py` started a second path on tweepy and a status from the next morning (`910002272825831425`). It imported `twitter_handler`, a module that was never committed, so that path could not run.

## Run it today

Python 3.11 or newer. The program uses the standard library only. Tests and lint use the pins in `requirements-dev.txt`.

```bash
python3 main.py --file examples/thread.jsonl
python3 replies.py --file examples/thread.jsonl
```

### Offline, from a JSONL archive

This path makes no network calls. It is how the project runs without an X developer account.

Each line is one JSON object. Blank lines and `#` comments are ignored. The fields the 2017 script already used are enough:

```json
{"id": 100, "text": "What is the best way to read a long Twitter argument?", "user": {"screen_name": "ada"}, "in_reply_to_status_id": null}
```

`id_str` and `full_text` from API v1.1 are accepted, and so is a v2 tweet with `referenced_tweets` of type `replied_to`. When both `id` and `id_str` are present, `id_str` wins, because these ids are wider than JavaScript's safe integer range. `json` in Python writes them back as exact digits.

When the file has a single root (a tweet that is not a reply to anything else in the file), `--root` is optional. Pass `--root ID` when several conversations share a file.

`replies.py` writes one JSON object per reply and leaves the root out, which is the stdout contract from the original docstring (`replies.py tweets.json > replies.json`). `main.py` prints the indented transcript, including the root.

A reply whose id is lower than its parent's is ignored. The 2017 search used `since_id`, which means "strictly newer," and snowflake ids increase with time. Hand-built files need increasing ids along each branch.

### Live, against the X API

```bash
export X_BEARER_TOKEN=...   # see .env.example; the program does not read that file
python3 main.py TWEET_ID
python3 replies.py TWEET_ID
```

What that call actually does:

- `GET https://api.x.com/2/tweets/:id` loads the root.
- `GET https://api.x.com/2/tweets/search/recent?query=to:USERNAME` loads candidates, then the same filter as offline mode keeps real replies. Pages follow `meta.next_token`, at most 10 pages (1000 posts) per parent.
- The walk stops after 25 reply levels.

Twitter API v1.1 `GET search/tweets`, which `python-twitter` 3.3 and tweepy 3.5 both called, was retired on 20 September 2023. Recent search is the replacement X documents for that endpoint. It is a paid, credit-metered read. Prices move; the X developer console is the source of truth. A token without read credit cannot fetch a thread.

If `X_BEARER_TOKEN` is unset, rejected, out of credits, or rate-limited past two retries, the command prints the reason on stderr and exits 2. The 2017 variables `CONSUMER_KEY`, `CONSUMER_SECRET`, `ACCESS_TOKEN`, and `ACCESS_TOKEN_SECRET` are not read. The tool does not scrape X and does not call unofficial hosts. Use `--file` when you already have the posts.

v2 search also accepts a `conversation_id:` operator that returns a whole thread in one query. This project keeps the `to:username` search and the reply-target filter so the original method stays what the code does.

## Sample

`python3 main.py --file examples/thread.jsonl` prints:

```text
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
```

There is no graphical interface, so there are no screenshots. The 2017 README said "Screenshots to follow on completion." The indented transcript is that view.

## Tech stack

- Python 3.11+ (CI runs 3.12). Developed on 3.12.
- Standard library: `urllib`, `json`, `argparse`.
- Dev and CI: pytest 9.1.1, ruff 0.17.0 (`requirements-dev.txt`).
- 2017 runtime, removed from the tree: Python 2.7, tweepy 3.5.0, python-twitter 3.3, and a virtualenv committed as `env/`.

## Project structure

```text
main.py                 indented thread (the command the GUI was going to sit on)
replies.py              JSONL replies, one object per line
tweet_processor.py      TweetProcessor.get_required_tweets, the 2017 class
twitter_handler.py      search seam that class imported and the repo lacked
threadedtweets/
  model.py              Tweet, parsing, tree, indented render
  collect.py            the search-and-filter walk
  archive.py            JSONL loader and the offline search client
  x_client.py           X API v2 recent search, and the errors around it
  cli.py                shared arguments
examples/thread.jsonl   the sample above
tests/                  walk, client, and both commands
.github/workflows/ci.yml
```

## Checks

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements-dev.txt
ruff check .
ruff format --check .
pytest
```

GitHub Actions runs those three commands on Python 3.12.

## Limits

- Live results are about the last seven days, and each page is a billed read. A busy thread can issue up to 10 search requests per reply that itself has replies, plus one lookup for the root.
- Offline mode applies the reply-target filter and the newer-id window. It cannot replay the `to:username` prefilter.
- No GUI, no database, no background job. A thread is one process and one stdout.
