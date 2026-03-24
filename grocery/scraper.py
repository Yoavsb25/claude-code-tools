"""
scraper.py — Playwright-based price scraper for Tesco, Ocado, and Waitrose.

CSS selectors may drift when retailers update their sites.
To fix: open the retailer's search results page in Chrome, press Cmd+Shift+C,
inspect a product card, and update the selectors below.

Apify fallback: if a retailer aggressively blocks Playwright (common with Ocado),
set USE_APIFY["ocado"] = True and supply APIFY_TOKEN in your environment.
"""

import asyncio
import re
import urllib.parse
from typing import Optional

from playwright.async_api import async_playwright, BrowserContext, Page

MAX_CONCURRENT_PAGES = 5
MAX_RESULTS_PER_RETAILER = 5
RETAILERS = ["tesco", "ocado", "waitrose"]

SEARCH_URLS = {
    "tesco": "https://www.tesco.com/groceries/en-GB/search?query={item}",
    "ocado": "https://www.ocado.com/search?entry={item}",
    "waitrose": "https://www.waitrose.com/ecom/shop/search?searchTerm={item}",
}

# CSS selectors — verify with DevTools if scraping returns empty results
SELECTORS = {
    "tesco": {
        "container": "[data-auto='product-tile']",
        "name": "[data-auto='product-tile--title']",
        "price": ".beans-price__text",
        "unit_price": ".beans-price__subtext",
        "link": "a",
        "base_url": "https://www.tesco.com",
    },
    "ocado": {
        "container": ".fop-item",
        "name": ".fop-title",
        "price": ".fop-price",
        "unit_price": ".fop-unit-price",
        "link": "a",
        "base_url": "https://www.ocado.com",
    },
    "waitrose": {
        "container": "[class*='ProductPod_container']",
        "name": "[data-testid='product-pod-link']",
        "price": "[class*='ProductPod'] [class*='price__value']",
        "unit_price": "[class*='pricePerUnit']",
        "link": "[data-testid='product-pod-link']",
        "base_url": "https://www.waitrose.com",
    },
}

# Switch a retailer to True to use the Apify HTTP fallback instead of Playwright.
# Requires APIFY_TOKEN environment variable.
USE_APIFY: dict[str, bool] = {
    "tesco": False,
    "ocado": False,
    "waitrose": False,
}


def _parse_price(text: str) -> Optional[float]:
    """Parse a price string ('£1.40', '140p', '1.40') to a float."""
    text = text.strip()
    m = re.search(r"£([\d]+\.[\d]{1,2})", text)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d]+\.[\d]{1,2})", text)
    if m:
        return float(m.group(1))
    m = re.search(r"([\d]+)p\b", text, re.IGNORECASE)
    if m:
        return int(m.group(1)) / 100
    return None


async def _scrape_playwright(page: Page, item: str, retailer: str) -> list[dict]:
    """Scrape a single retailer for one item using a Playwright page."""
    s = SELECTORS[retailer]
    url = SEARCH_URLS[retailer].format(item=urllib.parse.quote(item))

    try:
        response = await page.goto(url, wait_until="domcontentloaded", timeout=20_000)
        if response and response.status in (403, 429):
            print(
                f"  [{retailer}] Blocked (HTTP {response.status}). "
                f"Switch USE_APIFY['{retailer}'] = True in scraper.py to use the Apify fallback."
            )
            return []

        await page.wait_for_selector(s["container"], timeout=10_000)

    except Exception as exc:
        msg = str(exc)
        if "captcha" in msg.lower() or "403" in msg.lower():
            print(
                f"  [{retailer}] Bot detection triggered for '{item}'. "
                f"Switch USE_APIFY['{retailer}'] = True in scraper.py."
            )
        elif "timeout" in msg.lower():
            print(f"  [{retailer}] Timeout waiting for results for '{item}'.")
        else:
            print(f"  [{retailer}] Error scraping '{item}': {msg[:100]}")
        return []

    containers = await page.query_selector_all(s["container"])
    products: list[dict] = []

    for container in containers[:MAX_RESULTS_PER_RETAILER]:
        try:
            name_el = await container.query_selector(s["name"])
            price_el = await container.query_selector(s["price"])
            unit_el = await container.query_selector(s["unit_price"])
            link_el = await container.query_selector(s["link"])

            if not name_el or not price_el:
                continue

            name = (await name_el.text_content() or "").strip()
            price_raw = (await price_el.text_content() or "").strip()
            unit_price = ""
            if unit_el:
                unit_price = (await unit_el.text_content() or "").strip()

            href = ""
            if link_el:
                href = await link_el.get_attribute("href") or ""
                if href and not href.startswith("http"):
                    href = s["base_url"] + href

            price = _parse_price(price_raw)
            if price is None:
                continue

            products.append(
                {
                    "retailer": retailer,
                    "name": name,
                    "price": price,
                    "unit_price": unit_price,
                    "url": href,
                }
            )
        except Exception:
            continue

    return products


async def _scrape_apify(item: str, retailer: str) -> list[dict]:
    """
    Apify fallback — makes an HTTP call to a pre-built Apify actor.
    Requires APIFY_TOKEN environment variable.
    This is a stub: swap in the real Apify actor endpoint for each retailer.
    """
    import os

    token = os.environ.get("APIFY_TOKEN")
    if not token:
        print(
            f"  [{retailer}] APIFY_TOKEN not set. "
            "Set it in your environment to use the Apify fallback."
        )
        return []

    # Retailer-specific actor IDs from the Apify marketplace:
    # tesco:    "misceres/tesco-scraper"
    # ocado:    "misceres/ocado-scraper"
    # waitrose: look up current actor on apify.com/store
    print(
        f"  [{retailer}] Apify fallback not yet wired up. "
        "Update _scrape_apify() with the actor endpoint for this retailer."
    )
    return []


async def _scrape_item(
    item: str,
    retailer: str,
    semaphore: asyncio.Semaphore,
    context: BrowserContext,
) -> list[dict]:
    """Scrape one retailer for one item, respecting the concurrency limit."""
    async with semaphore:
        if USE_APIFY.get(retailer):
            return await _scrape_apify(item, retailer)

        page = await context.new_page()
        try:
            return await _scrape_playwright(page, item, retailer)
        finally:
            await page.close()


async def scrape_all(items: list[str]) -> dict[str, list[dict]]:
    """
    Scrape all retailers for every item concurrently.

    Returns a dict mapping each item name to a flat list of candidate products
    (mixed across all retailers, each product has a 'retailer' field).
    """
    semaphore = asyncio.Semaphore(MAX_CONCURRENT_PAGES)

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/120.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1280, "height": 800},
        )

        tasks = [
            _scrape_item(item, retailer, semaphore, context)
            for item in items
            for retailer in RETAILERS
        ]
        flat_results = await asyncio.gather(*tasks, return_exceptions=True)

        await browser.close()

    # Group back into {item: [products]}
    candidates: dict[str, list[dict]] = {item: [] for item in items}
    idx = 0
    for item in items:
        for retailer in RETAILERS:
            result = flat_results[idx]
            idx += 1
            if isinstance(result, list):
                candidates[item].extend(result)
            else:
                print(f"  [{retailer}] Unexpected error for '{item}': {result}")

    return candidates
