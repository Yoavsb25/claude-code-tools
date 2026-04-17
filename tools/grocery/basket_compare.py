#!/usr/bin/env python3
"""
basket_compare.py — Compare grocery basket prices across Tesco, Ocado, and Waitrose.

Usage:
    python basket_compare.py                     # reads list from stdin
    python basket_compare.py --file list.txt     # reads list from a file
    python basket_compare.py --file list.txt --save   # also saves a .md report
"""

import argparse
import asyncio
import re
import sys
from datetime import date

from scraper import scrape_all
from matcher import match_items, rematch_ambiguous, CONFIDENCE_THRESHOLD
from renderer import render_table


def parse_shopping_list(text: str) -> list[dict]:
    """
    Parse a free-form shopping list into [{"item": str, "qty": int}].

    Supported quantity prefixes:  2x, 2 x, 2X  (case-insensitive)
    Bullet/list markers stripped: -, *, •, digits followed by . or )

    If a line has no explicit quantity, qty defaults to 1.
    If quantity is ambiguous (e.g. "a few apples"), qty=1 and a note is shown.
    """
    items = []
    for line in text.strip().splitlines():
        line = line.strip()
        # Strip common list markers
        line = re.sub(r"^[-*•]|^\d+[.)]\s*", "", line).strip()
        if not line:
            continue

        qty = 1
        qty_match = re.match(r"^(\d+)\s*[xX]\s+(.+)$", line)
        if qty_match:
            qty = int(qty_match.group(1))
            line = qty_match.group(2).strip()

        items.append({"item": line, "qty": qty})

    return items


async def run(list_text: str, save: bool) -> None:
    items = parse_shopping_list(list_text)
    if not items:
        print("No items found in the shopping list. Exiting.")
        sys.exit(1)

    print(f"Parsed {len(items)} item{'s' if len(items) != 1 else ''}:")
    for i in items:
        qty_label = f" ×{i['qty']}" if i["qty"] > 1 else ""
        print(f"  • {i['item']}{qty_label}")

    print("\nScraping prices (this takes ~30–60 s)…\n")
    candidates = await scrape_all([i["item"] for i in items])

    # Warn about items with no candidates from any retailer
    for i in items:
        if not candidates.get(i["item"]):
            print(f"  ⚠  No results found for '{i['item']}' — it will show as N/A.")

    print("Matching items to products…")
    matches = match_items(items, candidates)

    # Clarification pass for low-confidence matches
    ambiguous = [
        m for m in matches
        if m.get("confidence", 1.0) < CONFIDENCE_THRESHOLD
        and m.get("clarification_question")
    ]

    if ambiguous:
        # Group by item (one question per item, not per item-retailer pair)
        item_questions: dict[str, str] = {}
        for m in ambiguous:
            if m["item"] not in item_questions:
                item_questions[m["item"]] = m["clarification_question"]

        print(f"\n{len(item_questions)} item(s) need clarification:\n")
        answers: dict[str, str] = {}
        for idx, (item_name, question) in enumerate(item_questions.items(), 1):
            answer = input(f"  [{idx}] {question} ").strip()
            answers[item_name] = answer or "no preference"

        print("\nRe-matching ambiguous items with your answers…")
        matches = rematch_ambiguous(matches, candidates, answers)

    print()
    output = render_table(items, matches)
    print(output)

    if save:
        filename = f"basket-comparison-{date.today().isoformat()}.md"
        with open(filename, "w") as f:
            f.write(output)
        print(f"\nReport saved to {filename}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compare grocery prices across Tesco, Ocado, and Waitrose."
    )
    parser.add_argument("--file", help="Path to a shopping list file (default: stdin)")
    parser.add_argument(
        "--save",
        action="store_true",
        help="Save the comparison table to basket-comparison-YYYY-MM-DD.md",
    )
    args = parser.parse_args()

    if args.file:
        with open(args.file) as f:
            text = f.read()
    else:
        print("Paste your shopping list, then press Ctrl+D:\n")
        text = sys.stdin.read()

    asyncio.run(run(text, args.save))


if __name__ == "__main__":
    main()
