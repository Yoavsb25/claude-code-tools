"""Radar enrichment: years required, level, role family, skill fit, salary."""

import re

from jobsearch.profile import profile_path
from jobsearch.store import load_json
from jobsearch.text import company_words_match, normalize_company

STORED_DESCRIPTION_CHARS = 6000

NUMBER_WORDS = {
    "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7,
    "eight": 8, "nine": 9, "ten": 10, "twelve": 12, "fifteen": 15,
}
_NUM = r"(\d{1,2}|" + "|".join(NUMBER_WORDS) + r")"
# "3+ years", "3-5 years", "3 to 5 yrs", "at least three years", "minimum of 4 years"
YEARS_RE = re.compile(
    r"\b" + _NUM + r"\s*(?:\+|plus)?\s*(?:(?:-|–|—|to)\s*" + _NUM + r"\s*\+?\s*)?(?:years?|yrs?)\b",
    re.IGNORECASE,
)
# Sentences where "N years" is about the company, not the candidate.
YEARS_NOISE_RE = re.compile(
    r"years?\s+(?:ago|old)|founded|anniversary|in business|of history|history of|"
    r"(?:past|last|next|over the)\s+" + _NUM + r"\s+years?|years? in a row|"
    r"(?:parental|maternity|paternity)|vesting|of service|holiday",
    re.IGNORECASE,
)

LEVEL_RULES = [
    ("intern", r"\bintern(ship)?\b|\bplacement\b"),
    ("entry", r"\bgraduate\b|\bnew grad\b|\bentry[- ]level\b|\bapprentice"),
    ("staff+", r"\bstaff\b|\bprincipal\b|\bdistinguished\b|\barchitect\b"),
    # Any people/function manager; product, program, project, delivery and account managers are
    # job titles, not a level.
    ("manager", r"\bhead of\b|\bdirector\b|\bvp\b|\bvice president\b|\bmgr\b|"
                r"(?<!product )(?<!program )(?<!programme )(?<!project )(?<!delivery )(?<!account )\bmanager\b"),
    ("senior", r"\bsenior\b|\bsr\.?\b|\blead\b|\biii\b|\biv\b"),
    ("junior", r"\bjunior\b|\bjr\.?\b|\bassociate\b|\b(?:engineer|developer) i\b"),
    ("mid", r"\bmid[- ]?level\b|\bii\b"),
]
LINKEDIN_SENIORITY_LEVELS = {
    "internship": "intern", "entry level": "entry", "associate": "junior",
    "mid-senior level": "mid/senior", "director": "manager", "executive": "manager",
}

# First match on the title wins; order matters (e.g. "AI solutions engineer" -> AI/FDE).
ROLE_FAMILY_RULES = [
    ("Product", r"product manager|product owner|\bpm\b"),
    # Before AI/FDE so "Research Scientist - Generative Audio" isn't read as an AI engineering role.
    ("Data/ML", r"scientist|\bresearch(?:er)?\b"),
    ("Mobile", r"\bandroid\b|\bios\b|\bmobile\b|react native|\bflutter\b|\bkotlin\b|\bswift\b"),
    ("AI/FDE", r"\bai\b|\bllm\b|\bgenai\b|\bgenerative\b|forward[- ]deployed|deployed engineer|\bagents?\b|applied ai"),
    ("DevEx/Tools", r"developer experience|devex|developer productivity|internal tools|tooling|build|release"),
    ("Infra/DevOps", r"platform|devops|devsecops|\bsre\b|reliability|infrastructure|cloud engineer|kubernetes"),
    ("Solutions", r"solutions?|deployment strategist|technical success|customer engineer|sales engineer|implementation|integration engineer|"
                  r"technical account|support engineer|pre-?sales|consultant"),
    ("TPM/Program", r"program(?:me)? (?:manager|management|lead)|project manager|delivery manager|\btpm\b|scrum|chief of staff"),
    ("Security/IT", r"security|\biam\b|\bgrc\b|\bit (?:manager|support|analyst|engineer)|"
                    r"systems analyst|infosec|\bsoc\b"),
    ("Data/ML", r"\bdata\b|machine learning|\bml\b|analytics|scientist|research engineer"),
    ("QA/Automation", r"\bqa\b|quality|\btest|\bsdet\b|automation"),
    ("SWE", r"engineer|developer|programmer|swe\b|full[- ]?stack|backend|back-end|frontend|front-end"),
]
NON_TECH_RE = re.compile(
    r"account executive|sales|recruit|talent|legal|counsel|finance|accountant|marketing|"
    r"people partner|\bhr\b|office|executive assistant|payroll|procurement|designer|copywriter|"
    r"business development|partnerships|customer success manager|paralegal|account manager|"
    r"account director|client partner|revenue|fp&a|\btax\b|accounting|store|retail|merchandis|"
    r"\bpeople\b|employee relations|credit|fraud|financial crime|regulatory|\bgtm\b|deal desk|"
    r"renewals|channel|partner director|government relations|policy|workplace|coordinator|"
    r"user research|compliance|administrative|assistant|financial|treasury|controller|"
    r"accounts payable|complaints|claims|handler|collections|customer service|"
    r"customer operations|support specialist|growth|strateg|events|communications|"
    r"knowledge management|creative|artworker|dubbing|translator|linguist|audiobook|"
    r"laboratory|technician|economist|\blaw\b|proposal|paid media|lending|portfolio|onboarding|"
    r"operations (?:associate|executive)|surveillance|summer intern|\bsdr\b|\bbdr\b|"
    r"market operations|general application|general opportunities|register your interest|"
    r"engagement manager|pricing|payments control|floor manager|production manager|"
    r"property|\bpa\b|freelance|martech|account executive|technical writer",
    re.IGNORECASE,
)
# "Solutions Engineer (German speaking)": a separate posting per language. English and Hebrew are fine.
_LANGUAGES = (r"(?:french|german|spanish|italian|dutch|portuguese|arabic|nordic|swedish|danish|norwegian|"
              r"finnish|polish|turkish|greek|russian|japanese|mandarin|chinese|korean|hindi|czech|hungarian|romanian)")
OTHER_LANGUAGE_RE = re.compile(r"\b" + _LANGUAGES + r"[- ]speak(?:ing|er)\b|\bfluent (?:in )?" + _LANGUAGES + r"\b",
                               re.IGNORECASE)
DEAL_BREAKER_RE = re.compile(r"\b(?:gambling|betting|casino|sportsbook|igaming|poker)\b", re.IGNORECASE)

# Recruitment agencies post the same roles as the companies, but vaguer ("our client") and often
# duplicated. Flagged, not dropped; the page hides them by default.
RECRUITER_NAME_RE = re.compile(
    r"recruit|staffing|resourcing|talent solutions|hunter bond|client server|albert bow|\bsr2\b|"
    r"anson mccade|signify technology|atarus|la fosse|harnham|oliver bernard|tenth revolution|"
    r"burns sheehan|trust in soda|explore group|nigel frank|jefferson frank|montash|datatech|"
    r"\bsalt\b|lorien|robert walters|\bhays\b|michael page|randstad|harvey nash|venatrix|"
    r"miller maxwell|opus recruitment|understanding recruitment|\bdevelop\b|searchability|"
    r"x4 group|mploy|tec partners|stott and may|piper maddox|forward role",
    re.IGNORECASE,
)
RECRUITER_TEXT_RE = re.compile(r"\bour client\b|on behalf of (?:our|a) client|\bmy client\b", re.IGNORECASE)

SALARY_RE = re.compile(
    r"£\s?(\d{2,3})(?:[,.](\d{3}))?\s?(k)?(?:\s*(?:-|–|—|to)\s*£?\s?(\d{2,3})(?:[,.](\d{3}))?\s?(k)?)?",
    re.IGNORECASE,
)

LONDON_RE = re.compile(r"london", re.IGNORECASE)
UK_REMOTE_RE = re.compile(r"united kingdom|\buk\b|england|emea|europe", re.IGNORECASE)


# ---- enrichment (pure functions) --------------------------------------------

# "5+ years of X is a plus" is not a requirement; don't let it mark a role as too senior.
NICE_TO_HAVE_RE = re.compile(r"\bis a plus\b|nice[- ]to[- ]have|\bbonus\b|\bdesirable\b|\bideally\b|\bpreferred\b",
                             re.IGNORECASE)

# Skills a job ad can ask for: (name, regex for the job ad, regex for profile.json skills).
# The profile regex defaults to the job-ad one. Whether you have a skill comes from profile.json,
# so adding a skill there changes the scores on the next refresh.
SKILLS = [
    ("Python", r"\bpython\b", None),
    ("TypeScript", r"\btypescript\b", None),
    ("JavaScript", r"\bjavascript\b", None),
    ("Go", r"\bgolang\b|(?-i:\bGo\b)(?![- ](?:live|to|beyond|further|above|fast)\b)", r"\bgo\b|golang"),
    ("Java", r"\bjava\b(?!\s*script)", None),
    ("C#/.NET", r"c#|\.net\b|\bdotnet\b", None),
    ("C++", r"c\+\+", None),
    ("Rust", r"\brust\b", None),
    ("Scala", r"\bscala\b", None),
    ("Kotlin", r"\bkotlin\b", None),
    ("Swift", r"(?-i:\bSwift\b)", r"\bswift\b"),
    ("Ruby", r"\bruby\b|\brails\b", None),
    ("PHP", r"\bphp\b", None),
    ("Elixir", r"\belixir\b", None),
    ("SQL", r"\bsql\b|postgres|mysql", None),
    ("Bash", r"\bbash\b|shell script", None),
    ("Linux", r"\blinux\b|\bunix\b", None),
    ("Docker", r"\bdocker\b|\bcontaineri[sz]", None),
    ("Kubernetes", r"kubernetes|\bk8s\b|\beks\b|\bgke\b", None),
    ("Terraform/IaC", r"terraform|infrastructure[- ]as[- ]code|\biac\b|pulumi|cloudformation", None),
    ("AWS", r"\baws\b|amazon web services", None),
    ("Azure", r"\bazure\b", None),
    ("GCP", r"\bgcp\b|google cloud", None),
    ("CI/CD", r"ci/cd|continuous (?:integration|delivery|deployment)|jenkins|github actions|gitlab ci|circleci", None),
    ("GitOps", r"gitops|argo ?cd", None),
    ("React", r"\breact\b(?! native)", None),
    ("Vue/Angular", r"\bvue(?:\.?js)?\b|\bangular\b", None),
    ("Node.js", r"node\.?js|express\.?js|\bnestjs\b", r"node|express"),
    ("Flask/Django/FastAPI", r"\bflask\b|\bdjango\b|fastapi", None),
    ("REST APIs", r"\brestful\b|\brest(?:/json)? apis?\b|\bapi (?:design|development)\b|\bbuild(?:ing)? apis\b", r"rest api"),
    ("GraphQL", r"graphql", None),
    ("Test automation", r"pytest|playwright|vitest|unit tests?|test automation|automated tests?", r"pytest|playwright"),
    ("Git", r"\bgit\b|github|gitlab", None),
    # Model names only, not vendors: OpenAI's and Anthropic's own ads name the company everywhere.
    ("LLMs", r"\bllms?\b|large language model|generative ai|\bgenai\b|prompt engineering|\brag\b|ai agents?",
     r"ai integration|claude"),
    ("Kafka", r"\bkafka\b", None),
    ("Spark/Airflow/dbt", r"\bspark\b|\bairflow\b|\bdbt\b", None),
    ("ML frameworks", r"pytorch|tensorflow|\bjax\b|scikit", None),
]
SKILLS = [(name, re.compile(jd, re.IGNORECASE), re.compile(prof or jd, re.IGNORECASE)) for name, jd, prof in SKILLS]
LANGUAGES = {"Python", "TypeScript", "JavaScript", "Go", "Java", "C#/.NET", "C++", "Rust", "Scala", "Kotlin",
             "Swift", "Ruby", "PHP", "Elixir"}
BLOCKED_FIT_CAP = 20


def _to_int(token):
    token = token.lower()
    return int(token) if token.isdigit() else NUMBER_WORDS.get(token)


def _sentences(text):
    return [s.strip() for s in re.split(r"(?<=[.!?])\s+|\n+|•|·", text or "") if s.strip()]


def extract_years(text):
    """Return (min_years, evidence_sentence) for the strictest candidate-experience requirement
    in a JD, or (None, None). Strictest = largest minimum, since the page filters on "too
    senior". Values above 15 are ignored as noise."""
    best, evidence = None, None
    for sentence in _sentences(text):
        if YEARS_NOISE_RE.search(sentence) or NICE_TO_HAVE_RE.search(sentence):
            continue
        for m in YEARS_RE.finditer(sentence):
            low = _to_int(m.group(1))
            if low is None or low == 0 or low > 15:
                continue
            if best is None or low > best:
                best, evidence = low, sentence[:300]
    return best, evidence


def profile_skills():
    """Names from SKILLS that profile.json's skills list covers."""
    profile = load_json(profile_path(), {})
    text = "\n".join(profile.get("skills") or [])
    return {name for name, _, prof in SKILLS if prof.search(text)}


def skill_fit(text, have):
    """Score 0-100 for how well a job ad's tech asks match the skills you have. The +1 in the
    denominator means one matching skill alone scores 50, so a high score needs real evidence.
    Returns {fit, fit_have, fit_missing, fit_blocker}; fit is None when the ad names no tech.
    A skill only counts as missing when a required sentence asks for it ("Go is a plus" doesn't).
    fit_blocker names the main language when the ad requires one you lack and none you have."""
    found, missing = set(), set()
    for sentence in _sentences(text):
        optional = bool(NICE_TO_HAVE_RE.search(sentence))
        for name, jd, _ in SKILLS:
            if jd.search(sentence):
                found.add(name)
                if name not in have and not optional:
                    missing.add(name)
    matched = found & have
    result = {"fit": None, "fit_have": sorted(matched), "fit_missing": sorted(missing), "fit_blocker": None}
    if not matched and not missing:
        return result
    fit = round(100 * len(matched) / (len(matched) + len(missing) + 1))
    lacking_langs = sorted(missing & LANGUAGES)
    if lacking_langs and not (found & have & LANGUAGES):
        result["fit_blocker"] = lacking_langs[0]
        fit = min(fit, BLOCKED_FIT_CAP)
    result["fit"] = fit
    return result


def classify_level(title, linkedin_seniority=None):
    t = (title or "").lower()
    for level, pattern in LEVEL_RULES:
        if re.search(pattern, t):
            return level
    if linkedin_seniority:
        return LINKEDIN_SENIORITY_LEVELS.get(linkedin_seniority.strip().lower(), "unknown")
    return "unknown"


def role_family(title):
    t = (title or "").lower()
    # "AI" or "security" in a sales or compliance title doesn't make it a tech role.
    if "freelance" in t:
        return "Non-tech"
    if NON_TECH_RE.search(t) and not re.search(
            r"engineer|developer|product manager|\bpm\b|deployment strategist|scientist|data|\bml\b", t):
        return "Non-tech"
    for family, pattern in ROLE_FAMILY_RULES:
        if re.search(pattern, t):
            return family
    return "Other"


def _salary_value(num, thousands, k_suffix):
    if thousands:
        value = int(num + thousands)
    elif k_suffix:
        value = int(num) * 1000
    else:
        return None  # a bare "£500" is a perk or a fee, not a salary
    return value if 15000 <= value <= 400000 else None


def extract_salary(text):
    """Return (display_string, min_gbp) for the first plausible annual £ figure, else (None, None)."""
    for m in SALARY_RE.finditer(text or ""):
        low = _salary_value(m.group(1), m.group(2), m.group(3) or m.group(6))  # "£85-110k"
        if low is None:
            continue
        high = None
        if m.group(4):
            high = _salary_value(m.group(4), m.group(5), m.group(6) or m.group(3))
        display = f"£{low // 1000}k" + (f"–£{high // 1000}k" if high and high > low else "")
        return display, low
    return None, None


def on_watchlist(company_words, watch_words):
    """Word-prefix match in either direction: "Amazon" matches "Amazon / AWS" and
    "Google UK" matches "Google"."""
    return any(company_words_match(w, company_words)
               or company_words_match(company_words, w) for w in watch_words)


def is_recruiter(company, description=None):
    return bool(RECRUITER_NAME_RE.search(company or "")
                or RECRUITER_TEXT_RE.search((description or "")[:3000]))


def is_target_location(location, remote=None):
    loc = location or ""
    if LONDON_RE.search(loc):
        return True
    remote_flag = bool(remote) or "remote" in loc.lower()
    return remote_flag and bool(UK_REMOTE_RE.search(loc))


def posting_key(company, title):
    company_words = normalize_company(company or "")
    title_words = re.findall(r"[a-z0-9]+", (title or "").lower())
    return " ".join(company_words) + "|" + " ".join(title_words)


def title_flags(title):
    return ["other_language"] if OTHER_LANGUAGE_RE.search(title or "") else []


def enrich(raw, linkedin_seniority=None):
    description = raw.get("description") or ""
    years, evidence = extract_years(description)
    salary, salary_min = extract_salary(raw.get("salary") or description)
    flags = title_flags(raw.get("title"))
    if DEAL_BREAKER_RE.search(f"{raw.get('company')} {raw.get('title')} {description[:2000]}"):
        flags.append("deal_breaker")
    if is_recruiter(raw.get("company"), description):
        flags.append("recruiter")
    return {
        "company": raw.get("company"),
        "title": raw.get("title"),
        "location": raw.get("location"),
        "url": raw.get("url"),
        "source": raw.get("source"),
        "posted_date": raw.get("posted_date"),
        "years_min": years,
        "years_evidence": evidence,
        "level": classify_level(raw.get("title"), linkedin_seniority),
        "role_family": role_family(raw.get("title")),
        "salary": salary,
        "salary_min": salary_min,
        "flags": flags,
        "description": description[:STORED_DESCRIPTION_CHARS] or None,
    }
