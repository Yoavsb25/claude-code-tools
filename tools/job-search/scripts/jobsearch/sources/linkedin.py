"""LinkedIn guest job search and detail parsing."""

import re
import urllib.parse

from jobsearch.http import http_get_html_backoff
from jobsearch.sources.common import posting, print_detail_result, print_search_result
from jobsearch.text import (
    LINKEDIN_BLOCK_CLOSE_RE, LINKEDIN_BR_RE, _strip_tags_keep_newlines,
    clean_text, decode_html_entities,
)

LINKEDIN_SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
LINKEDIN_DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting"

def jobage_to_tpr(days):
    if not days or days <= 0 or days >= 9999:
        return None
    return f"r{days * 86400}"


def linkedin_work_type_flag(mode):
    return {"remote": "2", "hybrid": "3", "onsite": "1"}.get((mode or "").lower())


def normalize_linkedin_job_id(value):
    if not value:
        return None
    urn_match = re.search(r"urn:li:jobPosting:(\d+)", value)
    if urn_match:
        return urn_match.group(1)
    url_match = re.search(r"-(\d{6,})(?:\?|$)", value) or re.search(r"/(\d{6,})(?:\?|$)", value)
    if url_match:
        return url_match.group(1)
    if re.fullmatch(r"\d{6,}", value):
        return value
    return None

LINKEDIN_CARD_SPLIT_RE = re.compile(r'data-entity-urn="urn:li:jobPosting:')
LINKEDIN_ID_PREFIX_RE = re.compile(r"^(\d+)")
LINKEDIN_FULL_LINK_RE = re.compile(r'class="base-card__full-link[^"]*"[^>]*href="([^"]+)"', re.IGNORECASE)
LINKEDIN_TITLE_H3_RE = re.compile(r'class="base-search-card__title"[^>]*>([\s\S]*?)</h3>', re.IGNORECASE)
LINKEDIN_TITLE_SR_RE = re.compile(r'class="sr-only"[^>]*>([\s\S]*?)</span>', re.IGNORECASE)
LINKEDIN_SUBTITLE_RE = re.compile(r'class="base-search-card__subtitle"[^>]*>([\s\S]*?)</h4>', re.IGNORECASE)
LINKEDIN_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
LINKEDIN_LOCATION_RE = re.compile(r'class="job-search-card__location"[^>]*>([\s\S]*?)</span>', re.IGNORECASE)
LINKEDIN_LISTDATE_RE = re.compile(
    r'class="job-search-card__listdate[^"]*"[^>]*datetime="([^"]+)"', re.IGNORECASE
)


def parse_linkedin_cards(html):
    results = []
    chunks = LINKEDIN_CARD_SPLIT_RE.split(html)[1:]

    for chunk in chunks:
        id_match = LINKEDIN_ID_PREFIX_RE.match(chunk)
        if not id_match:
            continue
        job_id = id_match.group(1)

        link_match = LINKEDIN_FULL_LINK_RE.search(chunk)
        url = decode_html_entities(link_match.group(1)).split("?")[0] if link_match else ""

        title = None
        h3_match = LINKEDIN_TITLE_H3_RE.search(chunk)
        if h3_match:
            title = clean_text(h3_match.group(1)) or None
        if not title:
            sr_match = LINKEDIN_TITLE_SR_RE.search(chunk)
            if sr_match:
                title = clean_text(sr_match.group(1)) or None
        if not title:
            continue

        company = None
        sub_match = LINKEDIN_SUBTITLE_RE.search(chunk)
        if sub_match:
            company_link = LINKEDIN_HREF_RE.search(sub_match.group(1))
            company_url = (
                decode_html_entities(company_link.group(1)).split("?")[0] if company_link else None
            )
            company = clean_text(sub_match.group(1)) or None
        else:
            company_url = None

        loc_match = LINKEDIN_LOCATION_RE.search(chunk)
        location = clean_text(loc_match.group(1)) if loc_match else None
        location = location or None

        date_match = LINKEDIN_LISTDATE_RE.search(chunk)
        posted_date = date_match.group(1) if date_match else None

        results.append({
            "id": job_id,
            "title": title,
            "company": company,
            "company_url": company_url,
            "location": location,
            "posted_date": posted_date,
            "url": url or f"https://www.linkedin.com/jobs/view/{job_id}",
        })

    return results


LINKEDIN_TOPCARD_TITLE_RE = re.compile(
    r'class="(?:top-card-layout__title|topcard__title)[^"]*"[^>]*>([\s\S]*?)</h[12]>', re.IGNORECASE
)
LINKEDIN_ORG_RE = re.compile(
    r'class="topcard__org-name-link[^"]*"[^>]*href="([^"]+)"[^>]*>([\s\S]*?)</a>', re.IGNORECASE
)
LINKEDIN_LOC_DETAIL_RE = re.compile(
    r'class="topcard__flavor topcard__flavor--bullet"[^>]*>([\s\S]*?)</span>', re.IGNORECASE
)
LINKEDIN_DESC_RE = re.compile(
    r'class="(?:show-more-less-html__markup|description__text[^"]*)"[^>]*>([\s\S]*?)</div>',
    re.IGNORECASE,
)
LINKEDIN_CRITERIA_RE = re.compile(
    r'class="description__job-criteria-subheader"[^>]*>([\s\S]*?)</h3>[\s\S]*?'
    r'class="description__job-criteria-text[^"]*"[^>]*>([\s\S]*?)</span>',
    re.IGNORECASE,
)
LINKEDIN_APPLY_RE = re.compile(r'class="topcard__link[^"]*"[^>]*href="([^"]+)"', re.IGNORECASE)


def parse_linkedin_detail(html, job_id):
    title_match = LINKEDIN_TOPCARD_TITLE_RE.search(html)
    title = clean_text(title_match.group(1)) if title_match else None

    org_match = LINKEDIN_ORG_RE.search(html)
    company = clean_text(org_match.group(2)) or None if org_match else None
    company_url = decode_html_entities(org_match.group(1)).split("?")[0] if org_match else None

    loc_match = LINKEDIN_LOC_DETAIL_RE.search(html)
    location = (clean_text(loc_match.group(1)) or None) if loc_match else None

    description = None
    desc_match = LINKEDIN_DESC_RE.search(html)
    if desc_match:
        with_breaks = LINKEDIN_BR_RE.sub("\n", desc_match.group(1))
        with_breaks = LINKEDIN_BLOCK_CLOSE_RE.sub("\n", with_breaks)
        text = decode_html_entities(_strip_tags_keep_newlines(with_breaks))
        text = re.sub(r"\n{3,}", "\n\n", text).strip()
        description = text or None

    criteria = {}
    for match in LINKEDIN_CRITERIA_RE.finditer(html):
        key = clean_text(match.group(1)).lower()
        criteria[key] = clean_text(match.group(2))

    apply_match = LINKEDIN_APPLY_RE.search(html)
    apply_url = decode_html_entities(apply_match.group(1)).split("?")[0] if apply_match else None

    return {
        "id": job_id,
        "title": title or "(untitled)",
        "company": company,
        "company_url": company_url,
        "location": location,
        "url": f"https://www.linkedin.com/jobs/view/{job_id}",
        "description": description,
        "seniority": criteria.get("seniority level"),
        "employment_type": criteria.get("employment type"),
        "job_function": criteria.get("job function"),
        "industries": criteria.get("industries"),
        "apply_url": apply_url,
    }

def cmd_search_linkedin(args):
    params = {"location": args.location}
    if args.query:
        params["keywords"] = args.query
    tpr = jobage_to_tpr(args.jobage)
    if tpr:
        params["f_TPR"] = tpr
    work_type = linkedin_work_type_flag(args.remote)
    if work_type:
        params["f_WT"] = work_type
    params["start"] = str((args.page - 1) * 10)

    url = LINKEDIN_SEARCH_URL + "?" + urllib.parse.urlencode(params)
    html, err = http_get_html_backoff(url)
    if err:
        print_search_result("linkedin", [], err)
        return

    cards = parse_linkedin_cards(html)[: args.limit]
    results = [
        posting(
            "linkedin", card["title"], card["company"], card["location"], None,
            card["url"], [], None, card["posted_date"], None,
        )
        for card in cards
    ]
    print_search_result("linkedin", results, None)


def cmd_search_linkedin_detail(args):
    job_id = normalize_linkedin_job_id(args.id)
    if not job_id:
        print_detail_result("linkedin", None, f"could not parse a job id from '{args.id}'")
        return

    html, err = http_get_html_backoff(f"{LINKEDIN_DETAIL_URL}/{job_id}")
    if err:
        print_detail_result("linkedin", None, err)
        return
    if not html:
        print_detail_result("linkedin", None, "job not found")
        return

    detail = parse_linkedin_detail(html, job_id)
    print_detail_result("linkedin", detail, None)
