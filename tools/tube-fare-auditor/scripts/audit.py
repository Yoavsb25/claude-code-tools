#!/usr/bin/env python3
"""
TfL Oyster Fare Auditor
Parses Oyster journey history CSV(s) and a credit card statement CSV,
flags fare discrepancies, missing railcard discounts, and unmatched top-ups.

Fare verification strategy (in priority order):
  1. TfL Journey Planner API — exact fare for the specific route (live, cached 35 days)
  2. Zone-based fare table    — fallback when API is unavailable or station unknown
     Tables live in references/fare-config.json; update each March after fare increase.

Other config files:
  station-zones.json  — station → zone number (for fallback + unknown station warnings)
  railcard-types.json — railcard rules (discount %, peak eligibility, etc.)
"""

import argparse
import csv
import json
import math
import os
import re
import sys
from datetime import datetime, date
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
REFS_DIR = SKILL_DIR / "references"
sys.path.insert(0, str(Path(__file__).parent))

# Try to import the live fare fetcher
try:
    from fetch_fare import TflFareFetcher
    _FETCHER_AVAILABLE = True
except ImportError:
    _FETCHER_AVAILABLE = False


def load_json(name: str) -> dict:
    path = REFS_DIR / name
    with open(path) as f:
        return json.load(f)


# ── Config loading ────────────────────────────────────────────────────────────

def load_fare_config() -> dict:
    return load_json("fare-config.json")

def load_station_zones() -> dict:
    data = load_json("station-zones.json")
    # Build a normalised lookup: lowercase name → zone
    lookup = {}
    for name, zone in data["stations"].items():
        lookup[name.lower().strip()] = zone
    outside = {s.lower() for s in data.get("_outside_oyster", [])}
    return lookup, outside

def load_railcard_rules() -> dict:
    data = load_json("railcard-types.json")
    # Build alias → rule mapping
    rules = {}
    for key, rule in data["railcards"].items():
        rules[key.lower()] = rule
        for alias in rule.get("id_aliases", []):
            rules[alias.lower()] = rule
    return rules


# ── Fare calculation ──────────────────────────────────────────────────────────

def get_fare_period(fare_config: dict, dt: datetime | None) -> dict | None:
    """Return the fare period dict that was active on the given date."""
    if dt is None:
        # Use the most recent period
        return fare_config["fare_periods"][0]
    d = dt.date()
    for period in fare_config["fare_periods"]:
        start = date.fromisoformat(period["effective_from"])
        end_str = period.get("effective_until")
        end = date.fromisoformat(end_str) if end_str else date(9999, 12, 31)
        if start <= d <= end:
            return period
    return fare_config["fare_periods"][-1]  # fallback to oldest


def is_peak(fare_config: dict, dt: datetime) -> bool:
    """Return True if datetime is a TfL peak period."""
    if dt.weekday() >= 5:  # Weekend → always off-peak
        return False
    t = (dt.hour, dt.minute)
    for window in fare_config["peak_hours"]["windows"]:
        sh, sm = [int(x) for x in window["start"].split(":")]
        eh, em = [int(x) for x in window["end"].split(":")]
        if (sh, sm) <= t <= (eh, em):
            return True
    return False


def calc_expected_fare(
    fare_config: dict,
    z_min: int, z_max: int,
    peak: bool,
    railcard_rule: dict | None,
    dt: datetime | None = None
) -> float | None:
    period = get_fare_period(fare_config, dt)
    table = period["peak"] if peak else period["off_peak"]
    key = f"{z_min}-{z_max}"
    if key not in table:
        return None
    fare = table[key]
    if railcard_rule:
        # Check if railcard applies at this time of day
        if peak and not railcard_rule.get("applies_peak", True):
            pass  # Railcard doesn't apply at peak; use full fare
        elif not peak and not railcard_rule.get("applies_off_peak", True):
            pass  # Unusual, but handle anyway
        else:
            discount = railcard_rule["discount_fraction"]
            min_fare = railcard_rule.get("min_fare_gbp", 0.0)
            fare = max(fare * (1 - discount), min_fare)
            fare = math.floor(fare * 20) / 20  # round down to nearest 5p
    return round(fare, 2)


# ── Station zone lookup ───────────────────────────────────────────────────────

def station_zone(name: str, zone_lookup: dict, outside_oyster: set) -> tuple[int | None, str]:
    """
    Returns (zone_number, status) where status is:
      'found'   — zone confidently identified
      'outside' — station known to be outside Oyster zone
      'unknown' — station not in our database
    """
    raw = name.lower().strip()
    # Strip bracketed qualifiers like "(Piccadilly, Victoria lines)" or "[National Rail]"
    cleaned = re.sub(r'\s*[\(\[].*', '', raw).strip()

    # Try exact match first
    if cleaned in zone_lookup:
        return zone_lookup[cleaned], "found"
    if raw in zone_lookup:
        return zone_lookup[raw], "found"

    # Check outside list
    if any(o in cleaned for o in outside_oyster):
        return None, "outside"

    # Partial / prefix match — e.g. "kings cross" matches "king's cross st. pancras"
    for key, zone in zone_lookup.items():
        if cleaned in key or key in cleaned:
            return zone, "found"

    # Common abbreviations
    abbr_map = {
        "kx": "king's cross st. pancras",
        "kings x": "king's cross st. pancras",
        "victoria line": "victoria",
        "st pancras": "st pancras international",
        "heathrow t5": "heathrow terminal 5",
        "heathrow t4": "heathrow terminal 4",
        "heathrow t1": "heathrow terminal 1",
        "heathrow t2": "heathrow terminal 2",
        "heathrow t3": "heathrow terminal 3",
    }
    for abbr, full in abbr_map.items():
        if abbr in cleaned:
            if full in zone_lookup:
                return zone_lookup[full], "found"

    return None, "unknown"


def parse_journey_stations(journey_str: str) -> tuple[str | None, str | None]:
    """Extract (origin, destination) from 'A to B (lines)' format."""
    m = re.match(r'^(.+?)\s+to\s+(.+?)(?:\s*[\(\[].*)?$', journey_str, re.IGNORECASE)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return None, None


# ── CSV parsing ───────────────────────────────────────────────────────────────

def parse_amount(s: str) -> float:
    if not s:
        return 0.0
    s = s.replace('£', '').replace(',', '').strip()
    try:
        return float(s)
    except ValueError:
        return 0.0


def parse_oyster_csv(filepath: str) -> list[dict]:
    records = []
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        lines = [line for line in f if line.strip()]
    reader = csv.DictReader(lines)
    for row in reader:
        rec = {(k.strip() if k else ''): (v.strip() if v else '') for k, v in row.items() if k}
        date_str = rec.get('Date', '')
        time_str = rec.get('Start Time', '')
        dt = None
        if date_str and time_str:
            for fmt in ("%d-%b-%Y %H:%M", "%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M"):
                try:
                    dt = datetime.strptime(f"{date_str} {time_str}", fmt)
                    break
                except ValueError:
                    pass
        if dt is None and date_str:
            for fmt in ("%d-%b-%Y", "%d/%m/%Y", "%Y-%m-%d"):
                try:
                    dt = datetime.strptime(date_str, fmt)
                    break
                except ValueError:
                    pass
        rec['_datetime'] = dt
        rec['_charge'] = parse_amount(rec.get('Charge', ''))
        rec['_credit'] = parse_amount(rec.get('Credit', ''))
        rec['_source_file'] = os.path.basename(filepath)
        records.append(rec)
    return records


TFL_MERCHANT_KEYWORDS = {
    "tfl", "transport for london", "heathrow express",
    "london underground", "oyster", "st. pancras international",
    "st pancras international", "heathrow t", "kings cross station",
    "victoria station", "euston station", "paddington station",
    "unpaid fares",
}


def is_tfl_charge(merchant: str) -> bool:
    ml = merchant.lower()
    return any(k in ml for k in TFL_MERCHANT_KEYWORDS)


def parse_card_csv(filepath: str) -> list[dict]:
    """Parse a bank/card statement CSV. Handles Wise, Monzo, and generic formats."""
    records = []
    with open(filepath, newline='', encoding='utf-8-sig') as f:
        lines = [line for line in f if line.strip()]
    reader = csv.DictReader(lines)
    headers = reader.fieldnames or []

    # Detect format
    is_wise = any('source amount' in h.lower() for h in headers)
    is_monzo = any('monzo' in h.lower() or 'local amount' in h.lower() for h in headers)

    for row in reader:
        rec = {(k.strip() if k else ''): (v.strip() if v else '') for k, v in row.items() if k}

        # Parse datetime
        dt = None
        for field in ['Created on', 'Date', 'Transaction Date', 'date']:
            raw = rec.get(field, '')
            if raw:
                for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d", "%d/%m/%Y", "%d-%b-%Y", "%d %b %Y"):
                    try:
                        dt = datetime.strptime(raw[:19], fmt)
                        break
                    except ValueError:
                        pass
                if dt:
                    break

        # Parse merchant
        merchant = ''
        for field in ['Target name', 'Merchant', 'Description', 'Payee', 'Name', 'merchant']:
            val = rec.get(field, '').strip()
            if val:
                merchant = val
                break

        # Parse GBP amount (positive = money out)
        amount_gbp = None
        currency = rec.get('Source currency', rec.get('Currency', 'GBP')).strip().upper()

        if is_wise:
            raw = rec.get('Source amount (after fees)', '')
            if raw:
                try:
                    amount_gbp = abs(float(raw)) if currency == 'GBP' else None
                except ValueError:
                    pass
        elif is_monzo:
            raw = rec.get('Amount', rec.get('amount', ''))
            if raw:
                try:
                    val = float(raw.replace('£', '').replace(',', ''))
                    amount_gbp = abs(val) if val < 0 else None  # Monzo: negative = debit
                except ValueError:
                    pass
        else:
            for field in ['Amount', 'Debit', 'Withdrawal', 'Credit Debit Amount']:
                raw = rec.get(field, '').replace('£', '').replace(',', '').strip()
                if raw:
                    try:
                        amount_gbp = abs(float(raw))
                        break
                    except ValueError:
                        pass

        direction = rec.get('Direction', '').upper()
        # For generic formats, infer direction from sign or column name
        if not direction:
            if 'Debit' in headers and rec.get('Debit', ''):
                direction = 'OUT'
            elif amount_gbp is not None:
                direction = 'OUT'  # assume outgoing if we got an amount

        rec['_datetime'] = dt
        rec['_merchant'] = merchant
        rec['_amount_gbp'] = amount_gbp
        rec['_direction'] = direction
        records.append(rec)
    return records


# ── Main audit logic ──────────────────────────────────────────────────────────

def run_audit(
    oyster_files: list[str],
    card_file: str | None,
    railcard_key: str | None,
    output_dir: str,
    tfl_api_key: str | None = None,
) -> dict:
    os.makedirs(output_dir, exist_ok=True)

    fare_config = load_fare_config()
    zone_lookup, outside_oyster = load_station_zones()
    all_railcard_rules = load_railcard_rules()

    railcard_rule = None
    railcard_name = "None"
    if railcard_key:
        railcard_rule = all_railcard_rules.get(railcard_key.lower())
        if railcard_rule:
            railcard_name = railcard_rule["name"]
        else:
            print(f"⚠️  Unknown railcard '{railcard_key}'. Supported: {', '.join(set(r['name'] for r in all_railcard_rules.values()))}")

    all_oyster = []
    for f in oyster_files:
        records = parse_oyster_csv(f)
        all_oyster.extend(records)
        print(f"  Loaded {len(records)} rows from {os.path.basename(f)}")

    card_records = parse_card_csv(card_file) if card_file else []

    results = {
        "fare_flags": [],
        "incomplete_journeys": [],
        "top_up_matching": [],
        "unmatched_card_charges": [],
        "unknown_stations": [],
        "summary": {},
    }

    total_charged = 0.0
    total_potential_overcharge = 0.0
    journey_count = 0
    api_hits = 0
    api_misses = 0

    FARE_TOLERANCE = 0.10  # 10p — rounding varies slightly between systems

    # Initialise live fare fetcher if available
    fetcher = TflFareFetcher(api_key=tfl_api_key) if _FETCHER_AVAILABLE else None
    if fetcher:
        key_status = "authenticated" if tfl_api_key else "unauthenticated — throttled routes fall back to zone estimates"
        print(f"  Live TfL fare API: enabled [{key_status}]")
    else:
        print("  Live TfL fare API: unavailable — using zone-based fare table fallback")

    # ── 1. Fare audit ────────────────────────────────────────────────────────
    for rec in all_oyster:
        journey = rec.get('Journey/Action', '')
        charge = rec['_charge']
        dt = rec['_datetime']
        note = rec.get('Note', '').lower()

        # Skip non-journey rows
        if rec['_credit'] > 0:
            continue
        if 'topped up' in journey.lower():
            continue
        if not journey.strip():
            continue

        # Bus journeys
        if 'bus journey' in journey.lower():
            expected_bus = fare_config.get("bus_fare", 1.75)
            if charge > 0 and abs(charge - expected_bus) > FARE_TOLERANCE and 'daily cap' not in note:
                results["fare_flags"].append({
                    "type": "bus_wrong_fare",
                    "date": rec.get('Date'), "time": rec.get('Start Time'),
                    "journey": journey, "actual_charge": charge,
                    "expected_charge": expected_bus,
                    "difference": round(charge - expected_bus, 2),
                    "source_file": rec['_source_file'],
                    "explanation": f"Bus fare should be £{expected_bus:.2f} flat rate. Charged £{charge:.2f}."
                })
            total_charged += charge
            continue

        # Tube / rail journey
        if ' to ' not in journey.lower():
            total_charged += charge
            continue

        journey_count += 1
        total_charged += charge

        # Daily cap — skip fare check (correct behaviour)
        if 'daily cap' in note:
            continue

        origin_str, dest_str = parse_journey_stations(journey)
        if not origin_str or not dest_str:
            continue

        origin_zone, origin_status = station_zone(origin_str, zone_lookup, outside_oyster)
        dest_zone, dest_status = station_zone(dest_str, zone_lookup, outside_oyster)

        # Outside Oyster zone — flag separately
        if origin_status == 'outside' or dest_status == 'outside':
            results["fare_flags"].append({
                "type": "outside_oyster_zone",
                "date": rec.get('Date'), "time": rec.get('Start Time'),
                "journey": journey, "actual_charge": charge,
                "expected_charge": None, "difference": None,
                "source_file": rec['_source_file'],
                "explanation": "One or both stations are outside the standard Oyster zone (e.g. Gatwick, Luton). Fare cannot be auto-verified — check manually."
            })
            continue

        peak = is_peak(fare_config, dt) if dt else None
        period_label = ("peak" if peak else "off-peak") if peak is not None else "unknown period"
        fare_source = "zone-table"

        # ── Strategy 1: Live TfL API ──────────────────────────────────────────
        exp_adult = None
        exp_with_railcard = None

        if fetcher and origin_status != 'unknown' and dest_status != 'unknown' and peak is not None:
            try:
                api_adult = fetcher.get_fare(origin_str, dest_str, peak, dt)
                if api_adult is not None:
                    exp_adult = api_adult
                    if railcard_rule:
                        exp_with_railcard = fetcher.apply_railcard(api_adult, railcard_rule, peak)
                        if exp_with_railcard is None:
                            # Railcard doesn't apply at this time; full fare is correct
                            exp_with_railcard = api_adult
                    else:
                        exp_with_railcard = api_adult
                    fare_source = "tfl-api"
                    api_hits += 1
                else:
                    api_misses += 1
            except Exception:
                api_misses += 1

        # ── Strategy 2: Zone-based fallback ──────────────────────────────────
        if exp_with_railcard is None:
            if origin_status == 'unknown' or dest_status == 'unknown':
                unknown = [s for s, st in [(origin_str, origin_status), (dest_str, dest_status)] if st == 'unknown']
                results["unknown_stations"].append({
                    "journey": journey, "date": rec.get('Date'),
                    "unknown": unknown,
                    "note": "Station not in zone database and API lookup unavailable. Add to station-zones.json or check tfl.gov.uk/maps."
                })
                continue

            z_min = min(origin_zone, dest_zone)
            z_max = max(origin_zone, dest_zone)

            if peak is not None:
                exp_adult = calc_expected_fare(fare_config, z_min, z_max, peak, None, dt)
                exp_with_railcard = calc_expected_fare(fare_config, z_min, z_max, peak, railcard_rule, dt)
            else:
                # Time unknown — try both periods
                for is_pk, lbl in [(True, "peak"), (False, "off-peak")]:
                    ea = calc_expected_fare(fare_config, z_min, z_max, is_pk, None, dt)
                    erc = calc_expected_fare(fare_config, z_min, z_max, is_pk, railcard_rule, dt)
                    if erc and abs(charge - erc) <= FARE_TOLERANCE:
                        exp_adult, exp_with_railcard, period_label = ea, erc, lbl
                        break
                else:
                    exp_adult = calc_expected_fare(fare_config, z_min, z_max, False, None, dt)
                    exp_with_railcard = calc_expected_fare(fare_config, z_min, z_max, False, railcard_rule, dt)

        if exp_with_railcard is None:
            continue

        if origin_status == 'unknown' or dest_status == 'unknown':
            unknown = [s for s, st in [(origin_str, origin_status), (dest_str, dest_status)] if st == 'unknown']
            results["unknown_stations"].append({
                "journey": journey, "date": rec.get('Date'),
                "unknown": unknown,
                "note": "Could not find zone for this station. Add it to station-zones.json or check tfl.gov.uk/maps."
            })
            continue

        diff = round(charge - exp_with_railcard, 2)

        if abs(diff) > FARE_TOLERANCE:
            # Determine the most likely reason
            if exp_adult and abs(charge - exp_adult) <= FARE_TOLERANCE and railcard_rule:
                # Charged full adult fare when railcard should apply
                flag_type = "railcard_discount_missing"
                applies_peak = railcard_rule.get("applies_peak", True)
                if peak and not applies_peak:
                    explanation = (
                        f"Your {railcard_name} does NOT give a discount during peak hours — "
                        f"so the full adult fare (£{exp_adult:.2f}) is actually correct for this journey."
                    )
                    flag_type = "railcard_peak_restriction_note"
                else:
                    explanation = (
                        f"Charged £{charge:.2f} — this matches the full adult fare (£{exp_adult:.2f}). "
                        f"With your {railcard_name}, you should pay ~£{exp_with_railcard:.2f}. "
                        f"Potential overcharge: £{round(diff, 2):.2f}."
                    )
                    total_potential_overcharge += diff
            else:
                flag_type = "fare_mismatch"
                explanation = (
                    f"Charged £{charge:.2f} but expected ~£{exp_with_railcard:.2f} ({period_label}, "
                    f"zones {z_min}–{z_max}). Adult fare would be £{exp_adult:.2f}. "
                    f"Difference: £{diff:.2f}. Verify this journey manually."
                )

            results["fare_flags"].append({
                "type": flag_type,
                "date": rec.get('Date'), "time": rec.get('Start Time'),
                "journey": journey,
                "origin_zone": origin_zone, "dest_zone": dest_zone,
                "period": period_label,
                "actual_charge": charge,
                "expected_with_railcard": exp_with_railcard,
                "expected_adult": exp_adult,
                "difference": diff,
                "explanation": explanation,
                "source_file": rec['_source_file'],
            })

    # ── 2. Incomplete journey detection ──────────────────────────────────────
    for rec in all_oyster:
        journey = rec.get('Journey/Action', '')
        charge = rec['_charge']
        note = rec.get('Note', '').lower()
        if re.match(r'^entered\b', journey, re.IGNORECASE) and 'to' not in journey.lower():
            results["incomplete_journeys"].append({
                "date": rec.get('Date'), "time": rec.get('Start Time'),
                "journey": journey, "charge": charge, "note": note,
                "source_file": rec['_source_file'],
                "action": "Claim incomplete journey refund at tfl.gov.uk/contact or at any tube station (within 8 weeks)."
            })
            total_potential_overcharge += charge

    # ── 3. Top-up to card statement matching ─────────────────────────────────
    top_ups = [
        r for r in all_oyster
        if 'topped up' in r.get('Journey/Action', '').lower() and r['_credit'] > 0
    ]
    tfl_card_charges = [
        r for r in card_records
        if r['_direction'] == 'OUT'
        and r['_amount_gbp'] is not None
        and is_tfl_charge(r.get('_merchant', ''))
    ]
    used_card_idx = set()

    for top_up in top_ups:
        amount = top_up['_credit']
        tu_dt = top_up['_datetime']
        matched = None
        matched_idx = None

        for i, card_rec in enumerate(tfl_card_charges):
            if i in used_card_idx:
                continue
            if abs(card_rec['_amount_gbp'] - amount) > 0.05:
                continue
            if tu_dt and card_rec['_datetime']:
                delta_days = abs((card_rec['_datetime'] - tu_dt).total_seconds()) / 86400
                if delta_days <= 3:
                    matched = card_rec
                    matched_idx = i
                    break
            else:
                matched = card_rec
                matched_idx = i
                break

        location = top_up.get('Journey/Action', '').replace('Topped up,', '').replace('Topped up', '').strip().strip(',').strip()
        merchant = matched['_merchant'] if matched else None
        note = None
        if merchant and 'heathrow express' in merchant.lower():
            note = "Oyster top-ups at Heathrow stations appear as 'Heathrow Express' on card statements — this is normal."

        results["top_up_matching"].append({
            "oyster_date": top_up.get('Date'),
            "oyster_time": top_up.get('Start Time'),
            "location": location,
            "amount": amount,
            "card_date": matched['_datetime'].strftime('%Y-%m-%d %H:%M') if matched and matched['_datetime'] else None,
            "card_merchant": merchant,
            "status": "matched" if matched else "unmatched_on_card",
            "note": note,
            "source_file": top_up['_source_file'],
        })
        if matched_idx is not None:
            used_card_idx.add(matched_idx)

    for i, card_rec in enumerate(tfl_card_charges):
        if i not in used_card_idx:
            merchant = card_rec.get('_merchant', '')
            is_penalty = 'unpaid' in merchant.lower() or 'penalty' in merchant.lower()
            results["unmatched_card_charges"].append({
                "date": card_rec['_datetime'].strftime('%Y-%m-%d %H:%M') if card_rec['_datetime'] else None,
                "merchant": merchant,
                "amount": card_rec['_amount_gbp'],
                "type": "penalty_fare" if is_penalty else "tfl_charge_no_matching_topup",
                "note": (
                    "PENALTY: TfL charged your card directly for an unpaid or incomplete journey fare."
                    if is_penalty else
                    "TfL charge on card with no matching Oyster top-up. May be from a period not covered by your CSV, or paid via auto-top-up from a different card."
                )
            })

    # ── Summary ───────────────────────────────────────────────────────────────
    results["summary"] = {
        "total_journeys_audited": journey_count,
        "total_charged_gbp": round(total_charged, 2),
        "fare_flags_count": len(results["fare_flags"]),
        "railcard_missing_count": len([f for f in results["fare_flags"] if f.get("type") == "railcard_discount_missing"]),
        "outside_oyster_zone_count": len([f for f in results["fare_flags"] if f.get("type") == "outside_oyster_zone"]),
        "incomplete_journeys_count": len(results["incomplete_journeys"]),
        "unknown_stations_count": len(results["unknown_stations"]),
        "top_ups_matched": len([t for t in results["top_up_matching"] if t["status"] == "matched"]),
        "top_ups_unmatched": len([t for t in results["top_up_matching"] if t["status"] != "matched"]),
        "unmatched_card_charges_count": len(results["unmatched_card_charges"]),
        "potential_overcharge_gbp": round(total_potential_overcharge, 2),
        "railcard": railcard_name,
        "fare_verification": "tfl-api" if api_hits > 0 else "zone-table",
        "api_fares_fetched": api_hits,
        "api_misses": api_misses,
    }

    # Write output
    out_path = Path(output_dir) / "audit_results.json"
    with open(out_path, 'w') as f:
        json.dump(results, f, indent=2, default=str)

    # Print summary
    s = results["summary"]
    print(f"\n✅ Audit complete → {out_path}")
    print(f"\n📊 Summary:")
    print(f"   Journeys audited:       {s['total_journeys_audited']}")
    print(f"   Total charged:          £{s['total_charged_gbp']:.2f}")
    print(f"   Railcard:               {s['railcard']}")
    print(f"   Fare flags:             {s['fare_flags_count']} ({s['railcard_missing_count']} railcard-missing, {s['outside_oyster_zone_count']} outside-zone)")
    print(f"   Incomplete journeys:    {s['incomplete_journeys_count']}")
    print(f"   Unknown stations:       {s['unknown_stations_count']}")
    print(f"   Top-ups matched:        {s['top_ups_matched']} / {s['top_ups_matched'] + s['top_ups_unmatched']}")
    print(f"   Unmatched card charges: {s['unmatched_card_charges_count']}")
    print(f"\n💷 Potential overcharge:  £{s['potential_overcharge_gbp']:.2f}")
    print(f"   Fare source:          {s['fare_verification']} ({s['api_fares_fetched']} live, {s['api_misses']} fallback)")
    if fetcher:
        print(f"   {fetcher.stats()}")
        print(f"   Cache: ~/.cache/tfl-fare-auditor/")

    if results["fare_flags"]:
        print(f"\n⚠️  Fare flags:")
        for flag in results["fare_flags"]:
            marker = "❌" if flag["type"] == "railcard_discount_missing" else "⚠️ "
            print(f"   {marker} [{flag['type']}] {flag.get('date')} {flag.get('time')} — {flag.get('journey', '')[:55]} — £{flag.get('actual_charge')}")

    if results["unknown_stations"]:
        print(f"\n❓ Unknown stations (add to station-zones.json):")
        for u in results["unknown_stations"]:
            print(f"   {u['unknown']} — in journey: {u['journey'][:60]}")

    return results


def main():
    parser = argparse.ArgumentParser(description='TfL Oyster Fare Auditor')
    parser.add_argument('--oyster', action='append', required=True,
                        help='Oyster journey history CSV path (repeat for multiple cards)')
    parser.add_argument('--statement', default=None,
                        help='Bank/card statement CSV path')
    parser.add_argument('--railcard', default=None,
                        help='Railcard type, e.g. "26-30", "two-together", "senior"')
    parser.add_argument('--output', default='/tmp/tube_audit_output',
                        help='Output directory for audit_results.json')
    parser.add_argument('--tfl-api-key', default=os.environ.get('TFL_API_KEY'),
                        help='TfL API key for higher rate limits (free at api.tfl.gov.uk/registration). '
                             'Can also be set via TFL_API_KEY env var. Without a key, '
                             'first-run fare lookups fall back to zone-based estimates.')
    args = parser.parse_args()
    run_audit(args.oyster, args.statement, args.railcard, args.output, args.tfl_api_key)


if __name__ == '__main__':
    main()
