"""Read each posting and flag ones a 2nd-year student (graduating 2030) can't apply to.

Flags postings that ask for final year, 3rd/4th year, junior/senior standing, or a
graduation date in 2028 or earlier. Results are cached in data/reqs.json so each
posting is only re-read every couple of weeks.
"""
import datetime as dt
import html
import json
import re
import urllib.parse
import urllib.request

RECHECK_DAYS = 14
MAX_PER_RUN = 250
MY_GRAD = 2030

_YEAR = r"(?:3rd|4th|third|fourth|final|last|senior|penultimate)"
PATTERNS = [
    re.compile(r"\b(?:entering|going into|starting|in|into|completing|completed)\s+(?:their|your|his|her|the|a)?\s*" + _YEAR + r"[- ]year", re.I),
    re.compile(r"\b(?:final|last|penultimate)[- ]year\s+(?:of\s+)?(?:student|undergrad|bachelor|engineering|study|studies|university|program)", re.I),
    re.compile(r"\b(?:3rd|4th|third|fourth)[- ]year\s+(?:or\s+(?:above|higher|later|beyond)|and\s+(?:above|up)|\+|students?|undergrad\w*|standing|of\s+(?:an?\s+|your\s+|their\s+)?(?:engineering|bachelor|undergrad|degree|university|study|program))", re.I),
    re.compile(r"\b(?:minimum|at least|completed|completion of)\s+(?:of\s+)?(?:3|4|three|four)\s+(?:years?|academic terms|terms)\s+(?:of\s+)?(?:study|school|university|undergrad|completed|education)", re.I),
    re.compile(r"\brising\s+seniors?\b|\bcurrent(?:ly)?\s+(?:an?\s+)?(?:junior|senior)s?\b", re.I),
    re.compile(r"\bjunior\s+(?:or|and|/)\s+senior\b", re.I),
    re.compile(r"\b(?:junior|senior)[- ](?:level\s+)?standing\b", re.I),
    re.compile(r"\bclass of 20(?:2[5-9])\b", re.I),
]
GRAD = re.compile(
    r"\bgraduat\w*[^.;:\n]{0,90}?\b(20(?:2[5-9]|3\d))\b(?!\s*(?:or|and)\s*(?:later|after|beyond))", re.I)
GRAD_LATER = re.compile(r"\b(20\d\d)\s*(?:or|and)\s*(?:later|after|beyond)", re.I)


def _get(url, accept="text/html,application/json"):
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0 (compatible; mech-board/1.0)", "Accept": accept})
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.geturl(), r.read(2_000_000).decode("utf-8", "replace")


def _api_text(url):
    """Rewrite job-board URLs to their JSON APIs where the HTML is a JS shell."""
    p = urllib.parse.urlparse(url)
    host, path = p.netloc, p.path
    m = re.match(r"([\w-]+)\.wd\d+\.myworkdayjobs\.com$", host)
    if m:
        parts = [x for x in path.split("/") if x]
        if parts and re.match(r"^[a-z]{2}-[A-Z]{2}$", parts[0]):
            parts = parts[1:]
        if "job" in parts:
            i = parts.index("job")
            site = parts[i - 1] if i > 0 else ""
            api = f"https://{host}/wday/cxs/{m.group(1)}/{site}/" + "/".join(parts[i:])
            return _get(api, "application/json")[1]
    m = re.match(r"(wd\d+)\.myworkdaysite\.com$", host)
    if m:
        parts = [x for x in path.split("/") if x]
        if "recruiting" in parts and "job" in parts:
            r = parts.index("recruiting")
            tenant, site = parts[r + 1], parts[r + 2]
            api = f"https://{host}/wday/cxs/{tenant}/{site}/" + "/".join(parts[parts.index("job"):])
            return _get(api, "application/json")[1]
    if "greenhouse.io" in host:
        m = re.search(r"/([\w-]+)/jobs/(\d+)", path)
        if m:
            return html.unescape(_get(f"https://boards-api.greenhouse.io/v1/boards/{m.group(1)}/jobs/{m.group(2)}",
                                      "application/json")[1])
    if host == "jobs.lever.co":
        parts = [x for x in path.split("/") if x]
        if len(parts) >= 2:
            return _get(f"https://api.lever.co/v0/postings/{parts[0]}/{parts[1]}", "application/json")[1]
    return None


def page_text(url):
    text = _api_text(url)
    if text is None:
        final, raw = _get(url)
        if final != url:
            text = _api_text(final)
        if text is None:
            text = raw
    text = re.sub(r"<style[^>]*>[\s\S]*?</style>", " ", text, flags=re.I)
    text = html.unescape(re.sub(r"<[^>]+>", " ", text))
    text = text.replace("\\n", " ").replace("\\u0026", "&")
    return re.sub(r"\s+", " ", text)


def find_requirement(text):
    for pat in PATTERNS:
        for m in pat.finditer(text):
            # "2nd, 3rd or 4th year students" / "sophomore, junior or senior" include 2nd years
            before = text[max(0, m.start() - 45):m.start()]
            if re.search(r"\b(?:1st|2nd|first|second|sophomore|freshman|any)\b", before + m.group(0), re.I):
                continue
            return _snip(text, m)
    later = {int(y) for y in GRAD_LATER.findall(text)}
    for m in GRAD.finditer(text):
        year = int(m.group(1))
        if year < MY_GRAD and year not in later and not re.search(r"graduate (?:student|degree|program|school)", m.group(0), re.I):
            # "graduating between Dec 2027 and Jun 2030" includes 2030, so it's fine
            tail = text[m.end():m.end() + 40]
            if re.match(r"\s*(?:and|or|to|-|–|through)\s*(?:\w+\s+)?(20\d\d)", tail):
                end = int(re.match(r"\s*(?:and|or|to|-|–|through)\s*(?:\w+\s+)?(20\d\d)", tail).group(1))
                if end >= MY_GRAD:
                    continue
            return _snip(text, m)
    return ""


def _snip(text, m):
    a = max(0, m.start() - 40)
    b = min(len(text), m.end() + 40)
    s = text[a:b].strip()
    s = re.sub(r"^\S*\s", "", s) if a else s
    s = re.sub(r"\s\S*$", "", s) if b < len(text) else s
    return "…" + s + "…"


def check(jobs, cache):
    today = dt.date.today()
    done = 0
    for j in jobs:
        url = j["url"]
        c = cache.get(url)
        fresh = c and (today - dt.date.fromisoformat(c["checked"])).days < RECHECK_DAYS
        if not fresh and done < MAX_PER_RUN and not url.startswith(("https://jobs.magna.com/search", "https://wd3.myworkdaysite.com/en-US/recruiting/magna/Magna?")):
            done += 1
            try:
                text = page_text(url)
                c = {"checked": today.isoformat(), "read": len(text) > 800, "hit": find_requirement(text)}
            except Exception as e:
                c = {"checked": today.isoformat(), "read": False, "hit": "", "error": str(e)[:120]}
            cache[url] = c
        if c and c.get("hit") and not j.get("yr_manual"):
            j["yr"] = "no"
            j["yrwhy"] = "The posting asks for more than 2nd year: " + c["hit"]
        elif c and not c.get("read") and j.get("auto"):
            j["yrwhy"] = "Couldn't read this posting automatically: check its year and graduation requirements."
    return done
