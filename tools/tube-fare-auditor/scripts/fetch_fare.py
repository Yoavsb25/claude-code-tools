#!/usr/bin/env python3
"""
TfL fare fetcher with persistent caching.

Looks up the exact Oyster adult fare for a journey using the TfL Journey Planner API,
then caches results to avoid redundant API calls. Cache entries expire after 35 days
so they're automatically refreshed after each annual March fare increase.

Usage (from other scripts):
    from fetch_fare import TflFareFetcher
    fetcher = TflFareFetcher()
    fare = fetcher.get_fare("Paddington", "Brixton", peak=True)  # returns float or None
"""

import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta
from pathlib import Path

TFL_API_BASE = "https://api.tfl.gov.uk"
CACHE_DIR = Path.home() / ".cache" / "tfl-fare-auditor"
STOP_CACHE_FILE = CACHE_DIR / "stop_ids.json"
FARE_CACHE_FILE = CACHE_DIR / "fares.json"
CACHE_TTL_DAYS = 35  # refresh after 35 days to pick up annual fare changes

# A stable upcoming weekday for journey planner queries.
# The date itself doesn't matter — only the time (peak vs off-peak).
# We use a fixed Monday so results are reproducible within a cache cycle.
PROBE_DATE = "20260323"  # Monday 23 March 2026
PEAK_TIME = "0830"
OFFPEAK_TIME = "1100"

HEADERS = {"User-Agent": "TfL-Fare-Auditor/2.0", "Accept": "application/json"}

# Rate limiting: TfL's unauthenticated API throttles quickly on first run.
# A short delay between calls keeps us well under the limit; the persistent cache
# means only the first audit per station pair ever hits the network.
STOPPOINT_DELAY_S = 0.2        # delay between StopPoint/search calls (not heavily throttled)
JOURNEY_DELAY_S = 1.2          # delay between Journey Planner calls (strict rate limit without a key)
MAX_RETRIES = 3                # retries on 429 / transient errors
RETRY_BACKOFF_S = 3.0          # base back-off multiplier (doubles each retry)


class TflFareFetcher:
    def __init__(self, api_key: str | None = None):
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self._stop_cache = self._load_cache(STOP_CACHE_FILE)
        self._fare_cache = self._load_cache(FARE_CACHE_FILE)
        self._api_key = api_key
        self._request_count = 0
        self._last_request_time: float = 0.0
        self._journey_api_throttled: bool = False  # set True after first 429 on Journey Planner

    # ── Cache helpers ─────────────────────────────────────────────────────────

    def _load_cache(self, path: Path) -> dict:
        if path.exists():
            try:
                with open(path) as f:
                    return json.load(f)
            except (OSError, json.JSONDecodeError):
                pass
        return {}

    def _save_caches(self):
        try:
            with open(STOP_CACHE_FILE, 'w') as f:
                json.dump(self._stop_cache, f, indent=2)
            with open(FARE_CACHE_FILE, 'w') as f:
                json.dump(self._fare_cache, f, indent=2)
        except Exception as e:
            print(f"  [cache] Could not save cache: {e}")

    def _is_fresh(self, entry: dict) -> bool:
        cached_at = entry.get("cached_at")
        if not cached_at:
            return False
        age = datetime.now() - datetime.fromisoformat(cached_at)
        return age.days < CACHE_TTL_DAYS

    # ── API helpers ───────────────────────────────────────────────────────────

    def _api_get(self, path: str, params: dict | None = None) -> dict | None:
        url = f"{TFL_API_BASE}{path}"
        if self._api_key:
            params = params or {}
            params["app_key"] = self._api_key
        if params:
            url += "?" + urllib.parse.urlencode(params)
        # Defense-in-depth: ensure we only ever call the expected TfL host.
        # (Bandit may not be able to prove this automatically, but runtime is fail-closed.)
        parsed = urllib.parse.urlparse(url)
        if parsed.scheme != "https" or parsed.netloc != "api.tfl.gov.uk":
            return None
        req = urllib.request.Request(url, headers=HEADERS)

        # StopPoint searches use a different, lighter endpoint; Journey Planner is strictly throttled.
        is_journey = "/Journey/" in path
        delay = JOURNEY_DELAY_S if is_journey else STOPPOINT_DELAY_S

        # Unauthenticated calls hit a strict TfL quota (~50/30min).
        # Don't retry on 429 without a key — just fail fast so zone-table fallback kicks in.
        max_retries = MAX_RETRIES if self._api_key else 1

        for attempt in range(max_retries):
            # Enforce minimum gap between requests to avoid 429s
            elapsed = time.monotonic() - self._last_request_time
            if elapsed < delay:
                time.sleep(delay - elapsed)

            try:
                self._last_request_time = time.monotonic()
                with urllib.request.urlopen(req, timeout=15) as r:  # nosec: B310
                    self._request_count += 1
                    return json.loads(r.read())
            except urllib.error.HTTPError as e:
                if e.code in (404, 300):  # 300 = ambiguous stop, 404 = not found
                    return None
                if e.code == 429:
                    if is_journey:
                        self._journey_api_throttled = True
                        if not self._api_key:
                            print("  [tfl-api] Journey Planner throttled — falling back to zone estimates. "
                                  "Pass --tfl-api-key for exact fares (free at api.tfl.gov.uk/registration).")
                    if attempt + 1 < max_retries:
                        wait = RETRY_BACKOFF_S * (2 ** attempt)
                        print(f"  [tfl-api] Rate limited (429), waiting {wait:.0f}s before retry {attempt + 1}/{max_retries}...")
                        time.sleep(wait)
                        continue
                    return None  # Give up quietly — caller handles None
                print(f"  [tfl-api] HTTP {e.code} for {path}")
                return None
            except Exception as e:
                print(f"  [tfl-api] Error fetching {path}: {e}")
                return None

        return None

    # ── Stop ID resolution ────────────────────────────────────────────────────

    def resolve_stop(self, station_name: str) -> str | None:
        """Resolve a station name to its TfL NaptanId (cached)."""
        key = station_name.lower().strip()

        # Check cache
        if key in self._stop_cache:
            entry = self._stop_cache[key]
            if self._is_fresh(entry):
                return entry.get("naptan_id")

        # Clean up the station name for the API
        # Remove qualifiers like "(Met, Circle, H&C lines)" and "[National Rail]"
        import re
        clean = re.sub(r'\s*[\(\[].*', '', station_name).strip()

        data = self._api_get(
            f"/StopPoint/search/{urllib.parse.quote(clean)}",
            {"modes": "tube,dlr,overground,elizabeth-line,national-rail"}
        )
        if not data:
            return None

        matches = data.get("matches", [])
        # Prefer tube/underground matches
        best = None
        for m in matches:
            modes = m.get("modes", [])
            if "tube" in modes or "940GZZLU" in m.get("id", ""):
                best = m
                break
        if not best and matches:
            best = matches[0]

        naptan_id = best["id"] if best else None
        self._stop_cache[key] = {
            "naptan_id": naptan_id,
            "name": best.get("name") if best else None,
            "cached_at": datetime.now().isoformat(),
        }
        self._save_caches()
        return naptan_id

    # ── Fare lookup ───────────────────────────────────────────────────────────

    def get_fare(
        self,
        origin: str,
        destination: str,
        peak: bool,
        date_hint: datetime | None = None
    ) -> float | None:
        """
        Returns the adult Oyster single fare in GBP, or None if unavailable.
        Results are cached for CACHE_TTL_DAYS days.

        peak: True for peak journey, False for off-peak.
        date_hint: if provided, uses a representative date in the same fare period
                   (to handle multiple annual fare tables correctly).
        """
        cache_key = f"{origin.lower().strip()}|{destination.lower().strip()}|{'peak' if peak else 'offpeak'}"

        # Check fare cache
        if cache_key in self._fare_cache:
            entry = self._fare_cache[cache_key]
            if self._is_fresh(entry):
                return entry.get("fare_gbp")

        # If we were already throttled this session, skip everything — no point resolving stops either
        if self._journey_api_throttled:
            return None

        # Resolve stop IDs
        origin_id = self.resolve_stop(origin)
        dest_id = self.resolve_stop(destination)
        if not origin_id or not dest_id:
            return None
        if origin_id == dest_id:
            return None  # Same stop

        time_str = PEAK_TIME if peak else OFFPEAK_TIME
        data = self._api_get(
            f"/Journey/JourneyResults/{origin_id}/to/{dest_id}",
            {
                "date": PROBE_DATE,
                "time": time_str,
                "timeIs": "Departing",
                "journeyPreference": "LeastInterchange",
                "mode": "tube,dlr,overground,elizabeth-line",
            }
        )

        if not data:
            return None

        journeys = data.get("journeys", [])
        if not journeys:
            return None

        fare_pence = journeys[0].get("fare", {}).get("totalCost")
        if fare_pence is None:
            return None

        fare_gbp = round(fare_pence / 100, 2)

        self._fare_cache[cache_key] = {
            "fare_gbp": fare_gbp,
            "origin_id": origin_id,
            "dest_id": dest_id,
            "cached_at": datetime.now().isoformat(),
        }
        self._save_caches()
        return fare_gbp

    def apply_railcard(self, adult_fare: float, railcard_rule: dict, peak: bool) -> float | None:
        """Apply railcard discount to an adult fare. Returns discounted fare or None if railcard doesn't apply."""
        if not railcard_rule:
            return None
        applies_peak = railcard_rule.get("applies_peak", True)
        applies_offpeak = railcard_rule.get("applies_off_peak", True)
        if peak and not applies_peak:
            return None  # Railcard doesn't apply at peak
        if not peak and not applies_offpeak:
            return None
        discount = railcard_rule["discount_fraction"]
        min_fare = railcard_rule.get("min_fare_gbp", 0.0)
        fare = max(adult_fare * (1 - discount), min_fare)
        return round(round(fare * 20) / 20, 2)  # round to nearest 5p

    def stats(self) -> str:
        return f"{self._request_count} API calls made this session"
