#!/usr/bin/env python3
"""Daily board update.

Pulls Summer 2027 internship listings from public GitHub trackers, keeps the
mechanical ones in Ontario and the US, merges them with the hand-curated list
and rebuilds index.html.

  data/curated.json  hand-picked roles (never touched by this script)
  data/auto.json     roles found automatically (rewritten every run)
  data/seen.json     first date each auto role was seen (drives the "new" chip)
"""
import datetime as dt
import json
import re
import sys
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
TODAY = dt.date.today().isoformat()

SOURCES = {
    "coawp": "https://raw.githubusercontent.com/coawp-com/Canadian-Engineering-Internships-2027/main/README.md",
    "simplify": "https://raw.githubusercontent.com/SimplifyJobs/Summer2027-Internships/dev/.github/scripts/listings.json",
}

MECH = re.compile(
    r"mechanic|mechatron|manufactur|product design|design eng|engineering design|hvac|"
    r"maintenance|reliability|field service|process eng|quality eng|industrial eng|robot|"
    r"aerospace|propulsion|thermal|test eng|prototyp|\bcad\b|cadd|drafting|tooling|automation|"
    r"production eng|millwright|energy eng|building system|equipment|plant eng|"
    r"\bmech\b|mold|machin(e|ing) design|fluid|structures|vehicle eng|powertrain|chassis",
    re.I)
NOT_MECH = re.compile(
    r"software|firmware|\bdata\b|machine learning|\bai\b|\bml\b|analog|digital ic|asic|silicon|"
    r"verification|validation eng|civil|environmental|chemical|geotech|transportation|highway|"
    r"marketing|finance|sales|accounting|business|\bhr\b|human resources|legal|cyber|\bit\b|"
    r"electrical eng(?!.*mechanical)|power eng|biomedical|pharma|clinical|nurs|"
    r"ph\.?d|master|mba|graduate|new grad|senior|architect(?!ural)|"
    r"electronic|digital|physical design|circuit|\bic\b|fpga|dsp|pcb|layout|research|scientist|"
    r"perception|learning|developer|product manag|analytics|audio|lending|insurance",
    re.I)
# the US list (SimplifyJobs) is mostly software and electronics, so it needs a clearly mechanical title
US_MECH = re.compile(
    r"mechanical|mechatron|manufactur|product design eng|hvac|maintenance|reliability eng|"
    r"field service|process eng|industrial eng|propulsion|thermal|prototyp|tooling|structures|"
    r"\bcad\b|design engineering intern$|mechanism|actuator|fluid", re.I)
GTA = re.compile(
    r"toronto|scarborough|etobicoke|north york|mississauga|brampton|markham|vaughan|concord|"
    r"woodbridge|richmond hill|oakville|burlington|milton|pickering|ajax|whitby|oshawa|newmarket|"
    r"aurora|stouffville|bolton|caledon|georgetown|hamilton|stoney creek|ancaster|^ontario$", re.I)
STOP = {"intern", "internship", "co", "op", "coop", "summer", "2027", "bachelors", "bachelor", "the",
        "and", "of", "for", "student", "students", "engineering", "eng", "engineer", "position", "term"}
WRONG_TERM = re.compile(r"\b(fall|winter)\b(?!.*summer)", re.I)
NON_US = re.compile(r"\bUK\b|United Kingdom|Ireland|India|Germany|Mexico|China|Japan|Israel|Poland")
ONTARIO = re.compile(r",\s*ON\b|ontario", re.I)
US_STATE = re.compile(r",\s*[A-Z]{2}(,\s*(USA|US|United States))?$|\bUSA\b|United States|Remote in USA")

CATS = [
    ("Aerospace", r"aero|space|propulsion|aircraft|satellite|rocket|flight|avionic|drone|uav"),
    ("Robotics", r"robot|mechatron|automation"),
    ("Automotive", r"automotive|vehicle|\bev\b|powertrain|chassis|battery pack"),
    ("Buildings/HVAC", r"hvac|building|\bmep\b|plumbing|fire protection"),
    ("Energy", r"energy|nuclear|utility|solar|wind|turbine|hydro|power plant|oil|gas"),
    ("Thermal", r"thermal|heat transfer"),
    ("Manufacturing", r"manufactur|process|production|quality|plant|maintenance|reliability|"
                      r"millwright|tooling|mold|operations|industrial"),
]
STRONG = re.compile(r"mechanical design|design eng|product design|\bcad\b|prototyp|"
                    r"maintenance|reliability|field service|mechanical eng", re.I)


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": "mech-board-updater"})
    with urllib.request.urlopen(req, timeout=60) as r:
        return r.read().decode("utf-8")


def slug(*parts):
    return re.sub(r"[^a-z0-9]+", "-", " ".join(parts).lower()).strip("-")[:90]


def norm(s):
    return re.sub(r"[^a-z0-9]", "", s.lower())


def strip_tags(s):
    return re.sub(r"<[^>]+>", " ", s).replace("&amp;", "&").strip()


def category(text):
    for name, pat in CATS:
        if re.search(pat, text, re.I):
            return name
    return "Design"


def months(text):
    m = re.findall(r"(\d+)\s*(?:or|,|/|-|to)?\s*(?=[\d\s,or/to-]*months?)", text)
    return sorted({x for x in m if 2 <= int(x) <= 24}, key=int)


def tokens(role):
    return {t for t in re.findall(r"[a-z0-9]+", role.lower().replace("mech ", "mechanical "))
            if t not in STOP}


def city(loc):
    return norm(re.split(r"[,/]", loc)[0])


def same(a, b):
    if norm(a["company"]) != norm(b["company"]):
        return False
    ca, cb = city(a["loc"]), city(b["loc"])
    if ca and cb and ca != cb and "ontario" not in (ca, cb):
        return False
    ta, tb = tokens(a["role"]), tokens(b["role"])
    if not ta or not tb:
        return False
    small = min(len(ta), len(tb))
    return (small >= 2 and (ta <= tb or tb <= ta)) or len(ta & tb) / len(ta | tb) >= 0.6


def is_mech(title):
    return bool(MECH.search(title)) and not NOT_MECH.search(title)


def make(company, role, loc, country, terms, posted, url, source, note="", usp=False):
    text = f"{company} {role}"
    strong = STRONG.search(role) and country == "Canada" and GTA.search(loc)
    if country == "Canada" and not GTA.search(loc):
        note = "; ".join(x for x in [note, "Outside the GTA/Hamilton: you'd need to relocate."] if x)
    return {
        "id": slug(company, role, loc), "company": company, "role": role, "loc": loc,
        "country": country, "terms": terms, "deadline": "", "posted": posted, "url": url,
        "check": False, "usp": usp, "cat": category(text), "source": source, "note": note,
        "yr": "ok", "yrwhy": "Found automatically: check the posting for year requirements.",
        "pick": 2 if strong else 0,
        "pickwhy": "Auto-flagged: core mechanical role in the GTA/Hamilton. Read the posting to confirm." if strong else "",
        "auto": True,
    }


def from_coawp(md):
    out, company = [], ""
    now = dt.date.today()
    for line in md.splitlines():
        if not line.startswith("| ") or line.startswith("| Company") or line.startswith("|:"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6:
            continue
        co, role, loc, term, posted, link = cells[:6]
        if co != "↳":
            company = strip_tags(co.replace("**", ""))
        role_parts = role.split("<br>")
        title = strip_tags(role_parts[0])
        extra = strip_tags(" ".join(role_parts[1:]))
        locs = [strip_tags(x) for x in re.split(r"<br>", loc) if not x.startswith("<sub>")]
        mode = " ".join(re.findall(r"<sub>(.*?)</sub>", loc))
        url = re.search(r"\((https?://[^)]+)\)", link)
        if not url or not is_mech(title) or WRONG_TERM.search(strip_tags(term)):
            continue
        on = [l for l in locs if ONTARIO.search(l)]
        if not on:
            continue
        if re.search(r"french", extra, re.I):
            continue
        p = ""
        m = re.match(r"([A-Z][a-z]{2}) (\d{1,2})", posted)
        if m:
            d = dt.datetime.strptime(f"{m.group(1)} {m.group(2)} {now.year}", "%b %d %Y").date()
            if d > now + dt.timedelta(days=2):
                d = d.replace(year=now.year - 1)
            p = d.isoformat()
        note = "; ".join(x for x in [extra, mode] if x)
        out.append(make(company, title, " / ".join(on), "Canada", months(strip_tags(term)), p,
                        url.group(1), "GitHub list: coawp Canadian Engineering Internships 2027 (auto)", note))
    return out


def from_simplify(raw):
    out = []
    for x in json.loads(raw):
        if not (x.get("active") and x.get("is_visible", True)):
            continue
        terms = x.get("terms") or []
        if not any(t in ("Summer 2027", "Spring 2027") for t in terms):
            continue
        title = x.get("title", "")
        if not is_mech(title):
            continue
        locs = x.get("locations") or []
        if not any(ONTARIO.search(l) for l in locs) and not US_MECH.search(title):
            continue
        on = [l.replace(", Canada", "") for l in locs if ONTARIO.search(l)]
        us = [l for l in locs if "Canada" not in l and not NON_US.search(l)
              and (US_STATE.search(l) or l in ("Remote", "SF", "NYC"))]
        if on:
            loc, country = " / ".join(on[:3]), "Canada"
        elif us and not any("Canada" in l for l in locs):
            loc, country = " / ".join(us[:3]) + (" +" if len(us) > 3 else ""), "USA"
        else:
            continue
        posted = dt.date.fromtimestamp(x["date_posted"]).isoformat() if x.get("date_posted") else ""
        usp = x.get("sponsorship") == "U.S. Citizenship is Required"
        out.append(make(x["company_name"], title, loc, country, [], posted, x["url"],
                        "GitHub list: SimplifyJobs Summer 2027 (auto)", usp=usp))
    return out


def main():
    curated = json.loads((DATA / "curated.json").read_text())
    seen_path = DATA / "seen.json"
    seen = json.loads(seen_path.read_text()) if seen_path.exists() else {}

    found, ok = [], 0
    for name, fn in (("coawp", from_coawp), ("simplify", from_simplify)):
        try:
            rows = fn(fetch(SOURCES[name]))
            found += rows
            ok += 1
            print(f"{name}: {len(rows)} mechanical roles")
        except Exception as e:  # one broken source shouldn't wipe the board
            print(f"{name}: FAILED ({e})", file=sys.stderr)
    if ok == 0:
        sys.exit("all sources failed; leaving the board unchanged")

    have_url = {j["url"] for j in curated}
    auto, ids = [], set()
    for j in found:
        if j["url"] in have_url or j["id"] in ids:
            continue
        if any(same(j, c) for c in curated) or any(same(j, a) for a in auto):
            continue
        ids.add(j["id"])
        j["added"] = seen.setdefault(j["id"], TODAY)
        auto.append(j)

    # if a source failed, keep its previous rows rather than dropping them
    old_path = DATA / "auto.json"
    if ok < len(SOURCES) and old_path.exists():
        for j in json.loads(old_path.read_text()):
            if j["id"] not in ids:
                auto.append(j)
                ids.add(j["id"])

    old_path.write_text(json.dumps(auto, ensure_ascii=False, indent=1))
    seen_path.write_text(json.dumps(seen, indent=1, sort_keys=True))

    jobs = curated + auto
    tpl = (ROOT / "template.html").read_text()
    stamp = dt.date.today().strftime("%B %-d, %Y")
    html = (tpl.replace("__UPDATED__", stamp)
               .replace("__JOBS__", json.dumps(jobs, ensure_ascii=False).replace("</", "<\\/")))
    (ROOT / "index.html").write_text(html)
    new = sum(1 for j in auto if j.get("added") == TODAY)
    print(f"curated {len(curated)} + auto {len(auto)} = {len(jobs)} roles; {new} new today")


if __name__ == "__main__":
    main()
