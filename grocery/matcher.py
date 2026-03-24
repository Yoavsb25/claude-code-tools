"""
matcher.py — Claude API matching layer.

Sends all items and their scraped candidates to Claude in a single API call
and gets back the best-match product per item per retailer.
"""

import json
import os

from anthropic import Anthropic

MODEL = "claude-sonnet-4-6"
CONFIDENCE_THRESHOLD = 0.8

_client: Anthropic | None = None


def _get_client() -> Anthropic:
    global _client
    if _client is None:
        _client = Anthropic()
    return _client


SYSTEM_PROMPT = """\
You are matching shopping list items to supermarket products.
For each item, pick the best match per retailer from the candidates provided.

Matching rules (apply in this order):
1. Prefer own-label over branded — unless a specific brand is named in the shopping list
2. Match size/quantity as closely as possible to what was requested
3. Prefer standard over organic — unless organic is specified
4. Exception: if own-label is only available as organic (common at Waitrose), \
accept it rather than switching to a branded non-organic alternative

Confidence scale (self-assess honestly):
  1.0 — exact match: correct type, correct size, own-label
  0.8 — close match: slightly different size, or only branded option available
  <0.8 — ambiguous: wrong category, no reasonable match, brand unclear, \
          or two equally valid interpretations

For matches below 0.8, include a clarification_question field asking the user \
to disambiguate (be concise — one sentence).

If no candidate is a reasonable match for an item at a given retailer, return:
  {"price": null, "url": null, "matched_product": null, "confidence": 0}

Return ONLY a JSON array — no prose, no markdown fences.\
"""


def _call_claude(items_text: str, candidates_json: str) -> list[dict]:
    """Call Claude and return parsed match list. Retries once on malformed JSON."""
    client = _get_client()
    user_content = (
        f"Shopping list:\n{items_text}\n\n"
        f"Candidates (per item, across all retailers):\n{candidates_json}"
    )

    for attempt in range(2):
        try:
            response = client.messages.create(
                model=MODEL,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_content}],
            )
            text = response.content[0].text.strip()
            # Strip markdown code fences if Claude adds them anyway
            if text.startswith("```"):
                text = text.split("```")[1]
                if text.startswith("json"):
                    text = text[4:]
                text = text.strip()
            return json.loads(text)
        except (json.JSONDecodeError, IndexError):
            if attempt == 0:
                print("  [matcher] Claude returned malformed JSON — retrying...")
                continue
            raise RuntimeError("Claude API returned unparseable JSON after 2 attempts.")
        except Exception as exc:
            raise RuntimeError(f"Claude API call failed: {exc}") from exc

    return []


def match_items(items: list[dict], candidates: dict[str, list[dict]]) -> list[dict]:
    """
    Match all shopping list items to scraped products in a single Claude API call.

    items      — [{"item": str, "qty": int}, ...]
    candidates — {item_name: [product_dict, ...]}

    Returns a list of match dicts:
      {item, retailer, matched_product, price, unit_price, url, confidence,
       clarification_question?}
    """
    items_text = "\n".join(f"- {i['item']}" for i in items)

    # Strip candidates to essential fields — quantities are handled by the renderer,
    # not Claude, so we don't send qty here either.
    stripped: dict[str, list[dict]] = {}
    for item_name, products in candidates.items():
        stripped[item_name] = [
            {
                "retailer": p["retailer"],
                "name": p["name"],
                "price": p["price"],
                "unit_price": p["unit_price"],
                "url": p["url"],
            }
            for p in products
        ]

    return _call_claude(items_text, json.dumps(stripped, indent=2))


def rematch_ambiguous(
    existing_matches: list[dict],
    candidates: dict[str, list[dict]],
    user_answers: dict[str, str],
) -> list[dict]:
    """
    Re-call Claude with only the ambiguous items, appending the user's answers.
    Returns the full match list (high-confidence originals + new matches).

    user_answers — {item_name: answer_string}
    """
    high_conf = [
        m for m in existing_matches
        if m.get("confidence", 1.0) >= CONFIDENCE_THRESHOLD
    ]
    ambiguous_items = list(user_answers.keys())
    items_text = "\n".join(f"- {item}" for item in ambiguous_items)

    stripped: dict[str, list[dict]] = {}
    for item_name in ambiguous_items:
        stripped[item_name] = [
            {
                "retailer": p["retailer"],
                "name": p["name"],
                "price": p["price"],
                "unit_price": p["unit_price"],
                "url": p["url"],
                "user_clarification": user_answers[item_name],
            }
            for p in candidates.get(item_name, [])
        ]

    new_matches = _call_claude(items_text, json.dumps(stripped, indent=2))
    return high_conf + new_matches
