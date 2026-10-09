"""Radar merge: dedupe, closed marking, prune."""

from datetime import date

from jobsearch.radar_enrich import is_target_location, posting_key  # noqa: F401 — re-export

CLOSED_AFTER_DAYS = 3
PRUNE_AFTER_DAYS = 30

def merge(state, fresh, today):
    """Fold this run's enriched postings into radar state. Existing postings keep first_seen
    and any richer fields; ATS copies win over LinkedIn mirrors for url/description."""
    postings = state.setdefault("postings", {})
    for key, p in fresh.items():
        old = postings.get(key)
        if old is None:
            p.update(first_seen=today, last_seen=today, closed=False,
                     sources=[p["source"]], alt_urls=[])
            postings[key] = p
            continue
        old["last_seen"], old["closed"] = today, False
        if p["source"] not in old["sources"]:
            old["sources"].append(p["source"])
        prefer_new = old["source"] == "linkedin" and p["source"] != "linkedin"
        if prefer_new:
            if old["url"] and old["url"] not in old["alt_urls"]:
                old["alt_urls"].append(old["url"])
            for field in ("url", "source", "title", "location"):
                old[field] = p[field]
        elif p["url"] and p["url"] != old["url"] and p["url"] not in old["alt_urls"]:
            old["alt_urls"].append(p["url"])
        for field, value in p.items():
            if field in ("url", "source", "sources", "alt_urls"):
                continue
            if value not in (None, [], "") and (prefer_new or old.get(field) in (None, [], "")):
                old[field] = value
    for key in list(postings):
        unseen_days = (date.fromisoformat(today) - date.fromisoformat(postings[key]["last_seen"])).days
        if unseen_days >= PRUNE_AFTER_DAYS:
            del postings[key]
        else:
            postings[key]["closed"] = unseen_days >= CLOSED_AFTER_DAYS
    return state
