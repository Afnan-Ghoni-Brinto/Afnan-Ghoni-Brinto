#!/usr/bin/env python3
"""Generate the profile cards (stats, languages, streak, achievements) as SVG files.

No third-party image services are used, so nothing in the README can break because
someone else's server is down.

Usage:
    python3 scripts/generate_cards.py            # live: read the GitHub API
    python3 scripts/generate_cards.py --demo     # offline: use built-in sample data
    python3 scripts/generate_cards.py --sections # offline: (re)write the section headers

Live mode reads GITHUB_TOKEN (provided automatically inside GitHub Actions).
"""
import argparse
import datetime as dt
import json
import math
import os
import sys
import urllib.request
from html import escape as esc
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CARDS = ROOT / "assets" / "cards"
SECTIONS = ROOT / "assets" / "sections"
USER = os.environ.get("GH_USER", "Afnan-Ghoni-Brinto")
TOKEN = os.environ.get("GITHUB_TOKEN", "")

FONT = "'Segoe UI', Ubuntu, 'Helvetica Neue', Arial, sans-serif"
MONO = "Consolas, 'Courier New', monospace"

LANG_COLORS = {
    "C#": "#3FB950", "Java": "#E8A33D", "C++": "#F34B7D", "C": "#8892A0",
    "Python": "#4B8BBE", "HTML": "#E34C26", "CSS": "#8B5CF6", "JavaScript": "#F1E05A",
    "TypeScript": "#3178C6", "PHP": "#7A86B8", "Kotlin": "#A97BFF", "Dart": "#00B4AB",
    "Jupyter Notebook": "#F37626", "Shell": "#89E051", "Go": "#00ADD8", "Rust": "#DEA584",
    "Other": "#64748B",
}
FALLBACK = ["#00D9FF", "#FF4D8D", "#E8C77B", "#8B5CF6", "#27C93F", "#F97316"]

LEVELS = ["Seed", "Bronze", "Silver", "Gold", "Diamond"]
LEVEL_COLORS = ["#64748B", "#CD7F32", "#C0C8D4", "#E8C77B", "#00D9FF"]

# Sample data (taken from the first stats screenshot) used by --demo so the repo
# works on the very first push, before the workflow has run.
DEMO = {
    "stars": 1, "commits": 119, "prs": 0, "issues": 1, "contributed_to": 28,
    "langs": [("C#", 42.69), ("Java", 26.23), ("C++", 18.04), ("Python", 5.52),
              ("HTML", 4.14), ("CSS", 2.77), ("JavaScript", 0.62)],
    "total": 150, "since": "Dec 3, 2025",
    "cur": 13, "cur_range": "Nov 5 - Nov 17",
    "longest": 13, "long_range": "Nov 5 - Nov 17",
}

# ---------------------------------------------------------------- GitHub data

Q_YEAR = """query($login:String!,$from:DateTime!,$to:DateTime!){
  user(login:$login){ contributionsCollection(from:$from,to:$to){
    totalCommitContributions totalRepositoriesWithContributedCommits
    contributionCalendar{ weeks{ contributionDays{ date contributionCount } } }
  } } }"""
Q_TOTALS = """query($login:String!){ user(login:$login){
  pullRequests{ totalCount } issues{ totalCount } } }"""


def api(url, body=None):
    headers = {"Accept": "application/vnd.github+json", "User-Agent": "profile-cards"}
    if TOKEN:
        headers["Authorization"] = f"Bearer {TOKEN}"
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def graphql(query, variables):
    res = api("https://api.github.com/graphql",
              json.dumps({"query": query, "variables": variables}).encode())
    if res.get("errors"):
        raise RuntimeError(res["errors"])
    return res["data"]


def iso(d):
    return d.strftime("%Y-%m-%dT%H:%M:%SZ")


def short(d):
    return f"{d.strftime('%b')} {d.day}"


def full(d):
    return f"{d.strftime('%b')} {d.day}, {d.year}"


def streaks(days):
    dates = sorted(days)
    longest, run, run_start = (0, None, None), 0, None
    for ds in dates:
        d = dt.date.fromisoformat(ds)
        if days[ds] > 0:
            run += 1
            if run == 1:
                run_start = d
            if run > longest[0]:
                longest = (run, run_start, d)
        else:
            run = 0
    idx = len(dates) - 1
    if idx >= 0 and days[dates[idx]] == 0:  # today may still be empty
        idx -= 1
    cur, start, end = 0, None, None
    while idx >= 0 and days[dates[idx]] > 0:
        d = dt.date.fromisoformat(dates[idx])
        end = end or d
        start = d
        cur += 1
        idx -= 1
    rng = lambda a, b: f"{short(a)} - {short(b)}" if a and b else "No streak yet"
    return cur, rng(start, end), longest[0], rng(longest[1], longest[2])


def collect():
    user = api(f"https://api.github.com/users/{USER}")
    repos, page = [], 1
    while True:
        batch = api(f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner&page={page}")
        repos += batch
        if len(batch) < 100:
            break
        page += 1
    own = [r for r in repos if not r["fork"]]
    stars = sum(r["stargazers_count"] for r in own)

    by_lang = {}
    for r in own:
        if r["name"].lower() == USER.lower():  # skip the profile repo itself
            continue
        try:
            for k, v in api(r["languages_url"]).items():
                by_lang[k] = by_lang.get(k, 0) + v
        except Exception as exc:  # one bad repo should not break the cards
            print(f"languages failed for {r['name']}: {exc}", file=sys.stderr)
    total_bytes = sum(by_lang.values()) or 1
    langs = sorted(((k, v * 100 / total_bytes) for k, v in by_lang.items()), key=lambda x: -x[1])

    utc = dt.timezone.utc
    now = dt.datetime.now(utc)
    created = dt.datetime.fromisoformat(user["created_at"].replace("Z", "+00:00"))
    days = {}
    for year in range(created.year, now.year + 1):
        start = dt.datetime(year, 1, 1, tzinfo=utc)
        end = min(dt.datetime(year, 12, 31, 23, 59, 59, tzinfo=utc), now)
        cc = graphql(Q_YEAR, {"login": USER, "from": iso(start), "to": iso(end)})
        for w in cc["user"]["contributionsCollection"]["contributionCalendar"]["weeks"]:
            for d in w["contributionDays"]:
                days[d["date"]] = d["contributionCount"]

    roll = graphql(Q_YEAR, {"login": USER, "from": iso(now - dt.timedelta(days=365)), "to": iso(now)})
    roll = roll["user"]["contributionsCollection"]
    totals = graphql(Q_TOTALS, {"login": USER})["user"]

    cur, cur_range, longest, long_range = streaks(days)
    active = sorted(k for k, v in days.items() if v > 0)
    since = full(dt.date.fromisoformat(active[0])) if active else full(now.date())
    return {
        "stars": stars,
        "commits": roll["totalCommitContributions"],
        "prs": totals["pullRequests"]["totalCount"],
        "issues": totals["issues"]["totalCount"],
        "contributed_to": roll["totalRepositoriesWithContributedCommits"],
        "langs": langs,
        "total": sum(days.values()), "since": since,
        "cur": cur, "cur_range": cur_range, "longest": longest, "long_range": long_range,
    }


# ------------------------------------------------------------------ rendering

def reveal(delay, dur=0.6):
    total = delay + dur
    return (f'<animate attributeName="opacity" values="0;0;1" keyTimes="0;{delay / total:.3f};1" '
            f'dur="{total:.2f}s" begin="0s" fill="freeze"/>')


def shell(w, h, title, body, label):
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {w} {h}" width="{w}" height="{h}" role="img" aria-label="{esc(label)}">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#0D1117"/><stop offset="1" stop-color="#111B2E"/></linearGradient>
    <linearGradient id="acc" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#8B5CF6"/><stop offset="0.5" stop-color="#00D9FF"/><stop offset="1" stop-color="#FF4D8D"/></linearGradient>
  </defs>
  <rect x="1" y="1" width="{w - 2}" height="{h - 2}" rx="16" fill="url(#bg)" stroke="#30363D" stroke-width="2"/>
  <rect x="28" y="1" width="64" height="4" rx="2" fill="url(#acc)"/>
  <text x="28" y="46" font-family="{FONT}" font-size="20" font-weight="700" fill="#00D9FF">{esc(title)}</text>
{body}
</svg>
"""


def ring(cx, cy, r, frac, width=10):
    circ = 2 * math.pi * r
    final = circ * (1 - max(0.0, min(1.0, frac)))
    return f"""  <g transform="rotate(-90 {cx} {cy})">
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="#1F2937" stroke-width="{width}"/>
    <circle cx="{cx}" cy="{cy}" r="{r}" fill="none" stroke="url(#acc)" stroke-width="{width}" stroke-linecap="round" stroke-dasharray="{circ:.1f}" stroke-dashoffset="{final:.1f}">
      <animate attributeName="stroke-dashoffset" from="{circ:.1f}" to="{final:.1f}" dur="1.4s" fill="freeze"/>
    </circle>
  </g>"""


def tiles(d):
    spec = [
        ("Commits", d["commits"], [10, 50, 150, 500], ""),
        ("Stars Earned", d["stars"], [1, 5, 20, 50], ""),
        ("Pull Requests", d["prs"], [1, 5, 20, 50], ""),
        ("Issues", d["issues"], [1, 5, 15, 40], ""),
        ("Contributions", d["total"], [10, 100, 500, 1500], ""),
        ("Best Streak", d["longest"], [3, 7, 14, 30], " days"),
        ("Languages", len(d["langs"]), [2, 4, 6, 10], ""),
        ("Contributed To", d["contributed_to"], [1, 5, 15, 40], " repos"),
    ]
    out = []
    for name, val, th, suffix in spec:
        lvl = sum(1 for t in th if val >= t)
        prev = th[lvl - 1] if lvl else 0
        nxt = th[lvl] if lvl < len(th) else None
        frac = 1.0 if nxt is None else max(0.0, (val - prev) / (nxt - prev))
        out.append({"name": name, "val": val, "suffix": suffix, "lvl": lvl, "nxt": nxt, "frac": frac})
    return out


def grade(ts):
    total = sum(t["lvl"] for t in ts)
    for cutoff, letter in ((28, "S"), (22, "A+"), (16, "A"), (10, "B+"), (5, "B")):
        if total >= cutoff:
            return letter, total / (4 * len(ts))
    return "C", total / (4 * len(ts))


def card_stats(d):
    ts = tiles(d)
    letter, frac = grade(ts)
    rows = [("Total Stars Earned", d["stars"], "#E8C77B"),
            ("Commits (last year)", d["commits"], "#00D9FF"),
            ("Pull Requests", d["prs"], "#8B5CF6"),
            ("Issues Opened", d["issues"], "#FF4D8D"),
            ("Contributed to (last year)", d["contributed_to"], "#27C93F")]
    parts = []
    for i, (label, val, color) in enumerate(rows):
        y = 88 + i * 30
        parts.append(f"""  <g>{reveal(0.12 * i)}
    <circle cx="36" cy="{y - 5}" r="5" fill="{color}"/>
    <text x="52" y="{y}" font-family="{FONT}" font-size="14" fill="#C9D1D9">{esc(label)}</text>
    <text x="268" y="{y}" text-anchor="end" font-family="{FONT}" font-size="15" font-weight="700" fill="#E6EDF3">{val:,}</text>
  </g>""")
    parts.append(ring(342, 134, 46, frac))
    parts.append(f'  <text x="342" y="146" text-anchor="middle" font-family="{FONT}" font-size="32" font-weight="800" fill="#E8C77B">{letter}</text>')
    parts.append(f'  <text x="342" y="166" text-anchor="middle" font-family="{FONT}" font-size="10" letter-spacing="2" fill="#8B949E">RANK</text>')
    return shell(420, 236, "GitHub Stats", "\n".join(parts), "GitHub statistics")


def card_languages(d):
    langs = list(d["langs"])
    if len(langs) > 6:
        other = sum(p for _, p in langs[5:])
        langs = langs[:5] + [("Other", other)]
    total = sum(p for _, p in langs) or 1
    bw, x = 364, 28.0
    parts = []
    if not langs:
        parts.append(f'  <text x="28" y="100" font-family="{FONT}" font-size="14" fill="#8B949E">No language data yet.</text>')
        return shell(420, 236, "Most Used Languages", "\n".join(parts), "Most used languages")
    colored = []
    for i, (name, pct) in enumerate(langs):
        colored.append((name, pct, LANG_COLORS.get(name, FALLBACK[i % len(FALLBACK)])))
    parts.append(f"""  <defs>
    <clipPath id="barclip"><rect x="28" y="66" width="{bw}" height="12" rx="6"/></clipPath>
    <clipPath id="sweep"><rect x="28" y="60" width="{bw}" height="24"><animate attributeName="width" from="0" to="{bw}" dur="1.2s" fill="freeze"/></rect></clipPath>
  </defs>
  <g clip-path="url(#barclip)"><rect x="28" y="66" width="{bw}" height="12" fill="#1F2937"/><g clip-path="url(#sweep)">""")
    for name, pct, color in colored:
        seg = bw * pct / total
        parts.append(f'    <rect x="{x:.2f}" y="66" width="{seg:.2f}" height="12" fill="{color}"/>')
        x += seg
    parts.append("  </g></g>")
    for i, (name, pct, color) in enumerate(colored):
        col, row = i % 2, i // 2
        cx, y = 28 + col * 190, 112 + row * 34
        parts.append(f"""  <g>{reveal(0.1 * i + 0.3)}
    <circle cx="{cx + 5}" cy="{y - 5}" r="5" fill="{color}"/>
    <text x="{cx + 18}" y="{y}" font-family="{FONT}" font-size="14" fill="#C9D1D9">{esc(name)}</text>
    <text x="{cx + 172}" y="{y}" text-anchor="end" font-family="{FONT}" font-size="13" font-weight="700" fill="#E6EDF3">{pct * 100 / total:.1f}%</text>
  </g>""")
    return shell(420, 236, "Most Used Languages", "\n".join(parts), "Most used languages")


def card_streak(d):
    prog = min(1.0, d["cur"] / max(d["longest"], 1))
    p = []

    def col(cx, num, label, sub, color="#E6EDF3"):
        return f"""  <g>{reveal(0.2)}
    <text x="{cx}" y="116" text-anchor="middle" font-family="{FONT}" font-size="38" font-weight="800" fill="{color}">{num:,}</text>
    <text x="{cx}" y="144" text-anchor="middle" font-family="{FONT}" font-size="13" font-weight="600" fill="#8B949E">{esc(label)}</text>
    <text x="{cx}" y="164" text-anchor="middle" font-family="{FONT}" font-size="11" fill="#6E7681">{esc(sub)}</text>
  </g>"""
    p.append(col(150, d["total"], "Total Contributions", f"{d['since']} - Present", "#E8C77B"))
    p.append('  <line x1="290" y1="78" x2="290" y2="168" stroke="#30363D"/>')
    p.append('  <line x1="570" y1="78" x2="570" y2="168" stroke="#30363D"/>')
    p.append(ring(430, 112, 38, prog, 8))
    p.append(f'  <text x="430" y="122" text-anchor="middle" font-family="{FONT}" font-size="30" font-weight="800" fill="#00D9FF">{d["cur"]:,}</text>')
    p.append('  <circle cx="430" cy="74" r="10" fill="#0F1520"/>')
    p.append('  <path transform="translate(430 74) scale(0.8)" d="M0,-12 C5,-5 9,-1 7,6 C5,11 -5,11 -7,6 C-9,-1 -3,-5 0,-12Z" fill="#FF4D8D"><animate attributeName="opacity" values="1;0.55;1" dur="1.6s" repeatCount="indefinite"/></path>')
    p.append(f'  <text x="430" y="171" text-anchor="middle" font-family="{FONT}" font-size="13" font-weight="700" fill="#00D9FF">Current Streak</text>')
    p.append(f'  <text x="430" y="188" text-anchor="middle" font-family="{FONT}" font-size="11" fill="#6E7681">{esc(d["cur_range"])}</text>')
    p.append(col(710, d["longest"], "Longest Streak", d["long_range"], "#FF4D8D"))
    return shell(860, 204, "Contribution Streak", "\n".join(p), "Contribution streak")


def star_points(cx, cy, r_out=11, r_in=4.8):
    pts = []
    for k in range(10):
        r = r_out if k % 2 == 0 else r_in
        a = -math.pi / 2 + k * math.pi / 5
        pts.append(f"{cx + r * math.cos(a):.1f},{cy + r * math.sin(a):.1f}")
    return " ".join(pts)


def card_achievements(d):
    p = [f'  <text x="832" y="44" text-anchor="end" font-family="{FONT}" font-size="12" fill="#6E7681">Seed → Bronze → Silver → Gold → Diamond</text>']
    for i, t in enumerate(tiles(d)):
        x = 28 + (i % 4) * 204
        y = 68 + (i // 4) * 126
        c = LEVEL_COLORS[t["lvl"]]
        val = f"{t['val']:,}{t['suffix']}"
        nxt = "MAX LEVEL" if t["nxt"] is None else f"next: {t['nxt']:,}{t['suffix']}"
        star_fill = c if t["lvl"] else "none"
        p.append(f"""  <g>{reveal(0.12 * i)}
    <rect x="{x}" y="{y}" width="190" height="112" rx="12" fill="#0F1623" stroke="{c}" stroke-opacity="0.5" stroke-width="1.5"/>
    <circle cx="{x + 38}" cy="{y + 40}" r="22" fill="{c}" fill-opacity="0.14" stroke="{c}" stroke-width="2"/>
    <polygon points="{star_points(x + 38, y + 41)}" fill="{star_fill}" stroke="{c}" stroke-width="1.5" stroke-linejoin="round"/>
    <text x="{x + 70}" y="{y + 34}" font-family="{FONT}" font-size="11" letter-spacing="1" fill="#8B949E">{esc(t['name'].upper())}</text>
    <text x="{x + 70}" y="{y + 62}" font-family="{FONT}" font-size="22" font-weight="800" fill="{c}">{esc(val)}</text>
    <text x="{x + 16}" y="{y + 88}" font-family="{FONT}" font-size="11" font-weight="700" letter-spacing="1" fill="{c}">{LEVELS[t['lvl']].upper()}</text>
    <text x="{x + 174}" y="{y + 88}" text-anchor="end" font-family="{FONT}" font-size="11" fill="#6E7681">{esc(nxt)}</text>
    <rect x="{x + 16}" y="{y + 96}" width="158" height="6" rx="3" fill="#1F2937"/>
    <rect x="{x + 16}" y="{y + 96}" width="{158 * t['frac']:.1f}" height="6" rx="3" fill="{c}"><animate attributeName="width" from="0" to="{158 * t['frac']:.1f}" dur="1.2s" fill="freeze"/></rect>
  </g>""")
    return shell(860, 322, "Achievements", "\n".join(p), "Achievements earned from GitHub activity")


def section_svg(index, title):
    title = title.upper()
    x0 = 84 + int(len(title) * 21) + 24
    return f"""<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1200 64" width="1200" height="64" role="img" aria-label="{esc(title)}">
  <defs>
    <linearGradient id="t" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#E8C77B"/><stop offset="1" stop-color="#00D9FF"/></linearGradient>
    <linearGradient id="l" x1="0" y1="0" x2="1" y2="0"><stop offset="0" stop-color="#00D9FF" stop-opacity="0.9"/><stop offset="0.6" stop-color="#8B5CF6" stop-opacity="0.5"/><stop offset="1" stop-color="#8B5CF6" stop-opacity="0"/></linearGradient>
    <radialGradient id="g"><stop offset="0" stop-color="#FFFFFF"/><stop offset="0.4" stop-color="#00D9FF" stop-opacity="0.9"/><stop offset="1" stop-color="#00D9FF" stop-opacity="0"/></radialGradient>
  </defs>
  <rect x="2" y="4" width="1196" height="56" rx="14" fill="#0D1117" stroke="#30363D" stroke-width="2"/>
  <rect x="22" y="18" width="5" height="28" rx="2.5" fill="#00D9FF"><animate attributeName="opacity" values="1;0.35;1" dur="2.4s" repeatCount="indefinite"/></rect>
  <text x="44" y="39" font-family="{MONO}" font-size="16" fill="#6E7681">{index}</text>
  <text x="84" y="42" font-family="{FONT}" font-size="28" font-weight="800" letter-spacing="2" fill="url(#t)">{esc(title)}</text>
  <rect x="{x0}" y="31" width="{1170 - x0}" height="2" rx="1" fill="url(#l)"/>
  <circle cx="{x0}" cy="32" r="8" fill="url(#g)"><animate attributeName="cx" values="{x0};1160;{x0}" dur="6s" repeatCount="indefinite"/></circle>
</svg>
"""


SECTION_LIST = [("about", "About Me"), ("stack", "Tech Stack"), ("projects", "Projects"),
                ("stats", "GitHub Stats"), ("achievements", "Achievements"),
                ("snake", "Contribution Snake"), ("focus", "Currently"), ("connect", "Let's Connect")]


def write(folder, name, text):
    folder.mkdir(parents=True, exist_ok=True)
    (folder / name).write_text(text, encoding="utf-8")
    print("wrote", (folder / name).relative_to(ROOT))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--demo", action="store_true", help="use built-in sample data (offline)")
    ap.add_argument("--sections", action="store_true", help="write the section headers (offline)")
    args = ap.parse_args()

    if args.sections:
        for i, (slug, title) in enumerate(SECTION_LIST, 1):
            write(SECTIONS, f"{slug}.svg", section_svg(f"{i:02d}", title))
        if not args.demo:
            return
    data = DEMO if args.demo else collect()
    write(CARDS, "stats.svg", card_stats(data))
    write(CARDS, "languages.svg", card_languages(data))
    write(CARDS, "streak.svg", card_streak(data))
    write(CARDS, "achievements.svg", card_achievements(data))


if __name__ == "__main__":
    main()
