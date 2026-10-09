"""HTML cleanup, company-name normalization, and posting() shaping."""

import re

from jobsearch.fetchconfig import DEFAULT, FetchConfig

# Same suffix set ATS slug-guessing uses — kept here so normalize_company does not import sources.
ATS_SLUG_SUFFIXES = {
    "inc", "llc", "ltd", "corp", "corporation", "co", "company",
    "group", "technologies", "technology", "labs", "software", "systems",
}

LINKEDIN_BR_RE = re.compile(r"<\s*br\s*/?>", re.IGNORECASE)
LINKEDIN_BLOCK_CLOSE_RE = re.compile(r"</(p|li|ul|ol|div|h\d)>", re.IGNORECASE)


def strip_html(text):
    if not text:
        return text
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


def decode_html_entities(text):
    if not text:
        return text

    def numeric_entity(code_point):
        return chr(code_point) if 0 <= code_point <= 0x10FFFF else ""

    text = text.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
    text = text.replace("&quot;", '"').replace("&#39;", "'").replace("&apos;", "'")
    text = re.sub(r"&#(\d+);", lambda m: numeric_entity(int(m.group(1))), text)
    text = re.sub(r"&#[xX]([0-9a-fA-F]+);", lambda m: numeric_entity(int(m.group(1), 16)), text)
    text = text.replace("&nbsp;", " ")
    return text


def clean_text(html):
    if not html:
        return html
    return decode_html_entities(strip_html(html))


def _strip_tags_keep_newlines(text):
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" *\n *", "\n", text)
    return text.strip()


def description_text(html, config=None):
    config = config or DEFAULT
    if not config.keep_lines:
        return strip_html(html)
    text = decode_html_entities(decode_html_entities(html))  # some ATSs double-escape
    text = LINKEDIN_BR_RE.sub("\n", text)
    text = LINKEDIN_BLOCK_CLOSE_RE.sub("\n", text)
    text = decode_html_entities(_strip_tags_keep_newlines(text))
    return re.sub(r"\n{2,}", "\n", text)


def posting(source, title, company, location, remote, url, tags, salary, posted_date, description,
            config=None):
    config = config or DEFAULT
    desc = None
    if description:
        text = description_text(description, config)
        desc = text if config.description_max is None else text[: config.description_max]
    return {
        "source": source, "title": title, "company": company, "location": location,
        "remote": remote, "url": url, "tags": tags or [], "salary": salary,
        "posted_date": posted_date,
        "description": desc,
    }


def normalize_company(name):
    """Lowercase, strip punctuation, drop common legal-suffix words — for comparing a
    connection's Company field against a target_companies watchlist entry."""
    words = re.findall(r"[a-z0-9]+", (name or "").lower())
    trimmed = [w for w in words if w not in ATS_SLUG_SUFFIXES]
    return trimmed or words


def company_words_match(target_words, company_words):
    """Whole-word prefix match, not raw substring."""
    if not target_words or not company_words:
        return False
    return company_words[: len(target_words)] == target_words
