#!/usr/bin/env python3
"""
Expense analyzer for Wise CSV exports.
Usage: python analyze.py <csv_path> [--month YYYY-MM] [--compare <prev_csv_path>]
Outputs a markdown report to stdout.
"""

import csv
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


def load_transactions(filepath, month_filter=None):
    rows_by_id = defaultdict(list)
    ungrouped = []

    with open(filepath, newline="", encoding="utf-8-sig") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("Direction") != "OUT":
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
        tx_date = parse_date(row.get("Created on", ""))
        if month_filter and tx_date:
            if tx_date.strftime("%Y-%m") != month_filter:
                continue
        try:
            amount = float(row.get("Source amount (after fees)", 0) or 0)
        except (ValueError, TypeError):
            amount = 0.0
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


def infer_label(transactions):
    dates = [tx["date"] for tx in transactions if tx["date"]]
    if not dates:
        return "All Transactions"
    first, last = min(dates), max(dates)
    if first.month == last.month and first.year == last.year:
        return first.strftime("%B %Y")
    return f"{first.strftime('%d %b %Y')} – {last.strftime('%d %b %Y')}"


def render_report(transactions, month_label, filepath, prev_transactions=None, prev_label=None):
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

    lines = [
        f"# Expense Report — {month_label}",
        "",
        f"**Source:** `{filepath}`  ",
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
            f"| Category | Total | vs {prev_label} | # | Avg |",
            "|----------|------:|----------:|--:|----:|",
        ]
        for cat, txs in cat_order:
            cat_total = sum(t["amount_gbp"] for t in txs)
            cat_avg = cat_total / len(txs)
            prev = prev_totals.get(cat, 0.0)
            delta = cat_total - prev
            sign = "+" if delta >= 0 else ""
            lines.append(
                f"| {cat} | £{cat_total:,.2f} | {sign}£{delta:,.2f} | {len(txs)} | £{cat_avg:.2f} |"
            )
    else:
        lines += [
            "| Category | Total | # | Avg |",
            "|----------|------:|--:|----:|",
        ]
        for cat, txs in cat_order:
            cat_total = sum(t["amount_gbp"] for t in txs)
            cat_avg = cat_total / len(txs)
            lines.append(f"| {cat} | £{cat_total:,.2f} | {len(txs)} | £{cat_avg:.2f} |")

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
        print("Usage: analyze.py <csv_path> [--month YYYY-MM] [--compare <prev_csv_path>]", file=sys.stderr)
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

    transactions = load_transactions(filepath, month_filter)

    if month_filter:
        month_label = datetime.strptime(month_filter, "%Y-%m").strftime("%B %Y")
    elif transactions:
        month_label = infer_label(transactions)
    else:
        month_label = "All Transactions"

    prev_transactions = None
    prev_label = None
    if compare_path:
        prev_transactions = load_transactions(compare_path)
        if prev_transactions:
            prev_label = infer_label(prev_transactions).split()[0]  # e.g. "March"

    print(render_report(transactions, month_label, filepath, prev_transactions, prev_label))


if __name__ == "__main__":
    main()
