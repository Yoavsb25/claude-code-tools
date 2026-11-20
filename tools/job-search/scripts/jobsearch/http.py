"""HTTP helpers for board fetches. Never raise; return (data, error)."""

import json
import random
import time
import urllib.error
import urllib.request

from jobsearch.fetchconfig import DEFAULT as DEFAULT_FETCH

USER_AGENT = "job-search-skill/1.2 (+https://github.com/Yoavsb25/claude-code-tools)"
LINKEDIN_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)
LINKEDIN_MAX_RETRIES = 6
LINKEDIN_BACKOFF_BASE_MS = 500
LINKEDIN_BACKOFF_CAP_MS = 8000
APIFY_TIMEOUT = 90


def http_get_html_backoff(url, config=None):
    config = config or DEFAULT_FETCH
    delay_ms = LINKEDIN_BACKOFF_BASE_MS
    for attempt in range(LINKEDIN_MAX_RETRIES + 1):
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": LINKEDIN_USER_AGENT,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "X-Requested-With": "XMLHttpRequest",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=config.timeout) as resp:
                return resp.read().decode("utf-8"), None
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return "", None
            if e.code == 429 or e.code >= 500:
                if attempt == LINKEDIN_MAX_RETRIES:
                    return None, f"HTTP {e.code} from {url} after {attempt + 1} attempts"
                jitter_ms = random.randint(0, 500)
                time.sleep((delay_ms + jitter_ms) / 1000)
                delay_ms = min(delay_ms * 2, LINKEDIN_BACKOFF_CAP_MS)
                continue
            return None, f"HTTP {e.code} from {url}"
        except urllib.error.URLError as e:
            return None, f"network error reaching {url}: {e.reason}"
        except Exception as e:
            return None, f"unexpected error fetching {url}: {e}"
    return None, f"request to {url} failed after max retries"

def http_get_json(url, config=None):
    config = config or DEFAULT_FETCH
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=config.timeout) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} from {url}"
    except urllib.error.URLError as e:
        return None, f"network error reaching {url}: {e.reason}"
    except json.JSONDecodeError as e:
        return None, f"invalid JSON from {url}: {e}"
    except Exception as e:
        return None, f"unexpected error fetching {url}: {e}"


def http_post_json(url, payload, extra_headers=None):
    headers = {
        "User-Agent": USER_AGENT,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    if extra_headers:
        headers.update(extra_headers)
    req = urllib.request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=APIFY_TIMEOUT) as resp:
            return json.loads(resp.read().decode("utf-8")), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} from {url}"
    except urllib.error.URLError as e:
        return None, f"network error reaching {url}: {e.reason}"
    except json.JSONDecodeError as e:
        return None, f"invalid JSON from {url}: {e}"
    except Exception as e:
        return None, f"unexpected error fetching {url}: {e}"

def http_get_html(url, config=None):
    """Plain HTML GET for reading a career page's markup -- no retry/backoff (unlike
    http_get_html_backoff, which is tuned specifically for LinkedIn's rate limiting). Same
    (text, error) contract as http_get_json: never raises."""
    config = config or DEFAULT_FETCH
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "text/html,application/xhtml+xml"}
    )
    try:
        with urllib.request.urlopen(req, timeout=config.timeout) as resp:
            return resp.read().decode("utf-8", errors="replace"), None
    except urllib.error.HTTPError as e:
        return None, f"HTTP {e.code} from {url}"
    except urllib.error.URLError as e:
        return None, f"network error reaching {url}: {e.reason}"
    except Exception as e:
        return None, f"unexpected error fetching {url}: {e}"
