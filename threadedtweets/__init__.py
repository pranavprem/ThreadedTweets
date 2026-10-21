"""Threaded view of replies to a single tweet.

The walk is the 2017 search heuristic: posts directed at the parent author,
kept only when they actually reply to that parent, then repeated for each
reply. ``XClient`` runs that search against the current X API. ``FileSearchClient``
runs it against a JSONL archive so the project works with no credentials.
"""

__all__ = ["__version__"]

__version__ = "0.2.0"
