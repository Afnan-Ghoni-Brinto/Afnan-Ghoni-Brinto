#!/usr/bin/env python3
"""Rewrite the projects block of README.md with cards for the latest public repos.

Runs inside GitHub Actions (see .github/workflows/update-readme.yml). Uses only the
standard library. GITHUB_TOKEN is optional but avoids API rate limits.
"""
import json
import os
import re
import urllib.request
from pathlib import Path

USER = os.environ.get("GH_USER", "Afnan-Ghoni-Brinto")
TOKEN = os.environ.get("GITHUB_TOKEN", "")
MAX_REPOS = 6
README = Path(__file__).resolve().parent.parent / "README.md"
START, END = "<!--PROJECTS:START-->", "<!--PROJECTS:END-->"
CARD = (
    "https://github-stats-extended.vercel.app/api/pin/"
    "?username={user}&repo={repo}&theme=tokyonight&hide_border=true&border_radius=12"
)


def fetch_repos():
    url = f"https://api.github.com/users/{USER}/repos?per_page=100&type=owner&sort=pushed"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json"})
    if TOKEN:
        req.add_header("Authorization", f"Bearer {TOKEN}")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.load(resp)


def pick(repos):
    chosen = [
        r for r in repos
        if not r.get("fork") and not r.get("archived") and r["name"].lower() != USER.lower()
    ]
    chosen.sort(key=lambda r: (r.get("stargazers_count", 0), r.get("pushed_at", "")), reverse=True)
    return chosen[:MAX_REPOS]


def render(repos):
    link = f"https://github.com/{USER}?tab=repositories"
    footer = f"🔎 **[Browse all my public repositories]({link})**"
    if not repos:
        return f"I'm building and improving projects as I continue learning.\n\n{footer}"

    cells = []
    for r in repos:
        href = r["html_url"]
        img = CARD.format(user=USER, repo=r["name"])
        cells.append(
            f'<td width="50%"><a href="{href}"><img src="{img}" alt="{r["name"]}" width="100%"/></a></td>'
        )
    rows = []
    for i in range(0, len(cells), 2):
        pair = cells[i:i + 2]
        if len(pair) == 1:
            pair.append('<td width="50%"></td>')
        rows.append("  <tr>" + "".join(pair) + "</tr>")
    table = '<table width="100%">\n' + "\n".join(rows) + "\n</table>"
    return f"{table}\n\n{footer}"


def main():
    text = README.read_text(encoding="utf-8")
    pattern = re.compile(re.escape(START) + r".*?" + re.escape(END), re.S)
    if not pattern.search(text):
        raise SystemExit("Markers not found in README.md")
    block = f"{START}\n<!-- Auto-generated daily by .github/workflows/update-readme.yml -->\n\n{render(pick(fetch_repos()))}\n\n{END}"
    new_text = pattern.sub(lambda _m: block, text)
    if new_text != text:
        README.write_text(new_text, encoding="utf-8")
        print("README.md updated")
    else:
        print("No changes")


if __name__ == "__main__":
    main()
