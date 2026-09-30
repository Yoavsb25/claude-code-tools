#!/usr/bin/env python3
"""
Job Radar: collects every London / UK-remote posting from a company watchlist plus a LinkedIn
sweep, enriches each one with fixed rules (years required, level, role family, salary), and
keeps a running radar.json that the Radar page filters and browses. No LLM, no Claude login,
and nothing is ever applied to or sent anywhere.

Usage:
  radar.py refresh [--no-linkedin] [--max-details 100]
  radar.py status
  radar.py serve [--port 8765] [--no-open]   local page at http://127.0.0.1:8765

`serve` refreshes in the background when the data is older than STALE_AFTER_HOURS, so the page
is current even if the Mac was off at 07:00.

State (same dir as job_tool.py: ~/job-search-data, override with JOB_SEARCH_DIR):
  companies.json  - watchlist: [{name, platform, slug, tier}], seeded from profile.json
  radar.json      - {updated_at, postings: {key: posting}}; postings are never deleted,
                    only marked closed after CLOSED_AFTER_DAYS unseen
  coverage.json   - per-company fetch result of the last refresh + LinkedIn stats +
                    companies seen on LinkedIn that aren't on the watchlist yet
  radar_state.json - the page's Hide / Save choices and last visit time
"""

import argparse
import json
import re
import sys
import threading
import time
import urllib.parse
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import job_tool

job_tool.DESCRIPTION_MAX = None  # keep full JD text; "N+ years" often sits near the end
job_tool.DESCRIPTION_KEEP_LINES = True
job_tool.HTTP_TIMEOUT = 45  # full boards with JD text (Databricks, Wayve) take >15s to download

CLOSED_AFTER_DAYS = 3
PRUNE_AFTER_DAYS = 30  # closed postings unseen this long are dropped to keep radar.json small
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

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15,
}
_NUM = r"(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")"
# "3+ years", "3-5 years", "3 to 5 yrs", "at least three years", "minimum of 4 years"
YEARS_RE = re.compile(
    r"\b" + _NUM + r"\s*(?:\+|plus)?\s*(?:(?:-|–|—|to)\s*" + _NUM + r"\s*\+?\s*)?(?:years?|yrs?)\b",
    re.IGNORECASE,
)
# Sentences where "N years" is about the company, not the candidate.
YEARS_NOISE_RE = re.compile(
    r"years?\s+(?:ago|old)|founded|anniversary|in business|of history|history of|"
    r"(?:past|last|next|over the)\s+" + _NUM + r"\s+years?|years? in a row|"
    r"(?:parental|maternity|paternity)|vesting|of service|holiday",
    re.IGNORECASE,
)

LEVEL_RULES = [
    ("intern", r"\bintern(ship)?\b|\bplacement\b"),
    ("entry", r"\bgraduate\b|\bnew grad\b|\bentry[- ]level\b|\bapprentice"),
    ("staff+", r"\bstaff\b|\bprincipal\b|\bdistinguished\b|\barchitect\b"),
    ("manager", r"\bhead of\b|\bdirector\b|\bvp\b|\bvice president\b|\bengineering manager\b|^manager\b"),
    ("senior", r"\bsenior\b|\bsr\.?\b|\blead\b|\biii\b|\biv\b"),
    ("junior", r"\bjunior\b|\bjr\.?\b|\bassociate\b|\b(?:engineer|developer) i\b"),
    ("mid", r"\bmid[- ]?level\b|\bii\b"),
]
LINKEDIN_SENIORITY_LEVELS = {
    "internship": "intern", "entry level": "entry", "associate": "junior",
    "mid-senior level": "mid/senior", "director": "manager", "executive": "manager",
}

# First match on the title wins; order matters (e.g. "AI solutions engineer" -> AI/FDE).
ROLE_FAMILY_RULES = [
    ("Product", r"product manager|product owner|\bpm\b"),
    ("AI/FDE", r"\bai\b|\bllm\b|\bgenai\b|\bgenerative\b|forward[- ]deployed|deployed engineer|\bagents?\b|applied ai"),
    ("Platform/DevEx", r"platform|devops|\bsre\b|reliability|infrastructure|developer experience|devex|"
                       r"developer productivity|internal tools|build|release|cloud engineer|tooling"),
    ("Solutions", r"solutions?|deployment strategist|technical success|customer engineer|sales engineer|implementation|integration engineer|"
                  r"technical account|support engineer|pre-?sales|consultant"),
    ("TPM/Program", r"program(?:me)? (?:manager|management|lead)|project manager|delivery manager|\btpm\b|scrum|chief of staff"),
    ("Security/IT", r"security|\biam\b|\bgrc\b|\bit (?:manager|support|analyst|engineer)|"
                    r"systems analyst|infosec|\bsoc\b|technical writer"),
    ("Data/ML", r"\bdata\b|machine learning|\bml\b|analytics|scientist|research engineer"),
    ("QA/Automation", r"\bqa\b|quality|\btest|\bsdet\b|automation"),
    ("SWE", r"engineer|developer|programmer|swe\b|full[- ]?stack|backend|back-end|frontend|front-end"),
]
NON_TECH_RE = re.compile(
    r"account executive|sales|recruit|talent|legal|counsel|finance|accountant|marketing|"
    r"people partner|\bhr\b|office|executive assistant|payroll|procurement|designer|copywriter|"
    r"business development|partnerships|customer success manager|paralegal|account manager|"
    r"account director|client partner|revenue|fp&a|\btax\b|accounting|store|retail|merchandis|"
    r"\bpeople\b|employee relations|credit|fraud|financial crime|regulatory|\bgtm\b|deal desk|"
    r"renewals|channel|partner director|government relations|policy|workplace|coordinator|"
    r"user research|compliance|administrative|assistant|financial|treasury|controller|"
    r"accounts payable|complaints|claims|handler|collections|customer service|"
    r"customer operations|support specialist|growth|strateg|events|communications|"
    r"knowledge management|creative|artworker|dubbing|translator|linguist|audiobook|"
    r"laboratory|technician|economist|\blaw\b|proposal|paid media|lending|portfolio|onboarding|"
    r"operations (?:associate|executive)|surveillance|summer intern|\bsdr\b|\bbdr\b|"
    r"market operations|general application|general opportunities|register your interest|"
    r"engagement manager|pricing|payments control|floor manager|production manager|"
    r"property|\bpa\b|freelance",
    re.IGNORECASE,
)
DEAL_BREAKER_RE = re.compile(r"\b(?:gambling|betting|casino|sportsbook|igaming|poker)\b", re.IGNORECASE)

# Recruitment agencies post the same roles as the companies, but vaguer ("our client") and often
# duplicated. Flagged, not dropped; the page hides them by default.
RECRUITER_NAME_RE = re.compile(
    r"recruit|staffing|resourcing|talent solutions|hunter bond|client server|albert bow|\bsr2\b|"
    r"anson mccade|signify technology|atarus|la fosse|harnham|oliver bernard|tenth revolution|"
    r"burns sheehan|trust in soda|explore group|nigel frank|jefferson frank|montash|datatech|"
    r"\bsalt\b|lorien|robert walters|\bhays\b|michael page|randstad|harvey nash|venatrix|"
    r"miller maxwell|opus recruitment|understanding recruitment|\bdevelop\b|searchability|"
    r"x4 group|mploy|tec partners|stott and may|piper maddox|forward role",
    re.IGNORECASE,
)
RECRUITER_TEXT_RE = re.compile(r"\bour client\b|on behalf of (?:our|a) client|\bmy client\b", re.IGNORECASE)

SALARY_RE = re.compile(
    r"£\s?(\d{2,3})(?:[,.](\d{3}))?\s?(k)?(?:\s*(?:-|–|—|to)\s*£?\s?(\d{2,3})(?:[,.](\d{3}))?\s?(k)?)?",
    re.IGNORECASE,
)

LONDON_RE = re.compile(r"london", re.IGNORECASE)
UK_REMOTE_RE = re.compile(r"united kingdom|\buk\b|england|emea|europe", re.IGNORECASE)


# ---- enrichment (pure functions) --------------------------------------------

# "5+ years of X is a plus" is not a requirement; don't let it mark a role as too senior.
NICE_TO_HAVE_RE = re.compile(r"\bis a plus\b|nice[- ]to[- ]have|\bbonus\b|\bdesirable\b", re.IGNORECASE)


def _to_int(token):
    token = token.lower()
    return int(token) if token.isdigit() else NUMBER_WORDS.get(token)


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+|•|·", text or "") if s.strip()]


def extract_years(text):
    """Return (min_years, evidence_sentence) for the strictest candidate-experience requirement
    in a JD, or (None, None). Strictest = largest minimum, since the page filters on "too
    senior". Values above 15 are ignored as noise."""
    best, evidence = None, None
    for sentence in _sentences(text):
        if YEARS_NOISE_RE.search(sentence) or NICE_TO_HAVE_RE.search(sentence):
            continue
        for m in YEARS_RE.finditer(sentence):
            low = _to_int(m.group(1))
            if low is None or low == 0 or low > 15:
                continue
            if best is None or low > best:
                best, evidence = low, sentence[:300]
    return best, evidence


def classify_level(title, linkedin_seniority=None):
    t = (title or "").lower()
    for level, pattern in LEVEL_RULES:
        if re.search(pattern, t):
            return level
    if linkedin_seniority:
        return LINKEDIN_SENIORITY_LEVELS.get(linkedin_seniority.strip().lower(), "unknown")
    return "unknown"


def role_family(title):
    t = (title or "").lower()
    if NON_TECH_RE.search(t) and not re.search(
            r"engineer|developer|product manager|\bpm\b|deployment strategist|security|data|\bml\b|\bai\b", t):
        return "Non-tech"
    for family, pattern in ROLE_FAMILY_RULES:
        if re.search(pattern, t):
            return family
    return "Other"


def _salary_value(num, thousands, k_suffix):
    if thousands:
        value = int(num + thousands)
    elif k_suffix:
        value = int(num) * 1000
    else:
        return None  # a bare "£500" is a perk or a fee, not a salary
    return value if 15000 <= value <= 400000 else None


def extract_salary(text):
    """Return (display_string, min_gbp) for the first plausible annual £ figure, else (None, None)."""
    for m in SALARY_RE.finditer(text or ""):
        low = _salary_value(m.group(1), m.group(2), m.group(3) or m.group(6))  # "£85-110k"
        if low is None:
            continue
        high = None
        if m.group(4):
            high = _salary_value(m.group(4), m.group(5), m.group(6) or m.group(3))
        display = f"£{low // 1000}k" + (f"–£{high // 1000}k" if high and high > low else "")
        return display, low
    return None, None


def on_watchlist(company_words, watch_words):
    """Word-prefix match in either direction: "Amazon" matches "Amazon / AWS" and
    "Google UK" matches "Google"."""
    return any(job_tool.company_words_match(w, company_words)
               or job_tool.company_words_match(company_words, w) for w in watch_words)


def is_recruiter(company, description=None):
    return bool(RECRUITER_NAME_RE.search(company or "")
                or RECRUITER_TEXT_RE.search((description or "")[:3000]))


def is_target_location(location, remote=None):
    loc = location or ""
    if LONDON_RE.search(loc):
        return True
    remote_flag = bool(remote) or "remote" in loc.lower()
    return remote_flag and bool(UK_REMOTE_RE.search(loc))


def posting_key(company, title):
    company_words = job_tool.normalize_company(company or "")
    title_words = re.findall(r"[a-z0-9]+", (title or "").lower())
    return " ".join(company_words) + "|" + " ".join(title_words)


def enrich(raw, linkedin_seniority=None):
    description = raw.get("description") or ""
    years, evidence = extract_years(description)
    salary, salary_min = extract_salary(raw.get("salary") or description)
    flags = []
    if DEAL_BREAKER_RE.search(f"{raw.get('company')} {raw.get('title')} {description[:2000]}"):
        flags.append("deal_breaker")
    if is_recruiter(raw.get("company"), description):
        flags.append("recruiter")
    return {
        "company": raw.get("company"),
        "title": raw.get("title"),
        "location": raw.get("location"),
        "url": raw.get("url"),
        "source": raw.get("source"),
        "posted_date": raw.get("posted_date"),
        "years_min": years,
        "years_evidence": evidence,
        "level": classify_level(raw.get("title"), linkedin_seniority),
        "role_family": role_family(raw.get("title")),
        "salary": salary,
        "salary_min": salary_min,
        "flags": flags,
        "description": description[:STORED_DESCRIPTION_CHARS] or None,
    }


# ---- state -------------------------------------------------------------------

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


def reclassify(state):
    """Re-run the rules over stored postings so rule fixes apply to old postings too."""
    for p in state["postings"].values():
        p["role_family"] = role_family(p["title"])
        title_level = classify_level(p["title"])
        if title_level != "unknown":
            p["level"] = title_level
        if p.get("description"):
            p["years_min"], p["years_evidence"] = extract_years(p["description"])
        flags = [f for f in p.get("flags", []) if f != "recruiter"]
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
            results, err = job_tool.fetch_ats_postings(platform, slug)
        elif platform == "workday":
            tenant, wd_host, site = slug.split("/")
            tenant_info = {
                "tenant": tenant, "wd_host": wd_host, "site": site, "company": name,
                "api_base": f"https://{tenant}.{wd_host}.myworkdayjobs.com/wday/cxs/{tenant}/{site}",
                "public_base": f"https://{tenant}.{wd_host}.myworkdayjobs.com/{site}",
            }
            results, err = job_tool.fetch_workday_postings(
                tenant_info, limit=10000, max_scanned=WORKDAY_MAX_SCANNED, location_hint="London")
        elif platform == "comeet":
            token, uid = slug.split(":")
            results, err = job_tool.fetch_comeet_postings(token, uid, name, limit=10000)
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
                job_tool.LINKEDIN_SEARCH_URL + "?" + urllib.parse.urlencode(params))
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
            html, err = job_tool.http_get_html_backoff(f"{job_tool.LINKEDIN_DETAIL_URL}/{card['id']}")
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


def save_posting(key):
    """Add a posting to the tracker as Shortlisted. The only write the page makes outside
    radar_state.json; nothing is applied to or sent."""
    radar_state = job_tool.load_json(_path("radar.json"), {"postings": {}})
    p = radar_state["postings"].get(key)
    if p is None:
        return None, "unknown posting"
    row, err = job_tool.upsert_tracker_row({
        "company": p["company"], "role": p["title"], "link": p["url"], "salary": p.get("salary"),
        "role_family": p.get("role_family"), "source": "radar",
        "notes": f"Saved from Radar ({p.get('years_min') or '?'} yrs, {p.get('level')})",
    })
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


class RefreshRunner:
    """Runs refresh() on a background thread so the page never blocks on a 3-minute fetch."""

    def __init__(self):
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
            refresh()
            self.last_error = None
        except Exception as e:  # surfaced on the page instead of killing the server
            self.last_error = str(e)
        finally:
            with self.lock:
                self.running = False


def make_handler(runner):
    actions = {
        "/api/hide": lambda body: hide_posting(body.get("key"), body.get("reason")),
        "/api/unhide": lambda body: unhide_posting(body.get("key")),
        "/api/save": lambda body: save_posting(body.get("key")),
        "/api/visit": lambda body: record_visit(),
        "/api/refresh": lambda body: ({"started": runner.start()}, None),
        "/api/watchlist": lambda body: add_to_watchlist(body.get("company")),
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

        def do_GET(self):
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
            elif self.path == "/api/status":
                radar_state = job_tool.load_json(_path("radar.json"), {})
                self._send(200, {"updated_at": radar_state.get("updated_at"),
                                 "refreshing": runner.running, "refresh_error": runner.last_error})
            else:
                self._send(404, {"error": "not found"})

        def do_POST(self):
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
    runner = RefreshRunner()
    if is_stale(job_tool.load_json(_path("radar.json"), None)):
        runner.start()
        print("Data is older than 12h: refreshing in the background (about 3 minutes).")
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(runner))
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
    sub.add_parser("status").set_defaults(func=cmd_status)
    p_serve = sub.add_parser("serve")
    p_serve.add_argument("--port", type=int, default=8765)
    p_serve.add_argument("--no-open", action="store_true")
    p_serve.set_defaults(func=cmd_serve)
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    sys.exit(main())
