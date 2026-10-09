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
import html
import imaplib
import re
import subprocess
import sys
import threading
from datetime import date, datetime, timedelta, timezone

import job_tool

KEYCHAIN_SERVICE = "job-search-imap"
IMAP_HOST = "imap.gmail.com"
MAILBOX = '"[Gmail]/All Mail"'
FIRST_SYNC_DAYS = 30
FETCH_BATCH = 200
BODY_CHARS = 6000
HEADER_PART = "BODY.PEEK[HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID LIST-UNSUBSCRIBE)]"
FULL_PART = "BODY.PEEK[]"

from jobsearch import inbox_mail as _mail

ACTION_KINDS = _mail.ACTION_KINDS
REVIEW_KINDS = _mail.REVIEW_KINDS
GENERIC_COMPANY_WORDS = _mail.GENERIC_COMPANY_WORDS
ROLE_STOPWORDS = _mail.ROLE_STOPWORDS
NOISE_SUBJECT_RE = _mail.NOISE_SUBJECT_RE
NOISE_SENDER_RE = _mail.NOISE_SENDER_RE
JOB_HINT_RE = _mail.JOB_HINT_RE
ATS_SENDER_RE = _mail.ATS_SENDER_RE
NOREPLY_RE = _mail.NOREPLY_RE
WEAK_REJECTION_RE = _mail.WEAK_REJECTION_RE
REJECTION_RE = _mail.REJECTION_RE
VIEWED_RE = _mail.VIEWED_RE
INVITE_RE = _mail.INVITE_RE
CONFIRM_RE = _mail.CONFIRM_RE
INTERVIEW_RE = _mail.INTERVIEW_RE
CONDITIONAL_RE = _mail.CONDITIONAL_RE
LINKEDIN_MESSAGE_RE = _mail.LINKEDIN_MESSAGE_RE
LINKEDIN_COMPANY_RE = _mail.LINKEDIN_COMPANY_RE

_words = _mail._words
_contains = _mail._contains
is_candidate = _mail.is_candidate
classify = _mail.classify
_by_role = _mail._by_role
_is_generic = _mail._is_generic
_named_in_head = _mail._named_in_head
match = _mail.match
next_status = _mail.next_status
decide = _mail.decide
parse_message = _mail.parse_message
message_text = _mail.message_text
NON_TEXT_HTML_RE = _mail.NON_TEXT_HTML_RE


# ---- state ------------------------------------------------------------------

def state_path():
    return job_tool.state_dir() / "inbox_state.json"


def load_state():
    state = job_tool.load_json(state_path(), {})
    for key, default in (("uidvalidity", None), ("last_uid", 0), ("last_sync", None),
                         ("review", []), ("actions", []), ("ignored", [])):
        state.setdefault(key, default)
    return state


# Guards inbox_state.json read-modify-write between the sync thread and page clicks in the same
# server process: each writer re-reads the file under the lock instead of saving a stale copy.
_STATE_LOCK = threading.RLock()


def _merge_save(actions=(), review=(), meta=None):
    """Add new actions/review items (skipping ones already known or ignored) and sync bookkeeping
    to the state on disk, keeping whatever the page changed meanwhile."""
    with _STATE_LOCK:
        disk = load_state()
        seen = {i["msg_id"] for i in disk["actions"] + disk["review"]} | set(disk["ignored"])
        disk["actions"] += [a for a in actions if a["msg_id"] not in seen]
        disk["review"] += [i for i in review if i["msg_id"] not in seen]
        disk.update(meta or {})
        job_tool.save_json(state_path(), disk)
        return disk


def _known_msg_ids(rows, state):
    known = {e.get("msg_id") for r in rows for e in r.get("events") or []}
    known |= {i["msg_id"] for i in state["review"] + state["actions"]} | set(state["ignored"])
    known.discard(None)
    return known


# ---- IMAP -------------------------------------------------------------------

def _check(typ, data, what):
    if typ != "OK":
        raise RuntimeError(f"IMAP {what} failed: {data!r}")


def _uidvalidity(conn):
    _, data = conn.response("UIDVALIDITY")
    return int(data[0]) if data and data[0] else None


def search_uids(conn, state, days, today):
    validity = _uidvalidity(conn)
    if validity != state["uidvalidity"]:
        state["uidvalidity"], state["last_uid"] = validity, 0
    incremental = bool(state["last_uid"]) and days is None
    if incremental:
        typ, data = conn.uid("SEARCH", None, "UID", f"{state['last_uid'] + 1}:*")
    else:
        since = (today - timedelta(days=days or FIRST_SYNC_DAYS)).strftime("%d-%b-%Y")
        typ, data = conn.uid("SEARCH", None, "SINCE", since)
    _check(typ, data, "SEARCH")
    uids = sorted(int(u) for u in (data[0] or b"").split())
    # "UID n:*" always returns the newest message even when it is older than n.
    return [u for u in uids if u > state["last_uid"]] if incremental else uids


def fetch(conn, uids, part):
    """UID FETCH in batches, returning (uid, raw bytes) in UID order. `part` is always a BODY.PEEK
    item so the \\Seen flag is never set."""
    out = []
    for i in range(0, len(uids), FETCH_BATCH):
        batch = uids[i:i + FETCH_BATCH]
        typ, data = conn.uid("FETCH", ",".join(map(str, batch)), f"(UID {part})")
        _check(typ, data, "FETCH")
        for j, item in enumerate(data):
            if not isinstance(item, tuple):
                continue
            # The UID can come before the literal or in the trailing b" UID n)" element.
            m = re.search(rb"UID (\d+)", item[0])
            if not m and j + 1 < len(data) and isinstance(data[j + 1], bytes):
                m = re.search(rb"UID (\d+)", data[j + 1])
            if m:
                out.append((int(m.group(1)), item[1]))
    if len(out) < len(uids):
        print(f"warning: asked IMAP for {len(uids)} messages, parsed {len(out)}", file=sys.stderr)
    return sorted(out)


# ---- sync -------------------------------------------------------------------

def apply_to_row(row_id, item, kind, status):
    patch = {"id": row_id}
    if status:
        patch["status"] = status
        if status == "Applied":
            patch["applied_date"] = item["date"]
    event = {"date": item["date"], "type": "email", "kind": kind, "subject": item["subject"][:140],
             "msg_id": item["msg_id"], "source": "inbox"}
    return job_tool.upsert_tracker_row(patch, source="inbox", event=event, when=item["date"])


def _from_self(msg, own_address):
    return bool(own_address) and email.utils.parseaddr(msg["sender"])[1].lower() == own_address.lower()


def sync(conn, today=None, days=None, dry_run=False, own_address=None):
    """One pass over new mail. Messages sent by `own_address` (All Mail includes Sent) are skipped.
    Tracker writes and action items are saved per message, so a crash midway loses nothing."""
    today = today or date.today()
    state = load_state()
    rows = job_tool.load_rows()["rows"]
    uids = search_uids(conn, state, days, today)
    company_words = [job_tool.normalize_company(r["company"]) for r in rows]
    heads = [parse_message(uid, raw, with_body=False) for uid, raw in fetch(conn, uids, HEADER_PART)]
    wanted = [h["uid"] for h in heads if not _from_self(h, own_address) and is_candidate(h, company_words)]
    summary = {"scanned": len(heads), "candidates": len(wanted), "applied": [], "review": [],
               "actions": [], "ghosted": []}
    known = _known_msg_ids(rows, state)

    for uid, raw in fetch(conn, wanted, FULL_PART):
        msg = parse_message(uid, raw)
        if msg["msg_id"] in known:
            continue
        known.add(msg["msg_id"])
        kind = classify(msg)
        decision = decide(msg, kind, rows)
        record = {k: msg[k] for k in ("msg_id", "date", "sender", "subject")}
        record["kind"] = kind
        if decision["type"] == "apply":
            summary["applied"].append(dict(record, row_id=decision["row_id"], status=decision["status"]))
            action = dict(record, row_id=decision["row_id"], done=False) if decision["action"] else None
            if action:
                summary["actions"].append(action)
            if not dry_run:
                if action:
                    _merge_save(actions=[action])
                apply_to_row(decision["row_id"], msg, kind, decision["status"])
                rows = job_tool.load_rows()["rows"]
        elif decision["type"] == "review":
            summary["review"].append(dict(record, candidates=decision["candidates"],
                                          snippet=" ".join(msg["body"].split())[:300]))

    if dry_run:
        return summary
    if uids:
        state["last_uid"] = max(state["last_uid"], uids[-1])
    state["last_sync"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    state = _merge_save(review=summary["review"], meta={k: state[k] for k in ("uidvalidity", "last_uid", "last_sync")})
    # A reply that only matched weakly is still a reply: don't ghost a row while it waits in review.
    pending = {rid for item in state["review"] for rid in item["candidates"]}
    summary["ghosted"] = [r["id"] for r in job_tool.mark_ghosted(today, skip_ids=pending)]
    return summary


def resolve(msg_id, row_id=None):
    """Settle a review item: attach it to tracker row `row_id`, or drop it when row_id is None."""
    with _STATE_LOCK:
        return _resolve(msg_id, row_id)


def _resolve(msg_id, row_id):
    state = load_state()
    item = next((i for i in state["review"] if i["msg_id"] == msg_id), None)
    if item is None:
        return None, f"no review item {msg_id}"
    result = {"dropped": msg_id}
    if row_id is None:
        state["ignored"].append(msg_id)
    else:
        found = next((r for r in job_tool.load_rows()["rows"] if r["id"] == row_id), None)
        if found is None:
            return None, f"no tracker row {row_id}"
        result, err = apply_to_row(row_id, item, item["kind"], next_status(item["kind"], found["status"]))
        if err:
            return None, err
        if item["kind"] in ACTION_KINDS:
            action = {k: item[k] for k in ("msg_id", "date", "sender", "subject", "kind")}
            state["actions"].append(dict(action, row_id=row_id, done=False))
    state["review"].remove(item)
    job_tool.save_json(state_path(), state)
    return result, None


def mark_done(msg_id):
    with _STATE_LOCK:
        return _mark_done(msg_id)


def _mark_done(msg_id):
    state = load_state()
    item = next((a for a in state["actions"] if a["msg_id"] == msg_id), None)
    if item is None:
        return None, f"no action {msg_id}"
    item["done"] = True
    job_tool.save_json(state_path(), state)
    return item, None


# ---- credentials + connection -----------------------------------------------

SETUP_HELP = f"""One-off setup (2 minutes):
  1. Google Account > Security > 2-Step Verification must be on.
  2. https://myaccount.google.com/apppasswords > create one called "job-search".
  3. Store it in the Keychain (it prompts for the password, nothing lands in shell history):
       security add-generic-password -U -s {KEYCHAIN_SERVICE} -a <you>@gmail.com -w
  4. Check it: python3 inbox.py setup"""


def get_credentials():
    try:
        meta = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE],
                              capture_output=True, text=True, check=True).stdout
        password = subprocess.run(["security", "find-generic-password", "-s", KEYCHAIN_SERVICE, "-w"],
                                  capture_output=True, text=True, check=True).stdout.strip()
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None, f"no Keychain item '{KEYCHAIN_SERVICE}' — run `inbox.py setup` for instructions"
    m = re.search(r'"acct"<blob>="([^"]*)"', meta)
    if not m or not password:
        return None, f"Keychain item '{KEYCHAIN_SERVICE}' has no account or password"
    return (m.group(1), password), None


def find_all_mail(conn):
    """The All Mail folder is "[Gmail]/All Mail" or, on UK accounts, "[Google Mail]/All Mail"; find
    it by its \\All special-use flag."""
    typ, data = conn.list()
    if typ == "OK":
        for line in data or []:
            line = line.decode(errors="replace") if isinstance(line, bytes) else str(line)
            m = re.search(r'"([^"]+)"\s*$', line)
            if "\\All" in line.split(")")[0] and m:
                return f'"{m.group(1)}"'
    return MAILBOX


def open_mailbox(user, password):
    conn = imaplib.IMAP4_SSL(IMAP_HOST, timeout=60)
    conn.login(user, password)
    typ, data = conn.select(find_all_mail(conn), readonly=True)
    _check(typ, data, "SELECT")
    return conn


def run_sync(days=None, dry_run=False):
    creds, err = get_credentials()
    if err:
        raise RuntimeError(err)
    conn = open_mailbox(*creds)
    try:
        return sync(conn, days=days, dry_run=dry_run, own_address=creds[0])
    finally:
        try:
            conn.logout()
        except (imaplib.IMAP4.error, OSError):
            pass


def format_summary(s):
    lines = [f"Inbox: scanned {s['scanned']}, {s['candidates']} job-related, "
             f"{len(s['applied'])} tracker update(s), {len(s['review'])} to review, "
             f"{len(s['actions'])} need a reply, {len(s['ghosted'])} ghosted"]
    for a in s["applied"]:
        change = f" → {a['status']}" if a["status"] else ""
        lines.append(f"  row {a['row_id']}{change}  [{a['kind']}] {a['subject']}")
    for r in s["review"]:
        lines.append(f"  review {r['msg_id']}  [{r['kind']}] {r['subject']}")
    return "\n".join(lines)


# ---- CLI --------------------------------------------------------------------

def _print_items(items, empty):
    if not items:
        print(empty)
    for i in items:
        extra = f" candidates={i['candidates']}" if "candidates" in i else f" row={i.get('row_id')}"
        print(f"{i['date']}  [{i['kind']}] {i['subject']}\n    from {i['sender']}  {i['msg_id']}{extra}")


def _exit_on(result, err):
    if err:
        print(f"error: {err}", file=sys.stderr)
        sys.exit(1)
    print(result)


def cmd_setup(_args):
    creds, err = get_credentials()
    if err:
        print(f"{err}\n\n{SETUP_HELP}")
        return 1
    open_mailbox(*creds).logout()
    print(f"OK: logged in to {IMAP_HOST} as {creds[0]} (read-only)")


def cmd_sync(args):
    print(format_summary(run_sync(days=args.days, dry_run=args.dry_run)))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("setup").set_defaults(func=cmd_setup)
    p_sync = sub.add_parser("sync")
    p_sync.add_argument("--days", type=int)
    p_sync.add_argument("--dry-run", action="store_true")
    p_sync.set_defaults(func=cmd_sync)
    sub.add_parser("review").set_defaults(
        func=lambda a: _print_items(load_state()["review"], "Review queue is empty."))
    p_resolve = sub.add_parser("resolve")
    p_resolve.add_argument("msg_id")
    group = p_resolve.add_mutually_exclusive_group(required=True)
    group.add_argument("--row", type=int)
    group.add_argument("--ignore", action="store_true")
    p_resolve.set_defaults(func=lambda a: _exit_on(*resolve(a.msg_id, a.row)))
    p_actions = sub.add_parser("actions")
    p_actions.add_argument("--all", action="store_true")
    p_actions.set_defaults(func=lambda a: _print_items(
        [i for i in load_state()["actions"] if a.all or not i["done"]], "Nothing needs a reply."))
    p_done = sub.add_parser("done")
    p_done.add_argument("msg_id")
    p_done.set_defaults(func=lambda a: _exit_on(*mark_done(a.msg_id)))
    p_undo = sub.add_parser("undo")
    p_undo.add_argument("row_id", type=int)
    p_undo.set_defaults(func=lambda a: _exit_on(*job_tool.undo_last_status(a.row_id)))
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())
