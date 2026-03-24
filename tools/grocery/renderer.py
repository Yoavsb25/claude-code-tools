"""
renderer.py — Renders a markdown price comparison table from match data.
"""

from typing import Optional

RETAILERS = ["tesco", "ocado", "waitrose"]
RETAILER_LABELS = {"tesco": "Tesco", "ocado": "Ocado", "waitrose": "Waitrose"}

# A retailer is excluded from the cheapest-basket recommendation if it has
# this many or more N/A items (scraper miss OR matcher null).
NA_EXCLUSION_THRESHOLD = 2


def render_table(items: list[dict], matches: list[dict]) -> str:
    """
    Build a markdown comparison table.

    items   — [{"item": str, "qty": int}, ...]
    matches — [{"item": str, "retailer": str, "price": float|None,
                "unit_price": str|None, "matched_product": str|None,
                "confidence": float, ...}, ...]
    """
    # Build fast lookup: {item_name: {retailer: match}}
    lookup: dict[str, dict[str, dict]] = {}
    for m in matches:
        lookup.setdefault(m["item"], {})[m["retailer"]] = m

    qty_map = {i["item"]: i["qty"] for i in items}

    # Cost per item per retailer (price × qty), or None if unavailable
    costs: dict[str, dict[str, Optional[float]]] = {}
    for item_dict in items:
        name = item_dict["item"]
        qty = item_dict["qty"]
        costs[name] = {}
        for retailer in RETAILERS:
            match = lookup.get(name, {}).get(retailer, {})
            price = match.get("price")
            costs[name][retailer] = round(price * qty, 2) if price else None

    # Count N/A items per retailer
    na_counts = {r: 0 for r in RETAILERS}
    for item_costs in costs.values():
        for retailer, cost in item_costs.items():
            if cost is None:
                na_counts[retailer] += 1

    # Retailers eligible for cheapest-basket comparison
    eligible = [r for r in RETAILERS if na_counts[r] < NA_EXCLUSION_THRESHOLD]

    # Totals — partial sum even when some items are N/A (noted with *)
    totals: dict[str, Optional[float]] = {}
    has_gap: dict[str, bool] = {}
    for retailer in RETAILERS:
        partial = 0.0
        gap = False
        for item_dict in items:
            c = costs[item_dict["item"]][retailer]
            if c is None:
                gap = True
            else:
                partial += c
        totals[retailer] = round(partial, 2) if partial > 0 else None
        has_gap[retailer] = gap

    # Cheapest basket (among eligible retailers)
    cheapest_basket: Optional[str] = None
    eligible_totals = {r: totals[r] for r in eligible if totals.get(r) is not None}
    if eligible_totals:
        cheapest_basket = min(eligible_totals, key=lambda r: eligible_totals[r])

    # --- Column widths ---
    item_col_w = max(
        len("Item"),
        max(
            len(f"{i['item']} ×{i['qty']}" if i["qty"] > 1 else i["item"])
            for i in items
        ),
    )
    retailer_col_w = {r: max(len(RETAILER_LABELS[r]), 10) for r in RETAILERS}
    cheapest_col_w = max(len("Cheapest"), max(len(RETAILER_LABELS[r]) for r in RETAILERS))

    def fmt(cost: Optional[float], gap: bool = False, trophy: bool = False) -> str:
        if cost is None:
            s = "N/A"
        else:
            s = f"£{cost:.2f}"
            if gap:
                s += "*"
            if trophy:
                s += " 🏆"
        return s

    def row(*cells: str) -> str:
        parts = [f"{cells[0]:<{item_col_w}}"]
        for i, retailer in enumerate(RETAILERS):
            parts.append(f"{cells[i + 1]:<{retailer_col_w[retailer]}}")
        parts.append(f"{cells[-1]:<{cheapest_col_w}}")
        return " | ".join(parts)

    header = row(
        "Item",
        *[RETAILER_LABELS[r] for r in RETAILERS],
        "Cheapest",
    )
    divider = "-" * len(header)

    lines = [header, divider]

    for item_dict in items:
        name = item_dict["item"]
        qty = item_dict["qty"]
        label = f"{name} ×{qty}" if qty > 1 else name

        # Per-item cheapest (among eligible retailers with a price)
        item_eligible_prices = {
            r: costs[name][r]
            for r in eligible
            if costs[name][r] is not None
        }
        cheapest_item = (
            min(item_eligible_prices, key=lambda r: item_eligible_prices[r])
            if item_eligible_prices
            else None
        )

        cells = []
        for retailer in RETAILERS:
            cost = costs[name][retailer]
            cell = fmt(cost)
            if retailer == cheapest_item and cost is not None:
                cell += " ✓"
            cells.append(cell)

        cheapest_label = RETAILER_LABELS.get(cheapest_item, "") if cheapest_item else ""
        lines.append(row(label, *cells, cheapest_label))

    lines.append(divider)

    # Totals row
    total_cells = []
    for retailer in RETAILERS:
        cell = fmt(
            totals[retailer],
            gap=has_gap[retailer],
            trophy=(retailer == cheapest_basket),
        )
        total_cells.append(cell)

    lines.append(row("TOTAL", *total_cells, ""))

    # Footnotes
    footnotes = []
    for retailer in RETAILERS:
        if has_gap[retailer]:
            n = na_counts[retailer]
            note = f"* {RETAILER_LABELS[retailer]} missing {n} item{'s' if n > 1 else ''}"
            if na_counts[retailer] >= NA_EXCLUSION_THRESHOLD:
                note += " — excluded from cheapest basket"
            footnotes.append(note)

    if footnotes:
        lines.append("")
        lines.extend(footnotes)

    return "\n".join(lines)
