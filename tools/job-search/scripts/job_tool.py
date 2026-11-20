#!/usr/bin/env python3
"""Job-search bookkeeping CLI: profile, tracker, network, and board search.

JSON under ~/job-search-data is the source of truth. Implementation lives in the
jobsearch package; this module is only the argparse front end.
"""

import argparse

from jobsearch import tracker as _tracker
from jobsearch import profile as _profile
from jobsearch import network as _network
from jobsearch.sources import ats as _ats
from jobsearch.sources import workday as _workday
from jobsearch.sources import comeet as _comeet
from jobsearch.sources import linkedin as _linkedin
from jobsearch.sources import boards as _boards


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="group", required=True)

    p_profile = sub.add_parser("profile")
    profile_sub = p_profile.add_subparsers(dest="action", required=True)
    profile_sub.add_parser("show").set_defaults(func=_profile.cmd_profile_show)
    p_set = profile_sub.add_parser("set")
    p_set.add_argument("patch")
    p_set.set_defaults(func=_profile.cmd_profile_set)

    p_tracker = sub.add_parser("tracker")
    tracker_sub = p_tracker.add_subparsers(dest="action", required=True)
    p_list = tracker_sub.add_parser("list")
    p_list.add_argument("--status")
    p_list.add_argument("--stale-only", action="store_true")
    p_list.set_defaults(func=_tracker.cmd_tracker_list)
    p_upsert = tracker_sub.add_parser("upsert")
    p_upsert.add_argument("row")
    p_upsert.set_defaults(func=_tracker.cmd_tracker_upsert)
    tracker_sub.add_parser("render").set_defaults(func=_tracker.cmd_tracker_render)
    tracker_sub.add_parser("migrate").set_defaults(func=_tracker.cmd_tracker_migrate)
    p_undo = tracker_sub.add_parser("undo")
    p_undo.add_argument("--id", type=int, required=True)
    p_undo.set_defaults(func=_tracker.cmd_tracker_undo)

    p_network = sub.add_parser("network")
    network_sub = p_network.add_subparsers(dest="action", required=True)

    p_net_import = network_sub.add_parser("import")
    p_net_import.add_argument("--csv", required=True, help="Path to LinkedIn's exported Connections.csv")
    p_net_import.set_defaults(func=_network.cmd_network_import)

    p_net_list = network_sub.add_parser("list")
    p_net_list.add_argument("--company", help="Filter to connections at this company (normalized whole-word match)")
    p_net_list.set_defaults(func=_network.cmd_network_list)

    p_net_match = network_sub.add_parser("match")
    p_net_match.add_argument("--company", help="Check one company ad hoc instead of iterating profile's target_companies")
    p_net_match.set_defaults(func=_network.cmd_network_match)

    p_net_companies = network_sub.add_parser("companies")
    p_net_companies.set_defaults(func=_network.cmd_network_companies)

    p_search = sub.add_parser("search")
    search_sub = p_search.add_subparsers(dest="action", required=True)

    p_remotive = search_sub.add_parser("remotive")
    p_remotive.add_argument("--query")
    p_remotive.add_argument("--category")
    p_remotive.add_argument("--limit", type=int, default=25)
    p_remotive.set_defaults(func=_boards.cmd_search_remotive)

    p_arbeitnow = search_sub.add_parser("arbeitnow")
    p_arbeitnow.add_argument("--query")
    p_arbeitnow.add_argument("--limit", type=int, default=25)
    p_arbeitnow.add_argument("--max-pages", type=int, default=3)
    p_arbeitnow.set_defaults(func=_boards.cmd_search_arbeitnow)

    p_ats = search_sub.add_parser("ats")
    p_ats.add_argument("--platform", required=True, choices=list(_ats.ATS_ENDPOINTS))
    p_ats.add_argument("--company", required=True)
    p_ats.add_argument("--query")
    p_ats.add_argument("--limit", type=int, default=25)
    p_ats.set_defaults(func=_ats.cmd_search_ats)

    p_discover = search_sub.add_parser("discover-ats")
    p_discover.add_argument("--company", required=True)
    p_discover.add_argument("--slug-hint", dest="slug_hint", help="A likely slug to try first, e.g. parsed from a pasted URL fragment")
    p_discover.add_argument("--platforms", help="Comma-separated subset to probe (default: all supported ATS platforms)")
    p_discover.add_argument("--query")
    p_discover.add_argument("--limit", type=int, default=25)
    p_discover.set_defaults(func=_ats.cmd_search_discover_ats)

    p_linkedin = search_sub.add_parser("linkedin")
    p_linkedin.add_argument("--query")
    p_linkedin.add_argument("--location", required=True)
    p_linkedin.add_argument("--jobage", type=int)
    p_linkedin.add_argument("--remote", choices=["remote", "hybrid", "onsite"])
    p_linkedin.add_argument("--page", type=int, default=1)
    p_linkedin.add_argument("--limit", type=int, default=25)
    p_linkedin.set_defaults(func=_linkedin.cmd_search_linkedin)

    p_linkedin_detail = search_sub.add_parser("linkedin-detail")
    p_linkedin_detail.add_argument("--id", required=True)
    p_linkedin_detail.set_defaults(func=_linkedin.cmd_search_linkedin_detail)

    p_workday = search_sub.add_parser("workday")
    p_workday.add_argument("--url", required=True, help="Company's myworkdayjobs.com career-site URL")
    p_workday.add_argument("--query")
    p_workday.add_argument("--location")
    p_workday.add_argument("--limit", type=int, default=25)
    p_workday.set_defaults(func=_workday.cmd_search_workday)

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
        "--time-range", dest="time_range", default=_boards.JOBS_INDEX_DEFAULT_TIME_RANGE,
        choices=["1h", "24h", "7d", "6m"],
        help="'6m' (default) = every currently active _common.posting, for a per-company full-board pull. "
             "Use '24h'/'7d' instead for a market-wide freshness scan.",
    )
    p_jobs_index.add_argument("--limit", type=int, default=_boards.JOBS_INDEX_DEFAULT_LIMIT)
    p_jobs_index.set_defaults(func=_boards.cmd_search_jobs_index)

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
    p_discover_workday.set_defaults(func=_workday.cmd_search_discover_workday)

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
    p_workday_jobs.set_defaults(func=_workday.cmd_search_workday_jobs)

    p_discover_comeet = search_sub.add_parser("discover-comeet")
    p_discover_comeet.add_argument(
        "--url", required=True,
        help="A company's career-page URL -- its HTML will be scanned for an inline COMEET.init(...) "
             "call to extract the public token + company-uid",
    )
    p_discover_comeet.add_argument("--company", help="Company name, echoed back in the output for bookkeeping")
    p_discover_comeet.add_argument("--query")
    p_discover_comeet.add_argument("--limit", type=int, default=25)
    p_discover_comeet.set_defaults(func=_comeet.cmd_search_discover_comeet)

    p_comeet_jobs = search_sub.add_parser("comeet-jobs")
    p_comeet_jobs.add_argument(
        "--slug", required=True,
        help="'<token>:<company_uid>' as returned by a prior discover-comeet call's detected_slug "
             "-- skips the career-page fetch and goes straight to the API",
    )
    p_comeet_jobs.add_argument("--company", help="Company name, echoed back in the output for bookkeeping")
    p_comeet_jobs.add_argument("--query")
    p_comeet_jobs.add_argument("--limit", type=int, default=25)
    p_comeet_jobs.set_defaults(func=_comeet.cmd_search_comeet_jobs)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
