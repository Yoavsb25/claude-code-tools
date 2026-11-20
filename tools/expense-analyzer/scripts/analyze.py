#!/usr/bin/env python3
"""
Expense analyzer for Wise CSV exports and Monzo (via the wealth-dashboard DB).
Usage: python analyze.py <csv_path|monzo> [--month YYYY-MM] [--compare <prev_csv_path|monzo>]
  monzo  reads the joint Monzo account from the wealth dashboard's SQLite DB (read-only).
         Override the DB path with WEALTH_DB.
Outputs a markdown report to stdout.
"""

import csv
import glob
import os
import sqlite3
import sys
import statistics
from collections import defaultdict
from datetime import datetime

SKIP_CATEGORIES = {"Money added", "Rewards", "General"}
LARGE_THRESHOLD = 100.0
OUTLIER_MULTIPLIER = 2.0
OUTLIER_MIN_AMOUNT = 50.0


def parse_date(s):
    try:
        return datetime.strptime(s[:10], "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def to_gbp(amount, currency, exchange_rate):
    if currency == "GBP":
        return amount
    try:
        rate = float(exchange_rate)
        if rate > 0:
            return amount / rate
    except (ValueError, TypeError):
        pass
    return amount


def load_all_rows(filepath):
    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        return list(reader)


def find_refund_matcher(all_rows):
    """Returns a function that, given (merchant, amount, charge_date), consumes and
    returns True if a matching REFUNDED/IN row exists (same merchant + exact amount,
    dated on/after the charge)."""
    refunds = [
        r for r in all_rows
        if r.get("Direction") == "IN" and r.get("Status", "").strip().upper() == "REFUNDED"
    ]
    consumed = set()

    def amount_of(row):
        try:
            return float(row.get("Source amount (after fees)", 0) or 0)
        except (ValueError, TypeError):
            return 0.0

    def consume(merchant, amount, charge_date):
        for i, r in enumerate(refunds):
            if i in consumed:
                continue
            if r.get("Source name", "").strip().strip('"') != merchant:
                continue
            if abs(amount_of(r) - amount) > 0.01:
                continue
            r_date = parse_date(r.get("Created on", ""))
            if charge_date and r_date and r_date < charge_date:
                continue
            consumed.add(i)
            return True
        return False

    return consume


def load_transactions(filepath, month_filter=None):
    all_rows = load_all_rows(filepath)
    consume_refund = find_refund_matcher(all_rows)

    rows_by_id = defaultdict(list)
    ungrouped = []

    for row in all_rows:
        if row.get("Direction") != "OUT":
            continue
        if row.get("Status", "").strip().upper() == "REFUNDED":
            continue
        category = row.get("Category", "").strip()
        if category in SKIP_CATEGORIES:
            continue
        tx_id = row.get("ID", "").strip()
        if tx_id:
            rows_by_id[tx_id].append(row)
        else:
            ungrouped.append(row)

    transactions = []
    for tx_id, group in rows_by_id.items():
        gbp_rows = [r for r in group if r.get("Source currency", "") == "GBP"]
        chosen = gbp_rows[0] if gbp_rows else group[0]
        transactions.append(chosen)
    transactions.extend(ungrouped)

    result = []
    for row in transactions:
        tx_date = parse_date(row.get("Finished on", "") or row.get("Created on", ""))
        if month_filter and tx_date:
            if tx_date.strftime("%Y-%m") != month_filter:
                continue
        try:
            amount = float(row.get("Source amount (after fees)", 0) or 0)
        except (ValueError, TypeError):
            amount = 0.0
        merchant = row.get("Target name", "Unknown").strip().strip('"')

        if consume_refund(merchant, amount, tx_date):
            continue

        currency = row.get("Source currency", "GBP")
        exchange_rate = row.get("Exchange rate", 1)
        amount_gbp = to_gbp(amount, currency, exchange_rate)

        if amount_gbp < 0.01:
            continue

        result.append({
            "date": tx_date,
            "merchant": row.get("Target name", "Unknown").strip().strip('"'),
            "amount_gbp": amount_gbp,
            "currency": currency,
            "original_amount": amount,
            "category": row.get("Category", "Uncategorized").strip() or "Uncategorized",
        })

    return result


MONZO_DB = os.environ.get(
    "WEALTH_DB", os.path.expanduser("~/Developer/wealth-dashboard/data/wealth.db"))
MONZO_ACCOUNT = "monzo"  # joint account
EXPENSES_DIR = os.path.expanduser("~/Desktop/Money/Expenses")
# Not spending, on top of the dashboard's own non-counting categories (income, savings, ...).
MONZO_SKIP = {"investment", "general", "income", "savings", "not_spending"}
# Monzo category keys -> the names used in the Wise-era reports.
MONZO_NAMES = {
    "eating_out": "Eating out", "groceries": "Groceries", "transport": "Transport",
    "shopping": "Shopping", "entertainment": "Entertainment", "personal_care": "Personal care",
    "bills": "Bills", "holidays": "Trips", "transfers": "Personal transfers",
    "charity": "Charity", "expenses": "Expenses", "family": "Family", "gifts": "Gifts",
    "cash": "Cash", "finances": "Finances",
}


def load_monzo_transactions(month_filter=None, db_path=MONZO_DB, account_id=MONZO_ACCOUNT):
    """Outgoing spend from the dashboard DB. Applies the dashboard's merchant re-categorisation
    rules, skips pot moves, transfers between own accounts and non-spending categories, and
    cancels refunds against the charge they reverse (same merchant, exact amount)."""
    conn = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    try:
        rules = dict(conn.execute("SELECT merchant_key, category FROM merchant_rules"))
        counts = dict(conn.execute("SELECT key, counts FROM categories"))
        names = dict(conn.execute("SELECT key, name FROM categories"))
        own = {r[0] for r in conn.execute("SELECT identifier FROM own_identifiers")}
        rows = conn.execute(
            "SELECT external_id, date, amount, currency, merchant_key, merchant_name, category, "
            "pot_move, counterparty FROM transactions WHERE account_id = ? ORDER BY date, rowid",
            (account_id,)).fetchall()
    finally:
        conn.close()

    spend, refunds = [], []
    for ext_id, day, amount, currency, mkey, merchant, category, pot_move, cp in rows:
        category = rules.get(mkey, category)
        if pot_move or (cp and cp in own):
            continue
        if category in MONZO_SKIP or not counts.get(category, 1):
            continue
        item = {"id": ext_id, "date": parse_date(day), "amount": amount, "key": mkey,
                "merchant": merchant, "category": category, "currency": currency}
        (spend if amount < 0 else refunds).append(item)

    cancelled = set()
    for ref in refunds:
        if ref["category"] == "transfers":
            continue  # money from people isn't a refund
        for tx in spend:
            if (tx["id"] not in cancelled and tx["key"] == ref["key"]
                    and abs(abs(tx["amount"]) - ref["amount"]) < 0.005
                    and tx["date"] and ref["date"] and tx["date"] <= ref["date"]):
                cancelled.add(tx["id"])
                break

    result = []
    for tx in spend:
        if tx["id"] in cancelled:
            continue
        if month_filter and tx["date"] and tx["date"].strftime("%Y-%m") != month_filter:
            continue
        amount = -tx["amount"]
        if amount < 0.01:
            continue
        result.append({
            "date": tx["date"],
            "merchant": tx["merchant"],
            "amount_gbp": amount,  # Monzo amounts are already in the account currency (GBP)
            "currency": "GBP",
            "original_amount": amount,
            "category": MONZO_NAMES.get(tx["category"], names.get(tx["category"], tx["category"])),
        })
    return result


def load_source(source, month_filter=None):
    if source == "monzo":
        return load_monzo_transactions(month_filter)
    return load_transactions(source, month_filter)


def flag_unusual(transactions):
    by_category = defaultdict(list)
    for tx in transactions:
        by_category[tx["category"]].append(tx["amount_gbp"])

    category_means = {}
    for cat, amounts in by_category.items():
        if len(amounts) >= 3:
            category_means[cat] = statistics.mean(amounts)

    flags = []
    for tx in transactions:
        reasons = []
        if tx["amount_gbp"] >= LARGE_THRESHOLD:
            reasons.append(f"large spend (£{tx['amount_gbp']:.2f})")
        cat = tx["category"]
        if cat in category_means:
            mean = category_means[cat]
            if tx["amount_gbp"] >= OUTLIER_MIN_AMOUNT and tx["amount_gbp"] > mean * OUTLIER_MULTIPLIER:
                multiple = tx["amount_gbp"] / mean
                reasons.append(f"{multiple:.1f}× above {cat} average (avg £{mean:.2f})")
        if reasons:
            flags.append({**tx, "reasons": reasons})

    return sorted(flags, key=lambda x: x["amount_gbp"], reverse=True)


def get_category_totals(transactions):
    totals = defaultdict(float)
    for tx in transactions:
        totals[tx["category"]] += tx["amount_gbp"]
    return totals


def compute_monthly_category_averages(current_filepath):
    """Average monthly spend per category across every CSV in the same directory
    as current_filepath (i.e. all monthly exports) plus Monzo history from the
    dashboard DB, grouped by actual transaction month so cross-month settlement
    doesn't skew which month a charge counts in."""
    if current_filepath == "monzo":
        dirpath = EXPENSES_DIR
    else:
        dirpath = os.path.dirname(os.path.abspath(current_filepath)) or "."
    month_cat_totals = defaultdict(lambda: defaultdict(float))

    history = []
    for f in glob.glob(os.path.join(dirpath, "*.csv")):
        history.extend(load_transactions(f))
    if os.path.exists(MONZO_DB):
        history.extend(load_monzo_transactions())

    for tx in history:
        if not tx["date"]:
            continue
        month_key = tx["date"].strftime("%Y-%m")
        month_cat_totals[month_key][tx["category"]] += tx["amount_gbp"]

    num_months = len(month_cat_totals)
    if num_months == 0:
        return {}, 0

    cat_totals = defaultdict(float)
    for cats in month_cat_totals.values():
        for cat, amt in cats.items():
            cat_totals[cat] += amt

    return {cat: total / num_months for cat, total in cat_totals.items()}, num_months


def infer_label(transactions):
    dates = [tx["date"] for tx in transactions if tx["date"]]
    if not dates:
        return "All Transactions"
    first, last = min(dates), max(dates)
    if first.month == last.month and first.year == last.year:
        return first.strftime("%B %Y")
    return f"{first.strftime('%d %b %Y')} – {last.strftime('%d %b %Y')}"


def render_report(transactions, month_label, filepath, prev_transactions=None, prev_label=None,
                   avg_per_month=None, history_months=0):
    if not transactions:
        return f"# Expense Report — {month_label}\n\nNo transactions found.\n"

    total = sum(tx["amount_gbp"] for tx in transactions)
    by_category = defaultdict(list)
    for tx in transactions:
        by_category[tx["category"]].append(tx)

    cat_order = sorted(
        by_category.items(),
        key=lambda x: sum(t["amount_gbp"] for t in x[1]),
        reverse=True,
    )

    prev_totals = get_category_totals(prev_transactions) if prev_transactions else {}
    prev_total = sum(prev_totals.values()) if prev_totals else None
    avg_per_month = avg_per_month or {}

    lines = [
        f"# Expense Report — {month_label}",
        "",
        f"**Source:** `{'Monzo joint account (wealth-dashboard sync)' if filepath == 'monzo' else filepath}`  ",
    ]
    if prev_total is not None:
        delta = total - prev_total
        sign = "+" if delta >= 0 else ""
        lines.append(f"**Total spent:** £{total:,.2f} ({sign}£{delta:,.2f} vs {prev_label})  ")
    else:
        lines.append(f"**Total spent:** £{total:,.2f}  ")
    lines += [
        f"**Transactions:** {len(transactions)}",
        "",
        "---",
        "",
        "## By Category",
        "",
    ]

    if prev_totals:
        lines += [
            f"| Category | Total | vs {prev_label} | # | Avg/txn | Avg/month |",
            "|----------|------:|----------:|--:|----:|----:|",
        ]
        for cat, txs in cat_order:
            cat_total = sum(t["amount_gbp"] for t in txs)
            cat_avg = cat_total / len(txs)
            cat_month_avg = avg_per_month.get(cat, 0.0)
            prev = prev_totals.get(cat, 0.0)
            delta = cat_total - prev
            sign = "+" if delta >= 0 else ""
            lines.append(
                f"| {cat} | £{cat_total:,.2f} | {sign}£{delta:,.2f} | {len(txs)} | £{cat_avg:.2f} | £{cat_month_avg:,.2f} |"
            )
    else:
        lines += [
            "| Category | Total | # | Avg/txn | Avg/month |",
            "|----------|------:|--:|----:|----:|",
        ]
        for cat, txs in cat_order:
            cat_total = sum(t["amount_gbp"] for t in txs)
            cat_avg = cat_total / len(txs)
            cat_month_avg = avg_per_month.get(cat, 0.0)
            lines.append(f"| {cat} | £{cat_total:,.2f} | {len(txs)} | £{cat_avg:.2f} | £{cat_month_avg:,.2f} |")

    if history_months:
        lines.append(f"\n*Avg/month is the per-category average across {history_months} month(s) of exported history (Wise exports + Monzo).*")

    top = sorted(transactions, key=lambda x: x["amount_gbp"], reverse=True)[:10]
    lines += [
        "",
        "---",
        "",
        "## Top 10 Transactions",
        "",
        "| Date | Merchant | Category | Amount |",
        "|------|----------|----------|-------:|",
    ]
    for tx in top:
        d = tx["date"].strftime("%d %b") if tx["date"] else "—"
        lines.append(f"| {d} | {tx['merchant']} | {tx['category']} | £{tx['amount_gbp']:,.2f} |")

    flagged = flag_unusual(transactions)
    if flagged:
        lines += ["", "---", "", "## ⚠ Flagged Expenses", ""]
        for tx in flagged:
            d = tx["date"].strftime("%d %b") if tx["date"] else "—"
            reasons = "; ".join(tx["reasons"])
            lines.append(
                f"- **{tx['merchant']}** — £{tx['amount_gbp']:,.2f} ({tx['category']}, {d}) — {reasons}"
            )

    lines += ["", "---", "", "## Category Breakdown", ""]
    for cat, txs in cat_order:
        cat_total = sum(t["amount_gbp"] for t in txs)
        lines.append(f"### {cat} — £{cat_total:,.2f}")
        lines.append("")
        for tx in sorted(txs, key=lambda x: x["amount_gbp"], reverse=True):
            d = tx["date"].strftime("%d %b") if tx["date"] else "—"
            fx = f" ({tx['original_amount']:.2f} {tx['currency']})" if tx["currency"] != "GBP" else ""
            lines.append(f"- {d} · **{tx['merchant']}** · £{tx['amount_gbp']:.2f}{fx}")
        lines.append("")

    return "\n".join(lines)


def main():
    args = sys.argv[1:]
    if not args:
        print("Usage: analyze.py <csv_path|monzo> [--month YYYY-MM] [--compare <prev_csv_path|monzo>]",
              file=sys.stderr)
        sys.exit(1)

    filepath = args[0]
    month_filter = None
    compare_path = None

    if "--month" in args:
        idx = args.index("--month")
        month_filter = args[idx + 1]

    if "--compare" in args:
        idx = args.index("--compare")
        compare_path = args[idx + 1]

    transactions = load_source(filepath, month_filter)

    if month_filter:
        month_label = datetime.strptime(month_filter, "%Y-%m").strftime("%B %Y")
    elif transactions:
        month_label = infer_label(transactions)
    else:
        month_label = "All Transactions"

    prev_transactions = None
    prev_label = None
    if compare_path:
        if compare_path == "monzo":
            if not month_filter:
                print("--compare monzo needs --month", file=sys.stderr)
                sys.exit(1)
            y, m = map(int, month_filter.split("-"))
            prev_month = f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"
            prev_transactions = load_monzo_transactions(prev_month)
        else:
            prev_transactions = load_transactions(compare_path)
        if prev_transactions:
            prev_label = infer_label(prev_transactions).split()[0]  # e.g. "March"

    avg_per_month, history_months = compute_monthly_category_averages(filepath)

    print(render_report(transactions, month_label, filepath, prev_transactions, prev_label,
                         avg_per_month, history_months))


if __name__ == "__main__":
    main()
