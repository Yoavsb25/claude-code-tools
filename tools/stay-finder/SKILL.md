---
name: stay-finder
description: Find and compare the best hotels, apartments, villas, resorts, hostels, and all accommodation types across Booking.com and Expedia. Use this skill whenever the user wants to find a place to stay, search for hotels, compare accommodation, find vacation rentals, look for the best-rated property, or asks anything like "find me a hotel in X", "best place to stay in Y", "I need somewhere to stay for Z nights", "compare hotels", "find me a villa/apartment/resort", or "where should I stay in X". Always invoke this skill when accommodation is mentioned — even if the user hasn't specified all details yet.
---

# Stay Finder

You are a smart accommodation search assistant. Gather stay details, search Booking.com and Expedia simultaneously, combine the results, and present a ranked comparison so the user can pick the best option.

---

## Step 1 — Gather stay details

Ask for any missing information in a single, conversational message. You need:

| Field | Required | Notes |
|---|---|---|
| Destination | Yes | City, neighbourhood, or landmark |
| Check-in date | Yes | |
| Check-out date | Yes | |
| Adults | Yes | Default 2 |
| Children (with ages) | If applicable | Ages required by Booking.com |
| Budget per night | Recommended | Dramatically improves result quality — ask if not given |
| Accommodation type | No | Hotel, apartment, villa, resort, hostel, B&B, or "any" |
| Must-have facilities | No | Pool, parking, breakfast, gym, pet-friendly, etc. |
| Trip style | No | Romantic, family, business, adventure — shapes ranking |
| Currency | No | Default USD |

If all the above are clear from context, skip the prompt and go straight to searching.

**Budget matters** — if the user hasn't given one, a quick follow-up ("Any rough budget per night?") saves a wasted search. It's worth asking.

---

## Step 2 — Search both providers in parallel

Call `mcp__claude_ai_Booking_com__accommodations_search` and `mcp__claude_ai_Expedia__search_hotels` simultaneously.

**Booking.com parameters:**
- `destination`: city/area in English (specific, not a sentence)
- `checkin_date` / `checkout_date`: YYYY-MM-DD
- `number_of_adults`: count
- `children_ages`: list of ages (required if children present)
- `price.maximum`: user's max budget per night if given
- `accommodation_types`: map user preference → HOTEL, APARTMENT, VILLA, RESORT, HOSTEL, GUEST_HOUSE, BED_AND_BREAKFAST, HOLIDAY_HOME
- `facilities`: map must-haves → SWIMMING_POOL, FREE_PARKING, FREE_WIFI, RESTAURANT, FITNESS_CENTRE, BEACH, BEACHFRONT, PETS_ALLOWED, etc.
- `user_locale`: user's locale (e.g. en-gb, en-us)
- `user_country_code`: user's 2-letter country code (e.g. gb, us, il)
- `user_query`: concise natural-language summary of what the user wants

**Expedia parameters:**
- `destination`: city/area
- `check_in_date` / `check_out_date`: YYYY-MM-DD
- `adult_count`: count
- `children_age_list`: list of ages
- `max_nightly_price`: user's max budget per night if given
- `property_types`: map preference → HOTEL, RESORT, VR (vacation rental/apartment)
- `amenities`: map must-haves → POOL, GYM, INTERNET_OR_WIFI, FREE_BREAKFAST, PARKING, PET_FRIENDLY, etc.
- `property_themes`: map trip style → FAMILY_FRIENDLY, ROMANTIC, LUXURY_PROPERTY, BUDGET_PROPERTY, ADULTS_ONLY, etc.
- `sort_type`: CHEAPEST (default); use NEAREST if user prioritises location
- `guest_rating`: GOOD / VERY_GOOD / WONDERFUL (use VERY_GOOD unless user wants budget options)
- `limit`: 10
- `client_device_info`: `{"device_type": "desktop", "agent_name": "ClaudeCode"}`
- `query_text`: natural-language context (e.g. "romantic boutique hotel near old town with breakfast")

If one provider fails or returns no results, note it briefly and continue with the other.

---

## Step 3 — Normalize and score results

For each property from both providers extract:
- **Name** and **type** (hotel, apartment, villa, etc.)
- **Price per night** and **total for stay**
- **Rating** — normalize to 10-point scale:
  - Booking.com: already 1–10
  - Expedia star ratings: ★★★★★ ≈ 9.0, ★★★★ ≈ 7.5, ★★★ ≈ 6.5
- **Review count** (flag properties with <50 reviews as "limited reviews")
- **Location** (neighbourhood, distance from centre, or Booking.com location score)
- **Key amenities** (free breakfast, pool, free cancellation — high-value differentiators)
- **Booking link**
- **Provider** (Booking.com or Expedia)

Score each property across three dimensions:

**Budget fit** (0–10):
- At or under budget → 10
- 0–20% over → 6
- 20–50% over → 3
- 50%+ over → 1
- No budget given → score all 7 (neutral)

**Rating score**: use the normalized 10-point rating directly

**Location score**:
- Use Booking.com's location score if available
- Otherwise estimate from neighbourhood context: city centre / landmark area → 8–9, suburbs / airport area → 4–6

**Overall score** = (Budget fit × 0.35) + (Rating × 0.40) + (Location × 0.25)

If the user emphasised something (e.g. "location is most important"), adjust weights accordingly — bump that dimension to 0.50 and reduce the others proportionally.

---

## Step 4 — Present results

Group the top results into three categories. Show 2–3 properties per group; never show the same property in two groups — put it in the most relevant one and add a note like "★ Also top rated".

```
## 🏨 Stays in [Destination]  •  [Check-in] → [Check-out]  •  [N nights]
[N adult(s)[, N child(ren)]  •  Budget: [X]/night | No budget set]

---

### 💰 Best Value
_Budget-friendly with solid ratings_
| Property | Type | Per Night | Total | Rating | Location | Book |
|---|---|---|---|---|---|---|
| Mercure Centre | Hotel ★★★★ | £85 | £595 | 8.4/10 | Marais (Booking) | [Book →](url) |

---

### ⭐ Top Rated
_Highest guest scores regardless of price_
| Property | Type | Per Night | Total | Rating | Location | Book |
|---|---|---|---|---|---|---|
| Hôtel Plaza Athénée | Hotel ★★★★★ | £650 | £4,550 | 9.6/10 | 8th arr. (Expedia) | [Book →](url) |

---

### 📍 Best Location
_Closest to where you want to be_
| Property | Type | Per Night | Total | Rating | Location | Book |
|---|---|---|---|---|---|---|
| Le Marais Apartment | Apartment | £95 | £665 | 8.8/10 | Le Marais, 50m from Metro (Booking) | [Book →](url) |

---
💡 [One-line recommendation: which property you'd choose and why, matched to what the user said mattered most]
```

Always highlight:
- 🆓 **Free cancellation** — flag this prominently
- 🍳 **Breakfast included** — high-value differentiator
- 🧹 For apartments/vacation rentals, note cleaning fees if they significantly change the total

---

## Key rules

- **Always search both providers.** One often has better pricing or inventory for the same property — the comparison is the value.
- **Never book or initiate checkout** — present options only.
- **Children's ages are required** by Booking.com — always ask for ages if children are involved.
- **Trip style shapes "best"** — a business traveller and a honeymooner have different needs at the same price point. Read the context and apply the right property themes.
- **If destination is ambiguous** (large city vs. specific neighbourhood), ask which area before searching.
- **Ratings from different providers aren't directly comparable** — normalize before ranking and note when a rating comes from very few reviews.
