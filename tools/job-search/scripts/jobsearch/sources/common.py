"""Shared search CLI output helpers."""

import json

from jobsearch.fetchconfig import DEFAULT as DEFAULT_FETCH
from jobsearch import text as _text


def posting(source, title, company, location, remote, url, tags, salary, posted_date, description,
            config=None):
    return _text.posting(
        source, title, company, location, remote, url, tags, salary, posted_date, description,
        config=config or DEFAULT_FETCH,
    )


def description_text(html, config=None):
    return _text.description_text(html, config=config or DEFAULT_FETCH)


def print_search_result(source, results, error, extra=None):
    out = {"source": source, "error": error, "results": results}
    if extra:
        out.update(extra)
    print(json.dumps(out, indent=2))


def print_detail_result(source, result, error):
    print(json.dumps({"source": source, "error": error, "result": result}, indent=2))
