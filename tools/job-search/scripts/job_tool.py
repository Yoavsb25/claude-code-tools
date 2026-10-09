#!/usr/bin/env python3
"""Job-search bookkeeping CLI: profile, tracker, network, and board search.

JSON under ~/job-search-data is the source of truth. Implementation lives in the
jobsearch package; this module re-exports names for callers/tests and owns argparse.
"""

import argparse
import json
import os
import sys
import time
import urllib.parse
import urllib.request
from datetime import date, timedelta
from pathlib import Path

from jobsearch.fetchconfig import DEFAULT as DEFAULT_FETCH, FetchConfig, RADAR as RADAR_FETCH
from jobsearch import store as _store
from jobsearch import text as _text
from jobsearch import tracker as _tracker
from jobsearch import profile as _profile
from jobsearch import network as _network
from jobsearch import http as _http
from jobsearch.sources import common as _common
from jobsearch.sources import ats as _ats
from jobsearch.sources import workday as _workday
from jobsearch.sources import comeet as _comeet
from jobsearch.sources import linkedin as _linkedin
from jobsearch.sources import boards as _boards

# ---- store / text -----------------------------------------------------------
state_dir = _store.state_dir
load_json = _store.load_json
save_json = _store.save_json
read_json_arg = _store.read_json_arg
today_str = _store.today_str
parse_date = _store.parse_date

strip_html = _text.strip_html
decode_html_entities = _text.decode_html_entities
clean_text = _text.clean_text
_strip_tags_keep_newlines = _text._strip_tags_keep_newlines
normalize_company = _text.normalize_company
company_words_match = _text.company_words_match
LINKEDIN_BR_RE = _text.LINKEDIN_BR_RE
LINKEDIN_BLOCK_CLOSE_RE = _text.LINKEDIN_BLOCK_CLOSE_RE
ATS_SLUG_SUFFIXES = _text.ATS_SLUG_SUFFIXES

HTTP_TIMEOUT = DEFAULT_FETCH.timeout
DESCRIPTION_MAX = DEFAULT_FETCH.description_max
DESCRIPTION_KEEP_LINES = DEFAULT_FETCH.keep_lines
USER_AGENT = _http.USER_AGENT
APIFY_TIMEOUT = _http.APIFY_TIMEOUT
LINKEDIN_USER_AGENT = _http.LINKEDIN_USER_AGENT
LINKEDIN_MAX_RETRIES = _http.LINKEDIN_MAX_RETRIES
LINKEDIN_BACKOFF_BASE_MS = _http.LINKEDIN_BACKOFF_BASE_MS
LINKEDIN_BACKOFF_CAP_MS = _http.LINKEDIN_BACKOFF_CAP_MS

http_get_html_backoff = _http.http_get_html_backoff
http_get_json = _http.http_get_json
http_post_json = _http.http_post_json
http_get_html = _http.http_get_html

posting = _common.posting
description_text = _common.description_text
print_search_result = _common.print_search_result
print_detail_result = _common.print_detail_result

# ---- profile / tracker / network -------------------------------------------
STATUS_ORDER = _tracker.STATUS_ORDER
FOLLOWUP_STATUSES = _tracker.FOLLOWUP_STATUSES
CHANNELS = _tracker.CHANNELS
POSITIONINGS = _tracker.POSITIONINGS
TIERS = _tracker.TIERS
GHOST_AFTER_DAYS = _tracker.GHOST_AFTER_DAYS
SHORTLIST_STALE_DAYS = _tracker.SHORTLIST_STALE_DAYS
DEFAULT_FOLLOWUP_DAYS = _tracker.DEFAULT_FOLLOWUP_DAYS
INTERVIEW_FOLLOWUP_DAYS = _tracker.INTERVIEW_FOLLOWUP_DAYS
TRACKER_COLUMNS = _tracker.TRACKER_COLUMNS
CHANNEL_RULES = _tracker.CHANNEL_RULES
POSITIONING_RULES = _tracker.POSITIONING_RULES
REJECTION_DATE_RE = _tracker.REJECTION_DATE_RE

profile_path = _profile.profile_path
cmd_profile_show = _profile.cmd_profile_show
cmd_profile_set = _profile.cmd_profile_set

tracker_path = _tracker.tracker_path
markdown_path = _tracker.markdown_path
load_rows = _tracker.load_rows
save_rows = _tracker.save_rows
next_followup = _tracker.next_followup
compute_stale_reason = _tracker.compute_stale_reason
cmd_tracker_upsert = _tracker.cmd_tracker_upsert
validate_tracker_patch = _tracker.validate_tracker_patch
upsert_tracker_row = _tracker.upsert_tracker_row
undo_last_status = _tracker.undo_last_status
mark_ghosted = _tracker.mark_ghosted
infer_channel = _tracker.infer_channel
infer_positioning = _tracker.infer_positioning
backfill_events = _tracker.backfill_events
migrate_tracker = _tracker.migrate_tracker
cmd_tracker_migrate = _tracker.cmd_tracker_migrate
cmd_tracker_undo = _tracker.cmd_tracker_undo
cmd_tracker_list = _tracker.cmd_tracker_list
render_markdown = _tracker.render_markdown
cmd_tracker_render = _tracker.cmd_tracker_render

connections_path = _network.connections_path
load_connections = _network.load_connections
save_connections = _network.save_connections
parse_linkedin_connections_csv = _network.parse_linkedin_connections_csv
connection_key = _network.connection_key
cmd_network_import = _network.cmd_network_import
cmd_network_list = _network.cmd_network_list
cmd_network_match = _network.cmd_network_match
cmd_network_companies = _network.cmd_network_companies

# ---- sources ----------------------------------------------------------------
ATS_ENDPOINTS = _ats.ATS_ENDPOINTS
ATS_PROBE_ORDER = _ats.ATS_PROBE_ORDER
parse_ats_payload = _ats.parse_ats_payload
greenhouse_location = _ats.greenhouse_location
workable_location = _ats.workable_location
fetch_ats_postings = _ats.fetch_ats_postings
cmd_search_ats = _ats.cmd_search_ats
candidate_slugs = _ats.candidate_slugs
cmd_search_discover_ats = _ats.cmd_search_discover_ats
discover_ats = _ats.discover_ats

LINKEDIN_SEARCH_URL = _linkedin.LINKEDIN_SEARCH_URL
LINKEDIN_DETAIL_URL = _linkedin.LINKEDIN_DETAIL_URL
jobage_to_tpr = _linkedin.jobage_to_tpr
linkedin_work_type_flag = _linkedin.linkedin_work_type_flag
normalize_linkedin_job_id = _linkedin.normalize_linkedin_job_id
parse_linkedin_cards = _linkedin.parse_linkedin_cards
parse_linkedin_detail = _linkedin.parse_linkedin_detail
cmd_search_linkedin = _linkedin.cmd_search_linkedin
cmd_search_linkedin_detail = _linkedin.cmd_search_linkedin_detail

APIFY_API_BASE = _workday.APIFY_API_BASE
APIFY_DEFAULT_WORKDAY_ACTOR = _workday.APIFY_DEFAULT_WORKDAY_ACTOR
WORKDAY_URL_RE = _workday.WORKDAY_URL_RE
WORKDAY_LOCALE_RE = _workday.WORKDAY_LOCALE_RE
WORKDAY_PAGE_SIZE = _workday.WORKDAY_PAGE_SIZE
WORKDAY_MAX_JOBS_SCANNED = _workday.WORKDAY_MAX_JOBS_SCANNED
WORKDAY_DETAIL_WORKERS = _workday.WORKDAY_DETAIL_WORKERS
cmd_search_workday = _workday.cmd_search_workday
detect_workday_tenant = _workday.detect_workday_tenant
is_remote_location = _workday.is_remote_location
find_facet_values = _workday.find_facet_values
resolve_facet_ids = _workday.resolve_facet_ids
fetch_workday_facets = _workday.fetch_workday_facets
fetch_workday_postings = _workday.fetch_workday_postings
cmd_search_discover_workday = _workday.cmd_search_discover_workday
cmd_search_workday_jobs = _workday.cmd_search_workday_jobs

COMEET_TOKEN_RE = _comeet.COMEET_TOKEN_RE
COMEET_COMPANY_UID_RE = _comeet.COMEET_COMPANY_UID_RE
COMEET_POSITIONS_URL = _comeet.COMEET_POSITIONS_URL
detect_comeet_config = _comeet.detect_comeet_config
fetch_comeet_postings = _comeet.fetch_comeet_postings
cmd_search_discover_comeet = _comeet.cmd_search_discover_comeet
cmd_search_comeet_jobs = _comeet.cmd_search_comeet_jobs

APIFY_DEFAULT_JOBS_INDEX_ACTOR = _boards.APIFY_DEFAULT_JOBS_INDEX_ACTOR
JOBS_INDEX_DEFAULT_LIMIT = _boards.JOBS_INDEX_DEFAULT_LIMIT
JOBS_INDEX_DEFAULT_TIME_RANGE = _boards.JOBS_INDEX_DEFAULT_TIME_RANGE
REMOTIVE_URL = _boards.REMOTIVE_URL
ARBEITNOW_URL = _boards.ARBEITNOW_URL
cmd_search_remotive = _boards.cmd_search_remotive
cmd_search_arbeitnow = _boards.cmd_search_arbeitnow
_format_jobs_index_salary = _boards._format_jobs_index_salary
cmd_search_jobs_index = _boards.cmd_search_jobs_index

def main():
    import argparse

    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="group", required=True)

    p_profile = sub.add_parser("profile")
    profile_sub = p_profile.add_subparsers(dest="action", required=True)
    profile_sub.add_parser("show").set_defaults(func=cmd_profile_show)
    p_set = profile_sub.add_parser("set")
    p_set.add_argument("patch")
    p_set.set_defaults(func=cmd_profile_set)

    p_tracker = sub.add_parser("tracker")
    tracker_sub = p_tracker.add_subparsers(dest="action", required=True)
    p_list = tracker_sub.add_parser("list")
    p_list.add_argument("--status")
    p_list.add_argument("--stale-only", action="store_true")
    p_list.set_defaults(func=cmd_tracker_list)
    p_upsert = tracker_sub.add_parser("upsert")
    p_upsert.add_argument("row")
    p_upsert.set_defaults(func=cmd_tracker_upsert)
    tracker_sub.add_parser("render").set_defaults(func=cmd_tracker_render)
    tracker_sub.add_parser("migrate").set_defaults(func=cmd_tracker_migrate)
    p_undo = tracker_sub.add_parser("undo")
    p_undo.add_argument("--id", type=int, required=True)
    p_undo.set_defaults(func=cmd_tracker_undo)

    p_network = sub.add_parser("network")
    network_sub = p_network.add_subparsers(dest="action", required=True)

    p_net_import = network_sub.add_parser("import")
    p_net_import.add_argument("--csv", required=True, help="Path to LinkedIn's exported Connections.csv")
    p_net_import.set_defaults(func=cmd_network_import)

    p_net_list = network_sub.add_parser("list")
    p_net_list.add_argument("--company", help="Filter to connections at this company (normalized whole-word match)")
    p_net_list.set_defaults(func=cmd_network_list)

    p_net_match = network_sub.add_parser("match")
    p_net_match.add_argument("--company", help="Check one company ad hoc instead of iterating profile's target_companies")
    p_net_match.set_defaults(func=cmd_network_match)

    p_net_companies = network_sub.add_parser("companies")
    p_net_companies.set_defaults(func=cmd_network_companies)

    p_search = sub.add_parser("search")
    search_sub = p_search.add_subparsers(dest="action", required=True)

    p_remotive = search_sub.add_parser("remotive")
    p_remotive.add_argument("--query")
    p_remotive.add_argument("--category")
    p_remotive.add_argument("--limit", type=int, default=25)
    p_remotive.set_defaults(func=cmd_search_remotive)

    p_arbeitnow = search_sub.add_parser("arbeitnow")
    p_arbeitnow.add_argument("--query")
    p_arbeitnow.add_argument("--limit", type=int, default=25)
    p_arbeitnow.add_argument("--max-pages", type=int, default=3)
    p_arbeitnow.set_defaults(func=cmd_search_arbeitnow)

    p_ats = search_sub.add_parser("ats")
    p_ats.add_argument("--platform", required=True, choices=list(ATS_ENDPOINTS))
    p_ats.add_argument("--company", required=True)
    p_ats.add_argument("--query")
    p_ats.add_argument("--limit", type=int, default=25)
    p_ats.set_defaults(func=cmd_search_ats)

    p_discover = search_sub.add_parser("discover-ats")
    p_discover.add_argument("--company", required=True)
    p_discover.add_argument("--slug-hint", dest="slug_hint", help="A likely slug to try first, e.g. parsed from a pasted URL fragment")
    p_discover.add_argument("--platforms", help="Comma-separated subset to probe (default: all supported ATS platforms)")
    p_discover.add_argument("--query")
    p_discover.add_argument("--limit", type=int, default=25)
    p_discover.set_defaults(func=cmd_search_discover_ats)

    p_linkedin = search_sub.add_parser("linkedin")
    p_linkedin.add_argument("--query")
    p_linkedin.add_argument("--location", required=True)
    p_linkedin.add_argument("--jobage", type=int)
    p_linkedin.add_argument("--remote", choices=["remote", "hybrid", "onsite"])
    p_linkedin.add_argument("--page", type=int, default=1)
    p_linkedin.add_argument("--limit", type=int, default=25)
    p_linkedin.set_defaults(func=cmd_search_linkedin)

    p_linkedin_detail = search_sub.add_parser("linkedin-detail")
    p_linkedin_detail.add_argument("--id", required=True)
    p_linkedin_detail.set_defaults(func=cmd_search_linkedin_detail)

    p_workday = search_sub.add_parser("workday")
    p_workday.add_argument("--url", required=True, help="Company's myworkdayjobs.com career-site URL")
    p_workday.add_argument("--query")
    p_workday.add_argument("--location")
    p_workday.add_argument("--limit", type=int, default=25)
    p_workday.set_defaults(func=cmd_search_workday)

    p_jobs_index = search_sub.add_parser("jobs-index")
    p_jobs_index.add_argument("--company", help="Organization name to search for (exact-ish phrase match)")
    p_jobs_index.add_argument("--domain", help="Company domain to search for (exact match, e.g. 'acme.com')")
    p_jobs_index.add_argument("--query", help="Job title to search for")
    p_jobs_index.add_argument(
        "--location",
        help="'City, State/Region, Country' format, e.g. 'London, England, United Kingdom' "
             "(English names only, no abbreviations -- see README for the exact convention)",
    )
    p_jobs_index.add_argument("--ats", help="Comma-separated ATS platform filter, e.g. 'workday,oraclecloud,comeet'")
    p_jobs_index.add_argument("--work-arrangement", dest="work_arrangement", choices=["On-site", "Hybrid", "Remote OK", "Remote Solely"])
    p_jobs_index.add_argument(
        "--time-range", dest="time_range", default=JOBS_INDEX_DEFAULT_TIME_RANGE,
        choices=["1h", "24h", "7d", "6m"],
        help="'6m' (default) = every currently active posting, for a per-company full-board pull. "
             "Use '24h'/'7d' instead for a market-wide freshness scan.",
    )
    p_jobs_index.add_argument("--limit", type=int, default=JOBS_INDEX_DEFAULT_LIMIT)
    p_jobs_index.set_defaults(func=cmd_search_jobs_index)

    p_discover_workday = search_sub.add_parser("discover-workday")
    p_discover_workday.add_argument(
        "--url", required=True,
        help="A company's career-page URL (its HTML will be scanned for a myworkdayjobs.com link), "
             "or a myworkdayjobs.com URL directly if already known",
    )
    p_discover_workday.add_argument("--company", help="Company name, echoed back in the output for bookkeeping")
    p_discover_workday.add_argument("--query")
    p_discover_workday.add_argument(
        "--location-hint", dest="location_hint",
        help="Location name to filter to server-side via Workday's own location facet (exact "
             "match against that tenant's facet descriptors, e.g. 'United Kingdom'). A name with "
             "no matching facet for this tenant is silently skipped, not an error.",
    )
    p_discover_workday.add_argument(
        "--job-family-groups", dest="job_family_groups",
        help="Comma-separated category names to filter to server-side via Workday's Job Category "
             "facet (e.g. 'Engineering,Research'), matched case-insensitively against that "
             "tenant's actual facet descriptors. A name with no match for this tenant is silently "
             "skipped, not an error.",
    )
    p_discover_workday.add_argument("--limit", type=int, default=25)
    p_discover_workday.set_defaults(func=cmd_search_discover_workday)

    p_workday_jobs = search_sub.add_parser("workday-jobs")
    p_workday_jobs.add_argument(
        "--slug", required=True,
        help="'<tenant>/<wd_host>/<site>' as returned by a prior discover-workday call's detected_slug "
             "(e.g. 'unitytech/wd1/Unity') -- skips the career-page fetch and goes straight to the API",
    )
    p_workday_jobs.add_argument("--company", help="Company name, echoed back in the output for bookkeeping")
    p_workday_jobs.add_argument("--query")
    p_workday_jobs.add_argument(
        "--location-hint", dest="location_hint",
        help="Location name to filter to server-side via Workday's own location facet (exact "
             "match against that tenant's facet descriptors, e.g. 'United Kingdom'). A name with "
             "no matching facet for this tenant is silently skipped, not an error.",
    )
    p_workday_jobs.add_argument(
        "--job-family-groups", dest="job_family_groups",
        help="Comma-separated category names to filter to server-side via Workday's Job Category "
             "facet (e.g. 'Engineering,Research'), matched case-insensitively against that "
             "tenant's actual facet descriptors. A name with no match for this tenant is silently "
             "skipped, not an error.",
    )
    p_workday_jobs.add_argument("--limit", type=int, default=25)
    p_workday_jobs.set_defaults(func=cmd_search_workday_jobs)

    p_discover_comeet = search_sub.add_parser("discover-comeet")
    p_discover_comeet.add_argument(
        "--url", required=True,
        help="A company's career-page URL -- its HTML will be scanned for an inline COMEET.init(...) "
             "call to extract the public token + company-uid",
    )
    p_discover_comeet.add_argument("--company", help="Company name, echoed back in the output for bookkeeping")
    p_discover_comeet.add_argument("--query")
    p_discover_comeet.add_argument("--limit", type=int, default=25)
    p_discover_comeet.set_defaults(func=cmd_search_discover_comeet)

    p_comeet_jobs = search_sub.add_parser("comeet-jobs")
    p_comeet_jobs.add_argument(
        "--slug", required=True,
        help="'<token>:<company_uid>' as returned by a prior discover-comeet call's detected_slug "
             "-- skips the career-page fetch and goes straight to the API",
    )
    p_comeet_jobs.add_argument("--company", help="Company name, echoed back in the output for bookkeeping")
    p_comeet_jobs.add_argument("--query")
    p_comeet_jobs.add_argument("--limit", type=int, default=25)
    p_comeet_jobs.set_defaults(func=cmd_search_comeet_jobs)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
