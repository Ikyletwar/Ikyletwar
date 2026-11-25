#!/usr/bin/env python3
"""
Generator data profil — Ikyletwar/Ikyletwar

Menarik data publik GitHub lewat REST, lalu menyuntik tiga blok markdown ke
README.md: daftar endpoint live, indeks repo, dan timestamp sinkronisasi.

Profil sengaja memakai markdown biasa: tanpa SVG animasi, tanpa badge neon,
tanpa dependency eksternal. Dijalankan harian oleh .github/workflows/profile.yml.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor

LOGIN = os.environ.get("PROFILE_LOGIN", "Ikyletwar")
SELF_REPO = "Ikyletwar"
API = "https://api.github.com"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
README = os.path.join(ROOT, "README.md")
TOKEN = (
    os.environ.get("GITHUB_TOKEN")
    or os.environ.get("GH_TOKEN")
    or os.environ.get("PROFILE_TOKEN")
    or ""
)


class Http:
    """Klien REST minimal dengan cache dan retry untuk rate limit."""

    def __init__(self, token: str) -> None:
        self.token = token
        self.cache: dict[str, object] = {}

    def _headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{LOGIN}-profile-generator",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def get(self, path: str, *, allow_404: bool = False):
        if path in self.cache:
            return self.cache[path]
        url = path if path.startswith("http") else API + path
        for attempt in range(3):
            request = urllib.request.Request(url, headers=self._headers())
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    data = json.loads(response.read().decode("utf-8"))
                self.cache[path] = data
                return data
            except urllib.error.HTTPError as exc:
                if exc.code == 404 and allow_404:
                    self.cache[path] = None
                    return None
                if exc.code in (403, 429) and attempt < 2:
                    time.sleep(2 + attempt * 3)
                    continue
                raise
            except (urllib.error.URLError, TimeoutError):
                if attempt < 2:
                    time.sleep(2 + attempt * 2)
                    continue
                raise
        return None


def collect(http: Http) -> list[dict]:
    """Ambil repo owner, tanpa repo profil, lengkap dengan status Pages dan bahasa."""
    raw_repos: list[dict] = []
    page = 1
    while True:
        chunk = http.get(
            f"/users/{LOGIN}/repos?per_page=100&page={page}&sort=pushed&type=owner"
        )
        if not chunk:
            break
        raw_repos.extend(chunk)
        if len(chunk) < 100:
            break
        page += 1

    targets = [raw for raw in raw_repos if raw["name"] != SELF_REPO]

    def enrich(raw: dict) -> tuple[dict, object, dict]:
        name = raw["name"]
        pages = None
        if not raw.get("archived"):
            pages = http.get(f"/repos/{LOGIN}/{name}/pages", allow_404=True)
        languages = http.get(f"/repos/{LOGIN}/{name}/languages") or {}
        return raw, pages, languages

    with ThreadPoolExecutor(max_workers=12) as pool:
        enriched = list(pool.map(enrich, targets))

    repos: list[dict] = []
    for raw, pages, languages in enriched:
        name = raw["name"]
        homepage = (raw.get("homepage") or "").strip()
        if not homepage and pages and pages.get("status") in (None, "built"):
            homepage = f"https://{LOGIN.lower()}.github.io/{name}/"
        total = sum(languages.values()) or 1
        language = max(languages.items(), key=lambda kv: kv[1])[0] if languages else (
            raw.get("language") or "—"
        )
        repos.append(
            {
                "name": name,
                "desc": raw.get("description") or "",
                "lang": language or "—",
                "stars": raw.get("stargazers_count", 0),
                "live": homepage,
                "pushed": raw.get("pushed_at", ""),
            }
        )

    repos.sort(key=lambda repo: repo["pushed"] or "", reverse=True)
    return repos


def ago(iso: str) -> str:
    if not iso:
        return "—"
    try:
        stamp = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    seconds = int((dt.datetime.now(dt.timezone.utc) - stamp).total_seconds())
    if seconds < 3600:
        return f"{max(seconds // 60, 1)}m lalu"
    if seconds < 86400:
        return f"{seconds // 3600}j lalu"
    if seconds < 86400 * 30:
        return f"{seconds // 86400}h lalu"
    if seconds < 86400 * 365:
        return f"{seconds // (86400 * 30)}bl lalu"
    return f"{seconds // (86400 * 365)}th lalu"


def live_block(repos: list[dict]) -> str:
    rows = ["| Project | Endpoint | Stack |", "|---|---|---|"]
    live = [repo for repo in repos if repo["live"]]
    live.sort(key=lambda repo: repo["name"].lower())
    for repo in live:
        rows.append(
            f"| [`{repo['name']}`](https://github.com/{LOGIN}/{repo['name']}) "
            f"| [live]({repo['live']}) | {repo['lang']} |"
        )
    if not live:
        rows.append("| — | — | — |")
    return "\n".join(rows)


def index_block(repos: list[dict]) -> str:
    rows = ["| Repo | Bahasa | ★ | Live | Update |", "|---|---|---:|---|---|"]
    for repo in repos:
        live = f"[live]({repo['live']})" if repo["live"] else "—"
        rows.append(
            f"| [`{repo['name']}`](https://github.com/{LOGIN}/{repo['name']}) "
            f"| {repo['lang']} | {repo['stars']} | {live} | {ago(repo['pushed'])} |"
        )
    return "\n".join(rows)


def stamp_block() -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return f"`last sync {now}`"


def inject(readme: str, name: str, block: str) -> str:
    pattern = re.compile(
        rf"(<!-- AUTO:{name} -->)(.*?)(<!-- /AUTO:{name} -->)", re.DOTALL
    )
    if not pattern.search(readme):
        print(f"  ! marker AUTO:{name} tidak ditemukan", file=sys.stderr)
        return readme
    return pattern.sub(lambda match: f"{match.group(1)}\n{block}\n{match.group(3)}", readme)


def main() -> int:
    if not TOKEN:
        print("! GITHUB_TOKEN kosong — memakai batas rate anonim (60/jam).")
    http = Http(TOKEN)
    print("→ mengambil data GitHub …")
    repos = collect(http)
    print(f"  {len(repos)} repo · {sum(1 for repo in repos if repo['live'])} live")

    with open(README, encoding="utf-8") as handle:
        readme = handle.read()
    for name, block in (
        ("LIVE", live_block(repos)),
        ("INDEX", index_block(repos)),
        ("STAMP", stamp_block()),
    ):
        readme = inject(readme, name, block)
    with open(README, "w", encoding="utf-8") as handle:
        handle.write(readme)
    print("→ README disuntik")
    return 0


if __name__ == "__main__":
    sys.exit(main())
