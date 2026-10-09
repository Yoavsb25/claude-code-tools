#!/usr/bin/env python3
"""
Job Radar: collects every London / UK-remote posting from a company watchlist plus a LinkedIn
sweep, enriches each one with fixed rules (years required, level, role family, salary), and
keeps a running radar.json that the Radar page filters and browses. No LLM, no Claude login,
and nothing is ever applied to or sent anywhere.

Usage:
  radar.py refresh [--no-linkedin] [--max-details 100]
  radar.py daily [--no-linkedin]             refresh, then inbox sync, then commit the state repo (launchd)
  radar.py status
  radar.py serve [--port 8765] [--no-open]   local page at http://127.0.0.1:8765

`serve` refreshes in the background when the data is older than STALE_AFTER_HOURS, so the page
is current even if the Mac was off at 07:00.

State (same dir as job_tool.py: ~/job-search-data, override with JOB_SEARCH_DIR):
  companies.json  - watchlist: [{name, platform, slug, tier}], seeded from profile.json
  radar.json      - {updated_at, postings: {key: posting}}; marked closed after
                    CLOSED_AFTER_DAYS unseen, dropped after PRUNE_AFTER_DAYS
  coverage.json   - per-company fetch result of the last refresh + LinkedIn stats +
                    companies seen on LinkedIn that aren't on the watchlist yet
  radar_state.json - the page's Hide / Save choices and last visit time
  cockpit_state.json - public-proof log behind the weekly 3/2/1 targets (cockpit.py)

The page is the Job Cockpit: Today (replies, emails to sort, follow-ups, automatic changes with
Undo), Roles (this radar), Pipeline (edit the tracker) and Insights (what converts).
"""

import argparse
import json
import re
import subprocess
import sys
import threading
import time
import urllib.parse
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from jobsearch import cockpit
import inbox
import job_tool
from jobsearch.fetchconfig import RADAR as RADAR_FETCH

# CLOSED_AFTER_DAYS / PRUNE_AFTER_DAYS imported from jobsearch.radar_merge below
STALE_AFTER_HOURS = 12
PAGE_PATH = Path(__file__).with_name("radar.html")
HIDE_REASONS = {"too senior", "wrong work", "pay", "company", "other"}
COMPANY_WORKERS = 6
LINKEDIN_PAGES_PER_QUERY = 3
LINKEDIN_MAX_DETAILS = 100
LINKEDIN_LOCATION = "London, England, United Kingdom"
LINKEDIN_JOBAGE_DAYS = 7
LINKEDIN_DELAY_S = 1.0
STORED_DESCRIPTION_CHARS = 6000
# Built from the capability map (docs/job-radar-plan.md): market language, not job titles.
LINKEDIN_QUERIES = [
    "platform engineer", "developer experience", "devops engineer", "automation engineer",
    "AI engineer", "forward deployed engineer", "solutions engineer", "technical program manager",
    "software engineer python", "internal tools engineer",
]
WORKDAY_MAX_SCANNED = 80

from jobsearch import radar_enrich as _enrich
from jobsearch import radar_merge as _merge

# Enrichment / merge re-exports (tests and refresh call these as radar.*)
STORED_DESCRIPTION_CHARS = _enrich.STORED_DESCRIPTION_CHARS
NUMBER_WORDS = _enrich.NUMBER_WORDS
YEARS_RE = _enrich.YEARS_RE
YEARS_NOISE_RE = _enrich.YEARS_NOISE_RE
NICE_TO_HAVE_RE = _enrich.NICE_TO_HAVE_RE
LEVEL_RULES = _enrich.LEVEL_RULES
LINKEDIN_SENIORITY_LEVELS = _enrich.LINKEDIN_SENIORITY_LEVELS
ROLE_FAMILY_RULES = _enrich.ROLE_FAMILY_RULES
NON_TECH_RE = _enrich.NON_TECH_RE
OTHER_LANGUAGE_RE = _enrich.OTHER_LANGUAGE_RE
DEAL_BREAKER_RE = _enrich.DEAL_BREAKER_RE
RECRUITER_NAME_RE = _enrich.RECRUITER_NAME_RE
RECRUITER_TEXT_RE = _enrich.RECRUITER_TEXT_RE
SALARY_RE = _enrich.SALARY_RE
LONDON_RE = _enrich.LONDON_RE
UK_REMOTE_RE = _enrich.UK_REMOTE_RE
SKILLS = _enrich.SKILLS
LANGUAGES = _enrich.LANGUAGES
BLOCKED_FIT_CAP = _enrich.BLOCKED_FIT_CAP

_to_int = _enrich._to_int
_sentences = _enrich._sentences
extract_years = _enrich.extract_years
profile_skills = _enrich.profile_skills
skill_fit = _enrich.skill_fit
classify_level = _enrich.classify_level
role_family = _enrich.role_family
_salary_value = _enrich._salary_value
extract_salary = _enrich.extract_salary
on_watchlist = _enrich.on_watchlist
is_recruiter = _enrich.is_recruiter
is_target_location = _enrich.is_target_location
posting_key = _enrich.posting_key
title_flags = _enrich.title_flags
enrich = _enrich.enrich

CLOSED_AFTER_DAYS = _merge.CLOSED_AFTER_DAYS
PRUNE_AFTER_DAYS = _merge.PRUNE_AFTER_DAYS
merge = _merge.merge


def _path(name):
    return job_tool.state_dir() / name


def load_watchlist():
    """companies.json, seeded from profile.json target_companies the first time."""
    path = _path("companies.json")
    if path.exists():
        return job_tool.load_json(path, [])
    profile = job_tool.load_json(job_tool.profile_path(), {})
    seeded = [
        {"name": c["name"], "platform": c.get("platform") or "linkedin-only",
         "slug": c.get("slug"), "tier": c.get("tier")}
        for c in profile.get("target_companies", [])
    ]
    for c in seeded:
        if c["platform"] == "other" or not c["slug"]:
            c["platform"], c["slug"] = "linkedin-only", None
    job_tool.save_json(path, seeded)
    return seeded


def reclassify(state):
    """Re-run the rules over stored postings so rule fixes (and profile skill changes) apply to old
    postings too."""
    have = profile_skills()
    for p in state["postings"].values():
        p.update(skill_fit(f"{p['title']}\n{p.get('description') or ''}", have))
        p["role_family"] = role_family(p["title"])
        title_level = classify_level(p["title"])
        if title_level != "unknown":
            p["level"] = title_level
        if p.get("description"):
            p["years_min"], p["years_evidence"] = extract_years(p["description"])
        flags = [f for f in p.get("flags", []) if f not in ("recruiter", "other_language")]
        flags += title_flags(p["title"])
        if is_recruiter(p["company"], p.get("description")):
            flags.append("recruiter")
        p["flags"] = flags


# ---- fetching ----------------------------------------------------------------

def fetch_company(company):
    """Returns (company_name, postings, error). Never raises. Retries once on a transient error."""
    name, results, err = _fetch_company_once(company)
    if err:
        time.sleep(2)
        name, results, err = _fetch_company_once(company)
    return name, results, err


def _fetch_company_once(company):
    platform, slug, name = company.get("platform"), company.get("slug"), company["name"]
    try:
        if platform in job_tool.ATS_ENDPOINTS:
            results, err = job_tool.fetch_ats_postings(platform, slug, config=RADAR_FETCH)
        elif platform == "workday":
            tenant, wd_host, site = slug.split("/")
            tenant_info = {
                "tenant": tenant, "wd_host": wd_host, "site": site, "company": name,
                "api_base": f"https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}",
                "public_base": f"https://{tenant}.{wd_host}.myworkdayjobs.com/{site}",
            }
            results, err = job_tool.fetch_workday_postings(
                tenant_info, limit=10000, max_scanned=WORKDAY_MAX_SCANNED, location_hint="London",
                config=RADAR_FETCH)
        elif platform == "comeet":
            token, uid = slug.split(":")
            results, err = job_tool.fetch_comeet_postings(
                token, uid, name, limit=10000, config=RADAR_FETCH)
        else:
            return name, [], None
    except Exception as e:  # a malformed slug must not sink the whole refresh
        return name, [], f"unexpected error: {e}"
    for r in results:
        r["company"] = name  # ATS payloads carry the slug, not the display name
    return name, results or [], err


def fetch_linkedin(max_details, known_keys):
    """LinkedIn sweep: search cards for each query, then detail fetches (description + seniority)
    for cards not already in radar state. Sequential and throttled; LinkedIn rate-limits hard."""
    cards, errors = {}, []
    for query in LINKEDIN_QUERIES:
        for page in range(LINKEDIN_PAGES_PER_QUERY):
            params = {
                "keywords": query, "location": LINKEDIN_LOCATION,
                "f_TPR": job_tool.jobage_to_tpr(LINKEDIN_JOBAGE_DAYS), "start": str(page * 10),
            }
            html, err = job_tool.http_get_html_backoff(
                job_tool.LINKEDIN_SEARCH_URL + "?" + urllib.parse.urlencode(params),
                config=RADAR_FETCH)
            time.sleep(LINKEDIN_DELAY_S)
            if err:
                errors.append(err)
                break
            page_cards = job_tool.parse_linkedin_cards(html or "")
            for c in page_cards:
                cards.setdefault(c["id"], c)
            if len(page_cards) < 10:
                break

    results, details_fetched = [], 0
    for card in cards.values():
        raw = {
            "source": "linkedin", "title": card["title"], "company": card["company"],
            "location": card["location"], "url": card["url"], "posted_date": card["posted_date"],
            "description": None, "salary": None,
        }
        seniority = None
        key = posting_key(card["company"], card["title"])
        if key not in known_keys and details_fetched < max_details:
            html, err = job_tool.http_get_html_backoff(f"{job_tool.LINKEDIN_DETAIL_URL}/{card['id']}", config=RADAR_FETCH)
            time.sleep(LINKEDIN_DELAY_S)
            details_fetched += 1
            if err:
                errors.append(err)
            elif html:
                detail = job_tool.parse_linkedin_detail(html, card["id"])
                raw["description"] = detail.get("description")
                seniority = detail.get("seniority")
        results.append((raw, seniority))
    stats = {"queries": len(LINKEDIN_QUERIES), "cards": len(cards),
             "details_fetched": details_fetched, "errors": errors[:5], "error_count": len(errors)}
    return results, stats


def refresh(use_linkedin=True, max_details=LINKEDIN_MAX_DETAILS, today=None):
    today = today or date.today().isoformat()
    watchlist = load_watchlist()
    state = job_tool.load_json(_path("radar.json"), {"postings": {}})

    fresh, coverage_rows = {}, []
    fetchable = [c for c in watchlist if c.get("platform") != "linkedin-only"]
    with ThreadPoolExecutor(max_workers=COMPANY_WORKERS) as pool:
        for name, results, err in pool.map(fetch_company, fetchable):
            kept = [r for r in results if is_target_location(r.get("location"), r.get("remote"))]
            for r in kept:
                fresh[posting_key(r["company"], r["title"])] = enrich(r)
            coverage_rows.append({"name": name, "ok": err is None, "error": err,
                                  "total": len(results), "london": len(kept)})
    for c in watchlist:
        if c.get("platform") == "linkedin-only":
            coverage_rows.append({"name": c["name"], "ok": None, "error": None,
                                  "total": None, "london": None, "linkedin_only": True})

    previous = job_tool.load_json(_path("coverage.json"), {})
    linkedin_stats, discovered = previous.get("linkedin"), previous.get("discovered") or []
    if use_linkedin:
        known = set(state["postings"]) | set(fresh)
        results, linkedin_stats = fetch_linkedin(max_details, known)
        watch_words = [job_tool.normalize_company(c["name"]) for c in watchlist]
        counts = {}
        for raw, seniority in results:
            if not is_target_location(raw["location"]):
                continue
            key = posting_key(raw["company"], raw["title"])
            if key not in fresh:
                fresh[key] = enrich(raw, seniority)
            words = job_tool.normalize_company(raw["company"] or "")
            if raw["company"] and not is_recruiter(raw["company"]) and not on_watchlist(words, watch_words):
                counts[raw["company"]] = counts.get(raw["company"], 0) + 1
        discovered = sorted(
            ({"company": k, "postings": v} for k, v in counts.items() if k), key=lambda d: -d["postings"])

    merge(state, fresh, today)
    reclassify(state)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state["updated_at"] = stamp
    job_tool.save_json(_path("radar.json"), state)
    coverage = {"updated_at": stamp, "companies": sorted(coverage_rows, key=lambda r: r["name"].lower()),
                "linkedin": linkedin_stats, "discovered": discovered[:50]}
    job_tool.save_json(_path("coverage.json"), coverage)
    return state, coverage


# ---- page server --------------------------------------------------------------

def load_page_state():
    state = job_tool.load_json(_path("radar_state.json"), {})
    state.setdefault("hidden", {})
    state.setdefault("saved", {})
    state.setdefault("last_visit", None)
    return state


def is_stale(radar_state, now=None):
    stamp = (radar_state or {}).get("updated_at")
    if not stamp:
        return True
    now = now or datetime.now(timezone.utc)
    return now - datetime.fromisoformat(stamp) > timedelta(hours=STALE_AFTER_HOURS)


def hide_posting(key, reason):
    if reason not in HIDE_REASONS:
        return None, f"unknown reason {reason!r}"
    state = load_page_state()
    state["hidden"][key] = {"reason": reason, "date": date.today().isoformat()}
    job_tool.save_json(_path("radar_state.json"), state)
    return state["hidden"][key], None


def unhide_posting(key):
    state = load_page_state()
    state["hidden"].pop(key, None)
    job_tool.save_json(_path("radar_state.json"), state)
    return {"key": key}, None


def save_posting(key, tier=None):
    """Add a posting to the tracker as Shortlisted, with the tier chosen on the page and a guessed
    positioning for Yoav to confirm in Pipeline. The only write the page makes outside
    radar_state.json besides cockpit edits; nothing is applied to or sent."""
    radar_state = job_tool.load_json(_path("radar.json"), {"postings": {}})
    p = radar_state["postings"].get(key)
    if p is None:
        return None, "unknown posting"
    patch = {
        "company": p["company"], "role": p["title"], "link": p["url"], "salary": p.get("salary"),
        "role_family": p.get("role_family"), "source": "radar",
        "notes": f"Saved from Radar ({p.get('years_min') or '?'} yrs, {p.get('level')}, fit {p.get('fit', '?')})",
    }
    if tier is not None:
        patch["tier"] = tier
    existing = next((r for r in job_tool.load_rows()["rows"]
                     if job_tool.normalize_company(r["company"]) == job_tool.normalize_company(p["company"])
                     and r["role"].strip().lower() == p["title"].strip().lower()), None)
    if not (existing and existing.get("positioning")):
        guess = job_tool.infer_positioning(p["title"])
        if guess:
            patch.update(positioning=guess, positioning_inferred=True)
    row, err = job_tool.upsert_tracker_row(patch)
    if err:
        return None, err
    state = load_page_state()
    state["saved"][key] = {"tracker_id": row["id"], "date": date.today().isoformat()}
    job_tool.save_json(_path("radar_state.json"), state)
    return state["saved"][key], None


def record_visit():
    state = load_page_state()
    state["last_visit"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    job_tool.save_json(_path("radar_state.json"), state)
    return {"last_visit": state["last_visit"]}, None


def add_to_watchlist(name, tier=None):
    """Probe a company's career-page feed and add it to companies.json. Companies without a
    detectable feed are still added as LinkedIn-only, so they count as covered."""
    name = (name or "").strip()
    if not name:
        return None, "company name required"
    watchlist = load_watchlist()
    words = job_tool.normalize_company(name)
    if any(job_tool.normalize_company(c["name"]) == words for c in watchlist):
        return None, f"{name} is already on the watchlist"
    chosen, confidence, _ = job_tool.discover_ats(name)
    entry = {"name": name, "platform": "linkedin-only", "slug": None, "tier": tier}
    if chosen and confidence == "high":
        entry["platform"], entry["slug"] = chosen[0], chosen[1]
    watchlist.append(entry)
    job_tool.save_json(_path("companies.json"), watchlist)
    return entry, None


class Runner:
    """Runs `target` on a background thread so the page never blocks on a slow job (a 3-minute
    radar refresh, or an inbox sync)."""

    def __init__(self, target):
        self.target = target
        self.lock = threading.Lock()
        self.running = False
        self.last_error = None

    def start(self):
        with self.lock:
            if self.running:
                return False
            self.running = True
        threading.Thread(target=self._run, daemon=True).start()
        return True

    def _run(self):
        try:
            self.target()
            self.last_error = None
        except Exception as e:  # surfaced on the page instead of killing the server
            self.last_error = str(e)
        finally:
            with self.lock:
                self.running = False


def sync_inbox_from_page():
    inbox.run_sync()
    snapshot_state("inbox sync from the page")


LOCAL_HOSTS = ("127.0.0.1", "localhost")


def make_handler(runner, inbox_runner=None):
    inbox_runner = inbox_runner or Runner(sync_inbox_from_page)
    actions = {
        "/api/hide": lambda body: hide_posting(body.get("key"), body.get("reason")),
        "/api/unhide": lambda body: unhide_posting(body.get("key")),
        "/api/save": lambda body: save_posting(body.get("key"), body.get("tier")),
        "/api/visit": lambda body: record_visit(),
        "/api/refresh": lambda body: ({"started": runner.start()}, None),
        "/api/watchlist": lambda body: add_to_watchlist(body.get("company")),
        "/api/tracker": cockpit.update_row,
        "/api/inbox/resolve": lambda body: inbox.resolve(body.get("msg_id"), body.get("row_id")),
        "/api/inbox/done": lambda body: inbox.mark_done(body.get("msg_id")),
        "/api/inbox/undo": lambda body: job_tool.undo_last_status(body.get("row_id")),
        "/api/inbox/sync": lambda body: ({"started": inbox_runner.start()}, None),
        "/api/proof": lambda body: cockpit.add_proof(body.get("title")),
    }

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def _send(self, status, body, content_type="application/json"):
            data = body if isinstance(body, bytes) else json.dumps(body).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(data)

        def _refuse_foreign(self, post=False):
            """The API is for the page on this machine only: refuse other Host names (DNS
            rebinding), cross-site Origins, and non-JSON POSTs (which a website could send
            without a CORS preflight). Returns True when the request was refused."""
            host = (self.headers.get("Host") or "").rsplit(":", 1)[0]
            origin = self.headers.get("Origin")
            if host not in LOCAL_HOSTS or (origin and urllib.parse.urlsplit(origin).hostname not in LOCAL_HOSTS):
                self._send(403, {"error": "forbidden"})
                return True
            if post and (self.headers.get("Content-Type") or "").split(";")[0].strip() != "application/json":
                self._send(415, {"error": "send application/json"})
                return True
            return False

        def do_GET(self):
            if self._refuse_foreign():
                return
            if self.path in ("/", "/index.html"):
                self._send(200, PAGE_PATH.read_bytes(), "text/html; charset=utf-8")
            elif self.path == "/api/data":
                radar_state = job_tool.load_json(_path("radar.json"), {"postings": {}})
                postings = [dict(p, key=k) for k, p in radar_state["postings"].items()]
                self._send(200, {
                    "updated_at": radar_state.get("updated_at"),
                    "refreshing": runner.running, "refresh_error": runner.last_error,
                    "postings": postings, "page_state": load_page_state(),
                    "coverage": job_tool.load_json(_path("coverage.json"), None),
                })
            elif self.path == "/api/cockpit":
                self._send(200, dict(cockpit.build(), inbox_syncing=inbox_runner.running,
                                     inbox_error=inbox_runner.last_error))
            elif self.path == "/api/status":
                radar_state = job_tool.load_json(_path("radar.json"), {})
                self._send(200, {"updated_at": radar_state.get("updated_at"),
                                 "refreshing": runner.running, "refresh_error": runner.last_error})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
            if self._refuse_foreign(post=True):
                return
            action = actions.get(self.path)
            if action is None:
                self._send(404, {"error": "not found"})
                return
            try:
                length = int(self.headers.get("Content-Length") or 0)
                body = json.loads(self.rfile.read(length) or b"{}")
            except ValueError:
                self._send(400, {"error": "invalid JSON"})
                return
            result, err = action(body)
            self._send(400 if err else 200, {"error": err} if err else result)

    return Handler


def cmd_serve(args):
    runner = Runner(refresh)
    if is_stale(job_tool.load_json(_path("radar.json"), None)):
        runner.start()
        print("Data is older than 12h: refreshing in the background (about 3 minutes).")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(runner, Runner(sync_inbox_from_page)))
    url = f"http://127.0.0.1:{args.port}"
    print(f"Job Radar at {url}  (Ctrl+C to stop)")
    if not args.no_open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass


# ---- CLI ---------------------------------------------------------------------

def summarize(state, coverage):
    open_postings = [p for p in state["postings"].values() if not p["closed"]]
    new_today = [p for p in open_postings if p["first_seen"] == p["last_seen"] == date.today().isoformat()]
    failing = [c["name"] for c in coverage["companies"] if c["ok"] is False]
    li = coverage.get("linkedin") or {}
    print(f"Radar updated {state.get('updated_at')}")
    print(f"  open postings: {len(open_postings)}  (new today: {len(new_today)})")
    print(f"  ≤3 yrs or unknown, tech roles: "
          f"{sum(1 for p in open_postings if (p['years_min'] or 0) <= 3 and p['role_family'] != 'Non-tech')}")
    print(f"  companies checked: {sum(1 for c in coverage['companies'] if c['ok'] is not None)}, "
          f"failing: {len(failing)} {failing[:8]}")
    if li:
        print(f"  linkedin: {li.get('cards')} cards, {li.get('details_fetched')} details, "
              f"{li.get('error_count')} errors")
    print(f"  discovered companies (not on watchlist): {len(coverage.get('discovered') or [])}")


def cmd_refresh(args):
    state, coverage = refresh(use_linkedin=not args.no_linkedin, max_details=args.max_details)
    summarize(state, coverage)


def cmd_daily(args):
    """The 07:00 launchd entry point. Each step's failure is logged without stopping the other;
    ghosting only happens inside a successful inbox sync."""
    try:
        cmd_refresh(args)
    except Exception as e:  # noqa: BLE001 — keep going to the inbox sync
        print(f"radar refresh failed: {e}")
    try:
        print(inbox.format_summary(inbox.run_sync()))
    except Exception as e:  # noqa: BLE001
        print(f"inbox sync failed: {e}")
    snapshot_state(f"daily run {date.today().isoformat()}")


def snapshot_state(message):
    """Commit the state dir (a local git repo since 2026-10-09) so every automatic tracker change
    is reviewable and revertable: `git -C ~/job-search-data log -p tracker.json`. No-op without a
    repo or when nothing changed; never pushes."""
    d = job_tool.state_dir()
    if not (d / ".git").exists():
        return
    subprocess.run(["git", "-C", str(d), "add", "-A"], capture_output=True)
    subprocess.run(["git", "-C", str(d), "commit", "-q", "-m", message], capture_output=True)


def cmd_status(_args):
    state = job_tool.load_json(_path("radar.json"), None)
    coverage = job_tool.load_json(_path("coverage.json"), None)
    if not state or not coverage:
        print("No radar data yet. Run: radar.py refresh")
        return
    summarize(state, coverage)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    p_refresh = sub.add_parser("refresh")
    p_refresh.add_argument("--no-linkedin", action="store_true")
    p_refresh.add_argument("--max-details", type=int, default=LINKEDIN_MAX_DETAILS)
    p_refresh.set_defaults(func=cmd_refresh)
    p_daily = sub.add_parser("daily")
    p_daily.add_argument("--no-linkedin", action="store_true")
    p_daily.add_argument("--max-details", type=int, default=LINKEDIN_MAX_DETAILS)
    p_daily.set_defaults(func=cmd_daily)
    sub.add_parser("status").set_defaults(func=cmd_status)
    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--no-open", action="store_true")
    p_serve.set_defaults(func=cmd_serve)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
