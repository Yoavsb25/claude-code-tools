"""Inbox classification and tracker matching (no IMAP)."""

import email
import email.policy
import email.utils
import html
import re

from jobsearch.store import today_str
from jobsearch.text import clean_text, normalize_company

BODY_CHARS = 6000

ACTION_KINDS = ("interview", "reply")
REVIEW_KINDS = ("confirmation", "rejection", "interview")
GENERIC_COMPANY_WORDS = {"global", "search", "data", "digital", "talent", "group", "solutions", "partners",
                         "consulting", "recruitment", "people", "tech", "cloud", "capital", "media",
                         "health", "energy", "systems", "software", "client", "server", "united", "byte"}
ROLE_STOPWORDS = {"senior", "junior", "lead", "engineer", "engineering", "the", "and", "of", "for", "a",
                  "uk", "london", "remote", "hybrid", "i", "ii", "iii"}

NOISE_SUBJECT_RE = re.compile(
    r"job alert|jobs? you may be interested|new jobs? (for you|match|in)|recommended (jobs|for you)|"
    r"jobs? similar to|is hiring|are hiring|top job picks|newsletter|webinar|people also (viewed|applied)|"
    r"receipt|invoice|your order|payment|verification code|password|security alert", re.I)
NOISE_SENDER_RE = re.compile(r"jobalerts|job-alerts|jobs-listings|invitations@linkedin|newsletter", re.I)
JOB_HINT_RE = re.compile(
    r"applica|applying|applied|interview|candida|position|\brole\b|opportunit|recruit|talent|hiring|"
    r"career|offer|assessment", re.I)
ATS_SENDER_RE = re.compile(
    r"greenhouse|lever\.co|ashbyhq|workable|teamtailor|workday|smartrecruiters|recruitee|gem\.com|"
    r"comeet|bamboohr|personio|hibob|jobvite|icims|successfactors|linkedin", re.I)
NOREPLY_RE = re.compile(r"no-?reply|do-?not-?reply|notification|mailer|automated", re.I)

# "unfortunately"/"unsuccessful" alone also appear in confirmation boilerplate ("unfortunately we
# can't reply to everyone"), so they only count as a rejection when no confirmation phrase is present.
WEAK_REJECTION_RE = re.compile(r"unfortunately|unsuccessful", re.I)
REJECTION_RE = re.compile(
    r"regret to inform|not to (move|proceed|progress|continue)|application_rejected|"
    r"do(n.t| not) have any (relevant|suitable) (opportunit|position|role)|not (be )?(moving|move|progress\w*|proceed\w*) (forward|further|ahead)|"
    r"(decided|chosen) to (move|proceed|progress|go) (forward |ahead )?with other|other candidates (whose|who)|"
    r"will not be (progressing|proceeding|taking)|not been successful|"
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
CONDITIONAL_RE = re.compile(
    r"\bif (you are |you're |you have been |your application is )?(shortlisted|successful|selected|suitable)|"
    r"if your (profile|experience|application|skills|background)|should (you|your \w+) (be|progress|match)", re.I)
LINKEDIN_MESSAGE_RE = re.compile(r"sent you a (new )?message|new message from|\binmail\b", re.I)
# LinkedIn names the employer exactly: "...application was sent to Byte", "...to AI Engineer at Byte".
LINKEDIN_COMPANY_RE = re.compile(r"(?:was sent to|was viewed by|\bat)\s+(.+?)\s*$", re.I)


NON_TEXT_HTML_RE = re.compile(r"<(style|script|head)\b.*?</\1>", re.I | re.S)


# ---- parsing ----------------------------------------------------------------

def parse_message(uid, raw, with_body=True):
    msg = email.message_from_bytes(raw, policy=email.policy.default)
    try:
        sent = email.utils.parsedate_to_datetime(str(msg["Date"])).date().isoformat()
    except (TypeError, ValueError):
        sent = today_str()
    return {
        "uid": uid,
        "msg_id": str(msg["Message-ID"] or f"<uid-{uid}>").strip(),
        "date": sent,
        "sender": " ".join(str(msg["From"] or "").split()),
        "subject": " ".join(str(msg["Subject"] or "").split()),
        "body": message_text(msg)[:BODY_CHARS] if with_body else "",
        # Mass mail (newsletters, marketing, visitor systems) carries List-Unsubscribe; a person's reply doesn't.
        "bulk": msg["List-Unsubscribe"] is not None,
    }


def message_text(msg):
    try:
        part = msg.get_body(preferencelist=("plain", "html"))
        if part is None:
            return ""
        text = part.get_content()
        if part.get_content_subtype() == "html":
            text = clean_text(NON_TEXT_HTML_RE.sub(" ", text))
        return html.unescape(text)
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
    if NOISE_SUBJECT_RE.search(head["subject"]) or NOISE_SENDER_RE.search(head["sender"]):
        return False
    if JOB_HINT_RE.search(head["subject"]) or ATS_SENDER_RE.search(head["sender"]):
        return True
    words = _words(f"{head['sender']} {head['subject']}")
    return any(_contains(words, cw) for cw in company_words)


def classify(msg):
    """Order matters: rejections often open with "thank you for applying", and confirmations often
    mention a future interview, so a confirmation only loses to an explicit invitation."""
    text = f"{msg['subject']}\n{msg['body']}"
    if NOISE_SUBJECT_RE.search(msg["subject"]) or NOISE_SENDER_RE.search(msg["sender"]):
        return "noise"
    confirm = CONFIRM_RE.search(text)
    if REJECTION_RE.search(text) or (WEAK_REJECTION_RE.search(text) and not confirm):
        return "rejection"
    if VIEWED_RE.search(text):
        return "viewed"
    if INVITE_RE.search(text) and not (confirm and CONDITIONAL_RE.search(text)):
        return "interview"
    if confirm:
        return "confirmation"
    if INTERVIEW_RE.search(text):
        return "interview"
    if LINKEDIN_MESSAGE_RE.search(msg["subject"]) or "inmail" in msg["sender"].lower():
        return "reply"
    if not msg.get("bulk") and not NOREPLY_RE.search(msg["sender"]):
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


def _is_generic(company_words):
    """A one-word dictionary name ("Byte", "Global") is too easily matched by accident."""
    return len(company_words) == 1 and company_words[0] in GENERIC_COMPANY_WORDS


def _named_in_head(cw, company, sender_words, subject_words, subject_company=None):
    # An email platform (LinkedIn, Greenhouse, ...) as the employer is named by every notification
    # it sends, so for those only the subject counts.
    in_sender = _contains(sender_words, cw) and not ATS_SENDER_RE.search(company)
    in_subject = _contains(subject_words, cw)
    if subject_company == cw:
        return True
    if _is_generic(cw):
        return in_sender
    return in_sender or in_subject


def match(msg, rows):
    """'strong' = the company is named by the sender or subject and exactly one row fits; 'weak' =
    named only in the body, or several rows fit. Only strong matches ever change the tracker.
    Generic one-word names only count when they are in the sender, and a name contained in a
    longer matched name ("Global" inside "Cboe Global") is demoted."""
    sender, subject = _words(msg["sender"]), _words(msg["subject"])
    body = _words(msg["body"])
    named = LINKEDIN_COMPANY_RE.search(msg["subject"]) if "linkedin" in msg["sender"].lower() else None
    subject_company = normalize_company(named.group(1)) if named else None
    strong, weak = [], []
    for r in rows:
        if r.get("status") == "Withdrawn":
            continue
        cw = normalize_company(r["company"])
        if _named_in_head(cw, r["company"], sender, subject, subject_company):
            strong.append(r)
        elif _contains(sender + subject + body, cw):
            weak.append(r)
    if len(strong) > 1:
        names = {r["id"]: normalize_company(r["company"]) for r in strong}
        contained = [r for r in strong
                     if any(len(names[o["id"]]) > len(names[r["id"]]) and _contains(names[o["id"]], names[r["id"]])
                            for o in strong)]
        weak += contained
        strong = [r for r in strong if r not in contained]
    if len(strong) > 1 and len({tuple(normalize_company(r["company"])) for r in strong}) == 1:
        strong = _by_role(strong, sender + subject + body)
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

