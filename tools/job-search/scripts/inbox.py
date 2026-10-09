#!/usr/bin/env python3
"""
Inbox sync: reads Gmail over IMAP (read-only) and keeps the application tracker in step with what
employers actually sent — confirmations, rejections, interview invites, recruiter replies.

Usage:
  inbox.py setup                          check the Keychain credential and the IMAP login
  inbox.py sync [--days N] [--dry-run]    process new mail (first run looks back 30 days)
  inbox.py review                         emails waiting for a decision
  inbox.py resolve <msg_id> (--row ID | --ignore)
  inbox.py actions [--all]                replies and invites that need an answer from you
  inbox.py done <msg_id>                  mark an action handled
  inbox.py undo <row_id>                  revert the last automatic status change on a row

Only unambiguous matches change the tracker (confirmation → Applied, rejection → Rejected,
invite/reply → Responded + an action item). Anything uncertain lands in the review queue.

Safety: the mailbox is opened with EXAMINE (read-only) and bodies are fetched with BODY.PEEK, so
nothing is marked read, moved, deleted or sent. The app password lives in the macOS Keychain.
"""

import argparse
import email
import email.policy
import email.utils
import imaplib
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone

import job_tool

KEYCHAIN_SERVICE = "job-search-imap"
IMAP_HOST = "imap.gmail.com"
MAILBOX = '"[Gmail]/All Mail"'
FIRST_SYNC_DAYS = 30
FETCH_BATCH = 200
BODY_CHARS = 6000
HEADER_PART = "BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)]"
FULL_PART = "BODY.PEEK[]"

ACTION_KINDS = ("interview", "reply")
REVIEW_KINDS = ("confirmation", "rejection", "interview")
ROLE_STOPWORDS = {"senior", "junior", "lead", "engineer", "engineering", "the", "and", "of", "for", "a",
                  "uk", "london", "remote", "hybrid", "i", "ii", "iii"}

NOISE_SUBJECT_RE = re.compile(
    r"job alert|jobs? you may be interested|new jobs? (for you|match|in)|recommended (jobs|for you)|"
    r"jobs? similar to|is hiring|are hiring|top job picks|newsletter|webinar|people also (viewed|applied)", re.I)
JOB_HINT_RE = re.compile(
    r"applica|applying|applied|interview|candida|position|\brole\b|opportunit|recruit|talent|hiring|"
    r"career|offer|assessment", re.I)
ATS_SENDER_RE = re.compile(
    r"greenhouse|lever\.co|ashbyhq|workable|teamtailor|workday|smartrecruiters|recruitee|gem\.com|"
    r"comeet|bamboohr|personio|hibob|jobvite|icims|successfactors|linkedin", re.I)
NOREPLY_RE = re.compile(r"no-?reply|do-?not-?reply|notification|mailer|automated", re.I)

REJECTION_RE = re.compile(
    r"unfortunately|regret to inform|not (be )?(moving|move|progress\w*|proceed\w*) (forward|further|ahead)|"
    r"(decided|chosen) to (move|proceed|progress|go) (forward |ahead )?with other|other candidates (whose|who)|"
    r"will not be (progressing|proceeding|taking)|not been successful|unsuccessful|"
    r"position has (now )?been filled|no longer (being )?consider|not (been )?selected", re.I)
VIEWED_RE = re.compile(r"application was viewed|viewed your application", re.I)
INVITE_RE = re.compile(
    r"(like|love|pleased|happy|keen) to (invite|schedule|arrange|set up|book|speak|chat|move you forward|progress)|"
    r"invite you to|book (a|some) time|calendly\.com|cal\.com/|your availability|"
    r"when (are|would) you (be )?(free|available)|available for a (quick )?(call|chat)", re.I)
CONFIRM_RE = re.compile(
    r"thank(s| you) for (your )?(applying|application|interest in)|"
    r"application (has been |was )?(received|submitted)|(we've|we have) received your application|"
    r"your application (was sent|to|for|has been)|application confirmation|successfully applied", re.I)
INTERVIEW_RE = re.compile(
    r"\binterview|phone screen|screening call|intro(ductory)? call|next stage|take-home|"
    r"technical (assessment|test)|coding (test|challenge)|hackerrank|codility", re.I)
LINKEDIN_MESSAGE_RE = re.compile(r"sent you a (new )?message|new message from|\binmail\b", re.I)


# ---- parsing ----------------------------------------------------------------

def parse_message(uid, raw, with_body=True):
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    try:
        sent = email.utils.parsedate_to_datetime(str(msg["Date"])).date().isoformat()
    except (TypeError, ValueError):
        sent = job_tool.today_str()
    return {
        "uid": uid,
        "msg_id": str(msg["Message-ID"] or f"<uid-{uid}>").strip(),
        "date": sent,
        "sender": " ".join(str(msg["From"] or "").split()),
        "subject": " ".join(str(msg["Subject"] or "").split()),
        "body": message_text(msg)[:BODY_CHARS] if with_body else "",
    }


def message_text(msg):
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is None:
            return ""
        text = part.get_content()
        return job_tool.clean_text(text) if part.get_content_subtype() == "html" else text
    except (KeyError, LookupError, ValueError):
        return ""


# ---- classify + match -------------------------------------------------------

def _words(text):
    return re.findall(r"[a-z0-9]+", (text or "").lower())


def _contains(words, seq):
    n = len(seq)
    return n > 0 and any(words[i:i + n] == seq for i in range(len(words) - n + 1))


def is_candidate(head, company_words):
    """Cheap header-only filter deciding which messages are worth downloading in full."""
    if NOISE_SUBJECT_RE.search(head["subject"]):
        return False
    if JOB_HINT_RE.search(head["subject"]) or ATS_SENDER_RE.search(head["sender"]):
        return True
    words = _words(f"{head['sender']} {head['subject']}")
    return any(_contains(words, cw) for cw in company_words)


def classify(msg):
    """Order matters: rejections often open with "thank you for applying", and confirmations often
    mention a future interview, so a confirmation only loses to an explicit invitation."""
    text = f"{msg['subject']}\n{msg['body']}"
    if NOISE_SUBJECT_RE.search(msg["subject"]):
        return "noise"
    if REJECTION_RE.search(text):
        return "rejection"
    if VIEWED_RE.search(text):
        return "viewed"
    if INVITE_RE.search(text):
        return "interview"
    if CONFIRM_RE.search(text):
        return "confirmation"
    if INTERVIEW_RE.search(text):
        return "interview"
    if LINKEDIN_MESSAGE_RE.search(msg["subject"]) or not NOREPLY_RE.search(msg["sender"]):
        return "reply"
    return "other"


def _by_role(rows, words):
    present = set(words)

    def score(r):
        role = [w for w in _words(r["role"]) if w not in ROLE_STOPWORDS]
        return sum(w in present for w in role) / len(role) if role else 0

    scored = sorted(((score(r), r) for r in rows), key=lambda x: -x[0])
    if scored[0][0] >= 0.6 and scored[0][0] > scored[1][0]:
        return [scored[0][1]]
    return rows


def match(msg, rows):
    """'strong' = the company is named by the sender or subject and exactly one row fits; 'weak' =
    named only in the body, or several rows fit. Only strong matches ever change the tracker."""
    head = _words(f"{msg['sender']} {msg['subject']}")
    body = _words(msg["body"])
    strong, weak = [], []
    for r in rows:
        if r.get("status") == "Withdrawn":
            continue
        cw = job_tool.normalize_company(r["company"])
        if _contains(head, cw):
            strong.append(r)
        elif _contains(body, cw):
            weak.append(r)
    if len(strong) > 1:
        strong = _by_role(strong, head + body)
    if len(strong) == 1:
        return strong[0], "strong", [strong[0]["id"]]
    candidates = strong or weak
    if candidates:
        return None, "weak", [r["id"] for r in candidates]
    return None, None, []


def next_status(kind, current):
    if kind == "confirmation" and current == "Shortlisted":
        return "Applied"
    if kind == "rejection" and current not in ("Rejected", "Withdrawn", "Offer"):
        return "Rejected"
    if kind in ACTION_KINDS and current in ("Shortlisted", "Applied", "Ghosted"):
        return "Responded"
    return None


def decide(msg, kind, rows):
    if kind in ("noise", "other"):
        return {"type": "skip"}
    found, strength, candidates = match(msg, rows)
    if strength == "strong":
        return {"type": "apply", "row_id": found["id"], "status": next_status(kind, found["status"]),
                "action": kind in ACTION_KINDS}
    if candidates or kind in REVIEW_KINDS:
        return {"type": "review", "candidates": candidates}
    return {"type": "skip"}
