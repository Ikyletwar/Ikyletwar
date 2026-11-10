#!/usr/bin/env python3
"""
Profile asset generator — Ikyletwar/Ikyletwar
=============================================

Menarik data publik GitHub (REST + GraphQL), lalu membangun seluruh aset
visual profil (SVG animasi) dan menyuntikkannya ke README.md di antara
marker AUTO. Dijalankan oleh .github/workflows/profile.yml setiap hari.

Tanpa dependency eksternal: hanya Python 3.9+ standard library.
"""

from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

# ----------------------------------------------------------------------------
# Konfigurasi
# ----------------------------------------------------------------------------

LOGIN = os.environ.get("PROFILE_LOGIN", "Ikyletwar")
DISPLAY_NAME = os.environ.get("PROFILE_NAME", "HIZKIA LETWAR")
TAGLINE = "XI TJKT 1 · SMK Negeri 1 Maluku Tengah"
TOKEN = (
    os.environ.get("GITHUB_TOKEN")
    or os.environ.get("GH_TOKEN")
    or os.environ.get("PROFILE_TOKEN")
    or ""
)

API = "https://api.github.com"
GRAPHQL = "https://api.github.com/graphql"
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
ASSETS = os.path.join(ROOT, "assets")
CARDS = os.path.join(ASSETS, "cards")
README = os.path.join(ROOT, "README.md")
SELF_REPO = "Ikyletwar"

# Palet
C = {
    "bg0": "#03060d",
    "bg1": "#071120",
    "bg2": "#0b1a2e",
    "line": "#17324a",
    "text": "#e6f1ff",
    "dim": "#7d93ad",
    "cyan": "#22d3ee",
    "teal": "#2dd4bf",
    "blue": "#3b82f6",
    "violet": "#a78bfa",
    "amber": "#fbbf24",
    "rose": "#fb7185",
    "green": "#34d399",
}

LANG_COLORS = {
    "HTML": "#e34c26", "CSS": "#663399", "JavaScript": "#f1e05a",
    "TypeScript": "#3178c6", "Kotlin": "#a97bff", "Java": "#b07219",
    "Python": "#3572a5", "C": "#555555", "C++": "#f34b7d", "C#": "#178600",
    "Shell": "#89e051", "Dart": "#00b4ab", "Vue": "#41b883", "PHP": "#4f5d95",
    "Go": "#00add8", "Rust": "#dea584", "Swift": "#f05138", "Ruby": "#701516",
    "Jupyter Notebook": "#da5b0b", "Lua": "#000080", "Assembly": "#6e4c13",
}

LANG_ICONS = {
    "HTML": "html", "CSS": "css", "JavaScript": "js", "TypeScript": "ts",
    "Kotlin": "kotlin", "Java": "java", "Python": "py", "C": "c",
    "C++": "cpp", "Shell": "bash", "Dart": "dart", "Go": "go", "Rust": "rust",
    "PHP": "php", "Swift": "swift", "Ruby": "ruby", "Lua": "lua",
}

FONT = "'Segoe UI',Roboto,'Helvetica Neue',Arial,sans-serif"
MONO = "ui-monospace,'SF Mono','Cascadia Code','Fira Code',Consolas,monospace"

# ----------------------------------------------------------------------------
# HTTP
# ----------------------------------------------------------------------------


class Http:
    def __init__(self, token: str) -> None:
        self.token = token
        self.cache: dict[str, object] = {}

    def _headers(self) -> dict[str, str]:
        h = {
            "Accept": "application/vnd.github+json",
            "User-Agent": f"{LOGIN}-profile-generator",
            "X-GitHub-Api-Version": "2022-11-28",
        }
        if self.token:
            h["Authorization"] = f"Bearer {self.token}"
        return h

    def get(self, path: str, *, allow_404: bool = False):
        if path in self.cache:
            return self.cache[path]
        url = path if path.startswith("http") else API + path
        for attempt in range(3):
            req = urllib.request.Request(url, headers=self._headers())
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    data = json.loads(resp.read().decode("utf-8"))
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

    def graphql(self, query: str, variables: dict) -> dict:
        body = json.dumps({"query": query, "variables": variables}).encode()
        h = self._headers()
        h["Content-Type"] = "application/json"
        req = urllib.request.Request(GRAPHQL, data=body, headers=h)
        with urllib.request.urlopen(req, timeout=45) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        if "errors" in payload:
            raise RuntimeError(f"GraphQL: {payload['errors']}")
        return payload["data"]


# ----------------------------------------------------------------------------
# Util
# ----------------------------------------------------------------------------


def esc(text: str) -> str:
    return html.escape(str(text), quote=True)


def clip(text: str, limit: int) -> str:
    text = " ".join(str(text or "").split())
    if len(text) <= limit:
        return text
    return text[: limit - 1].rstrip(" ,.;:-") + "…"


def wrap(text: str, width: int, max_lines: int) -> list[str]:
    """Bungkus teks berdasarkan perkiraan lebar karakter."""
    text = " ".join(str(text or "").split())
    if not text:
        return []
    words, lines, cur = text.split(" "), [], ""
    for word in words:
        candidate = f"{cur} {word}".strip()
        if len(candidate) <= width:
            cur = candidate
            continue
        if cur:
            lines.append(cur)
        cur = word
        if len(lines) == max_lines - 1:
            break
    if cur and len(lines) < max_lines:
        rest = text[text.find(cur):] if cur in text else cur
        lines.append(clip(rest, width))
    if len(lines) > max_lines:
        lines = lines[:max_lines]
    return lines


def fmt_num(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.1f}M".replace(".0M", "M")
    if value >= 1_000:
        return f"{value / 1_000:.1f}k".replace(".0k", "k")
    return str(value)


def ago(iso: str) -> str:
    if not iso:
        return "—"
    try:
        stamp = dt.datetime.fromisoformat(iso.replace("Z", "+00:00"))
    except ValueError:
        return "—"
    delta = dt.datetime.now(dt.timezone.utc) - stamp
    seconds = int(delta.total_seconds())
    if seconds < 3600:
        return f"{max(seconds // 60, 1)}m ago"
    if seconds < 86400:
        return f"{seconds // 3600}h ago"
    if seconds < 86400 * 30:
        return f"{seconds // 86400}d ago"
    if seconds < 86400 * 365:
        return f"{seconds // (86400 * 30)}mo ago"
    return f"{seconds // (86400 * 365)}y ago"


def write(path: str, content: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def svg(width: int, height: int, body: str, defs: str = "") -> str:
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" fill="none" role="img">'
        f"<defs>{defs}</defs>{body}</svg>"
    )


# ----------------------------------------------------------------------------
# Data
# ----------------------------------------------------------------------------


def collect(http: Http) -> dict:
    user = http.get(f"/users/{LOGIN}")
    raw_repos = []
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

    def enrich(raw: dict) -> tuple[dict, dict | None, dict]:
        name = raw["name"]
        pages = None
        if not raw.get("archived"):
            pages = http.get(f"/repos/{LOGIN}/{name}/pages", allow_404=True)
        langs = http.get(f"/repos/{LOGIN}/{name}/languages") or {}
        return raw, pages, langs

    from concurrent.futures import ThreadPoolExecutor

    with ThreadPoolExecutor(max_workers=12) as pool:
        enriched = list(pool.map(enrich, targets))

    repos = []
    for raw, pages, langs in enriched:
        name = raw["name"]
        home = (raw.get("homepage") or "").strip()
        if not home and pages and pages.get("status") in (None, "built"):
            home = f"https://{LOGIN.lower()}.github.io/{name}/"
        release = {"tag_name": ""}
        total_bytes = sum(langs.values()) or 1
        top = max(langs.items(), key=lambda kv: kv[1])[0] if langs else (raw.get("language") or "")
        repos.append(
            {
                "name": name,
                "desc": raw.get("description") or "",
                "lang": top or "—",
                "lang_bytes": langs,
                "lang_share": (langs.get(top, 0) / total_bytes) if top else 0,
                "stars": raw.get("stargazers_count", 0),
                "forks": raw.get("forks_count", 0),
                "watchers": raw.get("watchers_count", 0),
                "issues": raw.get("open_issues_count", 0),
                "size": raw.get("size", 0),
                "topics": raw.get("topics") or [],
                "live": home,
                "archived": bool(raw.get("archived")),
                "fork": bool(raw.get("fork")),
                "license": (raw.get("license") or {}).get("spdx_id") or "",
                "created": raw.get("created_at", ""),
                "updated": raw.get("updated_at", ""),
                "pushed": raw.get("pushed_at", ""),
                "release": (release or {}).get("tag_name", ""),
                "default_branch": raw.get("default_branch", "main"),
            }
        )

    repos.sort(key=lambda r: r["pushed"] or "", reverse=True)

    cal = http.graphql(
        """
        query($login:String!){
          user(login:$login){
            contributionsCollection{
              totalCommitContributions
              totalPullRequestContributions
              totalIssueContributions
              totalRepositoryContributions
              contributionCalendar{
                totalContributions
                weeks{ contributionDays{ date contributionCount } }
              }
            }
          }
        }""",
        {"login": LOGIN},
    )["user"]["contributionsCollection"]

    days = [d for w in cal["contributionCalendar"]["weeks"] for d in w["contributionDays"]]
    days.sort(key=lambda d: d["date"])
    streak = longest = 0
    for day in days:
        if day["contributionCount"] > 0:
            streak += 1
            longest = max(longest, streak)
        else:
            streak = 0
    current = 0
    for day in reversed(days):
        if day["contributionCount"] > 0:
            current += 1
        else:
            break

    lang_totals: dict[str, int] = {}
    for repo in repos:
        for lang, count in repo["lang_bytes"].items():
            lang_totals[lang] = lang_totals.get(lang, 0) + count

    return {
        "user": user,
        "repos": repos,
        "total_contributions": cal["contributionCalendar"]["totalContributions"],
        "commits": cal["totalCommitContributions"],
        "prs": cal["totalPullRequestContributions"],
        "issues": cal["totalIssueContributions"],
        "days": days,
        "weeks": cal["contributionCalendar"]["weeks"],
        "streak": current,
        "longest": longest,
        "active_days": sum(1 for d in days if d["contributionCount"] > 0),
        "languages": dict(sorted(lang_totals.items(), key=lambda kv: -kv[1])),
        "stars": sum(r["stars"] for r in repos),
        "forks": sum(r["forks"] for r in repos),
        "live": sum(1 for r in repos if r["live"]),
    }


# ----------------------------------------------------------------------------
# SVG: hero
# ----------------------------------------------------------------------------


def build_hero(data: dict, stamp: str) -> str:
    w, h = 1280, 430
    defs = f"""
<linearGradient id="hg" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="{C['bg0']}"/><stop offset=".55" stop-color="{C['bg1']}"/><stop offset="1" stop-color="{C['bg2']}"/>
</linearGradient>
<radialGradient id="aur1" cx=".5" cy=".5" r=".5">
  <stop offset="0" stop-color="{C['cyan']}" stop-opacity=".55"/><stop offset="1" stop-color="{C['cyan']}" stop-opacity="0"/>
</radialGradient>
<radialGradient id="aur2" cx=".5" cy=".5" r=".5">
  <stop offset="0" stop-color="{C['violet']}" stop-opacity=".5"/><stop offset="1" stop-color="{C['violet']}" stop-opacity="0"/>
</radialGradient>
<radialGradient id="aur3" cx=".5" cy=".5" r=".5">
  <stop offset="0" stop-color="{C['amber']}" stop-opacity=".35"/><stop offset="1" stop-color="{C['amber']}" stop-opacity="0"/>
</radialGradient>
<linearGradient id="nameg" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="#e6f1ff"><animate attributeName="stop-color" values="#e6f1ff;#22d3ee;#a78bfa;#e6f1ff" dur="12s" repeatCount="indefinite"/></stop>
  <stop offset=".5" stop-color="#22d3ee"><animate attributeName="stop-color" values="#22d3ee;#a78bfa;#fbbf24;#22d3ee" dur="12s" repeatCount="indefinite"/></stop>
  <stop offset="1" stop-color="#a78bfa"><animate attributeName="stop-color" values="#a78bfa;#22d3ee;#e6f1ff;#a78bfa" dur="12s" repeatCount="indefinite"/></stop>
</linearGradient>
<pattern id="grid" width="34" height="34" patternUnits="userSpaceOnUse">
  <path d="M34 0H0V34" stroke="{C['line']}" stroke-opacity=".55" stroke-width="1"/>
</pattern>
<filter id="soft" x="-40%" y="-40%" width="180%" height="180%">
  <feGaussianBlur stdDeviation="26"/>
</filter>
<filter id="glow" x="-30%" y="-30%" width="160%" height="160%">
  <feGaussianBlur stdDeviation="3" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
</filter>
<mask id="typingmask">
  <rect x="62" y="278" width="0" height="30" fill="#fff">
    <animate attributeName="width" values="0;0;660;660;0" keyTimes="0;.08;.44;.9;1" dur="15s" repeatCount="indefinite"/>
  </rect>
</mask>
"""

    def chip(x: int, label: str, value: str, color: str, delay: float) -> str:
        return f"""
<g opacity="0">
  <animate attributeName="opacity" values="0;1" dur=".6s" begin="{delay}s" fill="freeze"/>
  <rect x="{x}" y="334" width="196" height="54" rx="13" fill="#061021" fill-opacity=".85" stroke="{color}" stroke-opacity=".42"/>
  <rect x="{x}" y="334" width="4" height="54" rx="2" fill="{color}">
    <animate attributeName="opacity" values=".35;1;.35" dur="2.8s" begin="{delay}s" repeatCount="indefinite"/>
  </rect>
  <text x="{x + 20}" y="357" font-family="{MONO}" font-size="10.5" letter-spacing="2.2" fill="{C['dim']}">{esc(label)}</text>
  <text x="{x + 20}" y="378" font-family="{FONT}" font-size="16" font-weight="700" fill="{C['text']}">{esc(value)}</text>
</g>"""

    body = f"""
<rect width="{w}" height="{h}" rx="18" fill="url(#hg)"/>
<rect width="{w}" height="{h}" rx="18" fill="url(#grid)" opacity=".5"/>
<g filter="url(#soft)" opacity=".9">
  <circle cx="240" cy="90" r="170" fill="url(#aur1)">
    <animateTransform attributeName="transform" type="translate" values="0,0;70,34;0,0" dur="17s" repeatCount="indefinite"/>
  </circle>
  <circle cx="1030" cy="120" r="190" fill="url(#aur2)">
    <animateTransform attributeName="transform" type="translate" values="0,0;-84,48;0,0" dur="21s" repeatCount="indefinite"/>
  </circle>
  <circle cx="700" cy="380" r="150" fill="url(#aur3)">
    <animateTransform attributeName="transform" type="translate" values="0,0;40,-34;0,0" dur="14s" repeatCount="indefinite"/>
  </circle>
</g>

<!-- scanline -->
<rect x="0" y="-4" width="{w}" height="3" fill="{C['cyan']}" opacity=".18">
  <animate attributeName="y" values="-4;{h + 4}" dur="7.5s" repeatCount="indefinite"/>
</rect>

<!-- frame corners -->
<g stroke="{C['cyan']}" stroke-opacity=".55" stroke-width="1.4" fill="none">
  <path d="M18 58V18h40"/><path d="M{w - 18} 58V18h-40"/>
  <path d="M18 {h - 58}v40h40"/><path d="M{w - 18} {h - 58}v40h-40"/>
</g>

<!-- status -->
<g>
  <circle cx="36" cy="36" r="4.5" fill="{C['green']}">
    <animate attributeName="opacity" values="1;.25;1" dur="1.8s" repeatCount="indefinite"/>
  </circle>
  <text x="50" y="40.5" font-family="{MONO}" font-size="11" letter-spacing="1.6" fill="{C['dim']}">ONLINE · AUTO-GENERATED · {esc(stamp)}</text>
</g>
<text x="{w - 36}" y="40.5" text-anchor="end" font-family="{MONO}" font-size="11" letter-spacing="1.6" fill="{C['dim']}">@{esc(LOGIN)}</text>

<!-- name -->
<text x="64" y="176" font-family="{FONT}" font-size="17" letter-spacing="7" fill="{C['cyan']}" opacity=".9">SYSTEMS · APPS · RESEARCH</text>
<g filter="url(#glow)">
  <text x="62" y="262" font-family="{FONT}" font-size="72" font-weight="800" letter-spacing="-1.5" fill="url(#nameg)">{esc(DISPLAY_NAME)}</text>
</g>
<text x="64" y="296" font-family="{MONO}" font-size="15" fill="{C['dim']}" mask="url(#typingmask)">static-first · offline-first · mobile-first · reverse-engineering</text>
<rect x="730" y="281" width="2" height="19" fill="{C['cyan']}">
  <animate attributeName="opacity" values="1;0;1" dur="1.1s" repeatCount="indefinite"/>
</rect>

<!-- chips -->
{chip(64, "FOCUS", "WEB / PWA / ANDROID", C['cyan'], 0.9)}
{chip(276, "PROJECT REPOS", str(len(data['repos'])), C['violet'], 1.15)}
{chip(488, "LIVE DEMOS", str(data['live']), C['amber'], 1.4)}
{chip(700, "CONTRIBUTIONS / YR", fmt_num(data['total_contributions']), C['green'], 1.65)}

<!-- corner glyph -->
<g opacity=".5" font-family="{MONO}" font-size="10" fill="{C['dim']}">
  <text x="{w - 40}" y="{h - 30}" text-anchor="end">rendered by generate.py</text>
</g>
"""
    return svg(w, h, body, defs)


# ----------------------------------------------------------------------------
# SVG: typing + terminal
# ----------------------------------------------------------------------------


def build_terminal(data: dict) -> str:
    langs = list(data["languages"])[:5]
    live_names = [r["name"] for r in data["repos"] if r["live"]][:3]
    lines = [
        ("$", "neofetch --profile", C["cyan"]),
        ("", f"user      {LOGIN} ({DISPLAY_NAME.title()})", C["text"]),
        ("", f"role      {TAGLINE}", C["text"]),
        ("", f"repos     {len(data['repos'])} public · {data['live']} live demos", C["text"]),
        ("", f"streak    {data['streak']}d current · {data['longest']}d best · {data['active_days']} active days", C["text"]),
        ("", f"langs     {' · '.join(langs) if langs else '—'}", C["text"]),
        ("$", "ls --featured", C["cyan"]),
        ("", " · ".join(live_names) if live_names else "—", C["amber"]),
        ("$", "echo $PHILOSOPHY", C["cyan"]),
        ("", '"bikin sampai jalan dulu, lalu perbaiki sampai layak dipakai"', C["green"]),
    ]
    w = 1180
    line_h = 27
    h = 96 + line_h * len(lines) + 30
    rows = []
    for i, (prompt, text, color) in enumerate(lines):
        y = 118 + i * line_h
        delay = 0.55 + i * 0.42
        prompt_txt = f'<text x="44" y="{y}" font-family="{MONO}" font-size="13.5" fill="{C["cyan"]}">{esc(prompt)}</text>' if prompt else ""
        x = 76 if prompt else 44
        rows.append(
            f'<g opacity="0"><animate attributeName="opacity" values="0;1" dur=".28s" begin="{delay:.2f}s" fill="freeze"/>'
            f'{prompt_txt}<text x="{x}" y="{y}" font-family="{MONO}" font-size="13.5" fill="{color}">{esc(text)}</text></g>'
        )
    cursor_y = 118 + len(lines) * line_h
    defs = f"""
<linearGradient id="tg" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#050b14"/><stop offset="1" stop-color="#08172a"/>
</linearGradient>
<linearGradient id="tbar" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{C['cyan']}" stop-opacity=".85"/><stop offset=".5" stop-color="{C['violet']}" stop-opacity=".6"/><stop offset="1" stop-color="{C['amber']}" stop-opacity=".75"/>
</linearGradient>
"""
    body = f"""
<rect width="{w}" height="{h}" rx="16" fill="url(#tg)" stroke="{C['line']}"/>
<rect width="{w}" height="44" rx="16" fill="#0a1524"/>
<rect y="30" width="{w}" height="14" fill="#0a1524"/>
<rect y="43" width="{w}" height="2" fill="url(#tbar)">
  <animate attributeName="opacity" values=".55;1;.55" dur="6s" repeatCount="indefinite"/>
</rect>
<circle cx="28" cy="23" r="6" fill="#ff5f57"/><circle cx="50" cy="23" r="6" fill="#febc2e"/><circle cx="72" cy="23" r="6" fill="#28c840"/>
<text x="{w / 2}" y="27.5" text-anchor="middle" font-family="{MONO}" font-size="11.5" fill="{C['dim']}">zsh — {esc(LOGIN)}@github — 118×40</text>
{''.join(rows)}
<rect x="44" y="{cursor_y - 12}" width="8" height="15" fill="{C['cyan']}">
  <animate attributeName="opacity" values="1;0;1" dur="1.05s" repeatCount="indefinite"/>
</rect>
<text x="{w - 26}" y="{h - 18}" text-anchor="end" font-family="{MONO}" font-size="10" fill="{C['dim']}" opacity=".8">data: GitHub REST + GraphQL · {esc(stamp_date())}</text>
"""
    return svg(w, h, body, defs)


# ----------------------------------------------------------------------------
# SVG: marquee
# ----------------------------------------------------------------------------


def build_marquee() -> str:
    items = [
        ("HTML5", C["rose"]), ("CSS3", C["blue"]), ("JavaScript", "#f1e05a"),
        ("Tailwind", C["cyan"]), ("Node.js", C["green"]), ("Express", C["dim"]),
        ("Kotlin", C["violet"]), ("Compose", "#4285f4"), ("Java", "#b07219"),
        ("Python", "#3572a5"), ("C / NDK", "#8b949e"), ("PWA", C["teal"]),
        ("SQLite", "#0f80cc"), ("Room", C["green"]), ("Git", "#f05032"),
        ("GitHub Actions", C["cyan"]), ("radare2", C["rose"]), ("mitmproxy", C["amber"]),
        ("Frida", "#f97316"), ("apktool", C["teal"]), ("Three.js", "#e6f1ff"),
        ("Cerebras AI", C["violet"]),
    ]
    w, h = 1280, 86
    span = 1300
    seq = "".join(
        f'<text x="{i * 150}" y="50" font-family="{MONO}" font-size="15" fill="{color}">{esc(name)}</text>'
        f'<text x="{i * 150 + len(name) * 9 + 22}" y="50" font-family="{MONO}" font-size="15" fill="{C["dim"]}">/</text>'
        for i, (name, color) in enumerate(items)
    )

    def track(offset: int, dur: str) -> str:
        return (
            f'<g><animateTransform attributeName="transform" type="translate" '
            f'values="0,0;-{span},0" dur="{dur}" repeatCount="indefinite"/>'
            f'<g transform="translate({offset},0)">{seq}</g></g>'
        )

    defs = f"""
<linearGradient id="mf" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{C['bg0']}"/><stop offset=".12" stop-color="{C['bg0']}" stop-opacity="0"/>
  <stop offset=".88" stop-color="{C['bg0']}" stop-opacity="0"/><stop offset="1" stop-color="{C['bg0']}"/>
</linearGradient>
"""
    body = f"""
<rect width="{w}" height="{h}" rx="12" fill="{C['bg1']}" stroke="{C['line']}"/>
<rect y="21" width="{w}" height="1" fill="{C['line']}" opacity=".6"/>
<rect y="64" width="{w}" height="1" fill="{C['line']}" opacity=".6"/>
{track(0, '26s')}{track(span, '26s')}
<rect width="{w}" height="{h}" fill="url(#mf)"/>
<text x="18" y="50" font-family="{MONO}" font-size="10" fill="{C['cyan']}">STACK</text>
"""
    return svg(w, h, body, defs)


# ----------------------------------------------------------------------------
# SVG: dashboard
# ----------------------------------------------------------------------------


def build_dashboard(data: dict) -> str:
    w, h = 1280, 470
    langs = list(data["languages"].items())[:5]
    total = sum(v for _, v in langs) or 1
    stats = [
        ("PUBLIC REPOS", str(len(data["repos"])), C["cyan"]),
        ("LIVE DEMOS", str(data["live"]), C["amber"]),
        ("STARS / FORKS", f"{data['stars']} / {data['forks']}", C["violet"]),
        ("CONTRIB / 12 MO", fmt_num(data["total_contributions"]), C["green"]),
    ]
    tiles = []
    for i, (label, value, color) in enumerate(stats):
        x = 28 + i * 306
        tiles.append(
            f'<g><rect x="{x}" y="28" width="278" height="92" rx="14" fill="#061021" stroke="{C["line"]}"/>'
            f'<rect x="{x}" y="28" width="278" height="3" rx="1.5" fill="{color}"><animate attributeName="opacity" values=".4;1;.4" dur="3.4s" begin="{i * .3}s" repeatCount="indefinite"/></rect>'
            f'<text x="{x + 18}" y="60" font-family="{MONO}" font-size="10.5" letter-spacing="2" fill="{C["dim"]}">{esc(label)}</text>'
            f'<text x="{x + 18}" y="100" font-family="{FONT}" font-size="30" font-weight="800" fill="{color}">{esc(value)}</text></g>'
        )

    bars = []
    for i, (lang, count) in enumerate(langs):
        pct = count / total
        y = 176 + i * 46
        color = LANG_COLORS.get(lang, C["cyan"])
        bars.append(
            f'<g><text x="44" y="{y + 13}" font-family="{MONO}" font-size="12.5" fill="{C["text"]}">{esc(lang)}</text>'
            f'<text x="640" y="{y + 13}" text-anchor="end" font-family="{MONO}" font-size="12" fill="{C["dim"]}">{pct * 100:.1f}%</text>'
            f'<rect x="44" y="{y + 21}" width="{600}" height="8" rx="4" fill="#0d2136"/>'
            f'<rect x="44" y="{y + 21}" width="0" height="8" rx="4" fill="{color}">'
            f'<animate attributeName="width" from="0" to="{max(6, int(600 * pct))}" dur="1.5s" begin="{0.4 + i * .12:.2f}s" fill="freeze" calcMode="spline" keySplines=".22,1,.36,1" keyTimes="0;1"/></rect></g>'
        )

    # donut
    cx, cy, r = 890, 250, 78
    circumference = 2 * 3.141592653589793 * r
    offset = 0.0
    arcs = []
    for i, (lang, count) in enumerate(langs):
        share = count / total
        color = LANG_COLORS.get(lang, C["cyan"])
        dash = circumference * share
        arcs.append(
            f'<circle cx="{cx}" cy="{cy}" r="{r}" stroke="{color}" stroke-width="20" fill="none" '
            f'stroke-dasharray="0 {circumference:.2f}" stroke-dashoffset="{-offset:.2f}" transform="rotate(-90 {cx} {cy})" opacity=".95">'
            f'<animate attributeName="stroke-dasharray" from="0 {circumference:.2f}" to="{dash:.2f} {circumference - dash:.2f}" dur="1.4s" begin="{0.5 + i * .15:.2f}s" fill="freeze"/>'
            f"</circle>"
        )
        offset += dash
    arcs.append(
        f'<text x="{cx}" y="{cy - 4}" text-anchor="middle" font-family="{FONT}" font-size="26" font-weight="800" fill="{C["text"]}">{len(data["languages"])}</text>'
        f'<text x="{cx}" y="{cy + 18}" text-anchor="middle" font-family="{MONO}" font-size="9.5" letter-spacing="1.5" fill="{C["dim"]}">LANGUAGES</text>'
    )

    defs = f"""
<linearGradient id="dg" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#040a14"/><stop offset="1" stop-color="#0a1a2d"/>
</linearGradient>
<pattern id="dgrid" width="26" height="26" patternUnits="userSpaceOnUse">
  <path d="M26 0H0V26" stroke="{C['line']}" stroke-opacity=".35"/>
</pattern>
"""
    body = f"""
<rect width="{w}" height="{h}" rx="18" fill="url(#dg)"/>
<rect width="{w}" height="{h}" rx="18" fill="url(#dgrid)"/>
<text x="28" y="18" font-family="{MONO}" font-size="10" letter-spacing="2" fill="{C['dim']}"> </text>
{''.join(tiles)}
<text x="44" y="158" font-family="{MONO}" font-size="10.5" letter-spacing="2.4" fill="{C['cyan']}">LANGUAGE MIX — BYTES OF CODE</text>
{''.join(bars)}
{''.join(arcs)}
<g font-family="{MONO}" font-size="11" fill="{C['dim']}">
  <text x="44" y="425">STREAK {data['streak']}d</text>
  <text x="180" y="425">LONGEST {data['longest']}d</text>
  <text x="350" y="425">ACTIVE DAYS {data['active_days']}</text>
  <text x="{w - 26}" y="425" text-anchor="end">auto-refresh daily · {esc(stamp_date())}</text>
</g>
<rect x="28" y="442" width="{w - 56}" height="1" fill="{C['line']}"/>
"""
    return svg(w, h, body, defs)


# ----------------------------------------------------------------------------
# SVG: streak + activity
# ----------------------------------------------------------------------------


def build_streak(data: dict) -> str:
    w, h = 1180, 210
    items = [
        ("TOTAL CONTRIBUTIONS", fmt_num(data["total_contributions"]), C["cyan"]),
        ("CURRENT STREAK", f"{data['streak']} days", C["amber"]),
        ("LONGEST STREAK", f"{data['longest']} days", C["rose"]),
        ("COMMITS / 12 MO", fmt_num(data["commits"]), C["green"]),
    ]
    cells = []
    for i, (label, value, color) in enumerate(items):
        x = 24 + i * 289
        cells.append(
            f'<g><rect x="{x}" y="26" width="265" height="112" rx="14" fill="#061021" stroke="{C["line"]}"/>'
            f'<circle cx="{x + 26}" cy="58" r="5" fill="{color}"><animate attributeName="r" values="4;6;4" dur="2.4s" begin="{i * .25}s" repeatCount="indefinite"/></circle>'
            f'<text x="{x + 42}" y="63" font-family="{MONO}" font-size="9.5" letter-spacing="1.6" fill="{C["dim"]}">{esc(label)}</text>'
            f'<text x="{x + 22}" y="112" font-family="{FONT}" font-size="27" font-weight="800" fill="{C["text"]}">{esc(value)}</text></g>'
        )
    defs = f"""<linearGradient id="sg" x1="0" y1="0" x2="1" y2="1">
  <stop offset="0" stop-color="#050b15"/><stop offset="1" stop-color="#091a2c"/></linearGradient>"""
    body = f"""
<rect width="{w}" height="{h}" rx="16" fill="url(#sg)" stroke="{C['line']}"/>
{''.join(cells)}
<text x="24" y="176" font-family="{MONO}" font-size="10.5" fill="{C['dim']}">commit · pull request · issue · repository — rolling 12 months</text>
<text x="{w - 24}" y="176" text-anchor="end" font-family="{MONO}" font-size="10.5" fill="{C['cyan']}">@{esc(LOGIN)}</text>
"""
    return svg(w, h, body, defs)


def build_activity(data: dict) -> str:
    days = data["days"][-35:]
    w, h = 1180, 250
    left, right, top, base = 44, w - 32, 56, 196
    peak = max((d["contributionCount"] for d in days), default=1) or 1
    step = (right - left) / max(len(days) - 1, 1)
    bars = []
    for i, day in enumerate(days):
        count = day["contributionCount"]
        bar_h = max(3, (count / peak) * (base - top))
        x = left + i * step
        intensity = count / peak
        color = C["cyan"] if intensity < 0.5 else (C["teal"] if intensity < 0.85 else C["amber"])
        bars.append(
            f'<rect x="{x - 6:.1f}" y="{base - bar_h:.1f}" width="12" height="{bar_h:.1f}" rx="3" fill="{color}" opacity="0">'
            f'<animate attributeName="opacity" values="0;{0.45 + 0.5 * intensity:.2f}" dur=".5s" begin="{i * .035:.2f}s" fill="freeze"/></rect>'
        )
    total_recent = sum(d["contributionCount"] for d in days)
    body = f"""
<rect width="{w}" height="{h}" rx="16" fill="#050b15" stroke="{C['line']}"/>
<text x="44" y="34" font-family="{MONO}" font-size="10.5" letter-spacing="2.4" fill="{C['cyan']}">ACTIVITY — LAST {len(days)} DAYS</text>
<text x="{w - 32}" y="34" text-anchor="end" font-family="{MONO}" font-size="11" fill="{C['dim']}">{total_recent} contributions · peak {peak}/day</text>
<g stroke="{C['line']}" stroke-dasharray="3 5" opacity=".7">
  <line x1="{left}" y1="{top}" x2="{right}" y2="{top}"/>
  <line x1="{left}" y1="{(top + base) / 2}" x2="{right}" y2="{(top + base) / 2}"/>
  <line x1="{left}" y1="{base}" x2="{right}" y2="{base}"/>
</g>
{''.join(bars)}
<text x="{left}" y="{h - 18}" font-family="{MONO}" font-size="10" fill="{C['dim']}">{esc(days[0]['date'])}</text>
<text x="{right}" y="{h - 18}" text-anchor="end" font-family="{MONO}" font-size="10" fill="{C['dim']}">{esc(days[-1]['date'])}</text>
"""
    return svg(w, h, body, "")


# ----------------------------------------------------------------------------
# SVG: contribution snake
# ----------------------------------------------------------------------------


def build_snake(data: dict) -> str:
    weeks = data["weeks"]
    cell, gap = 13, 3
    step = cell + gap
    left, top = 46, 74
    w = left + len(weeks) * step + 30
    h = top + 7 * step + 52
    counts = [d["contributionCount"] for w_ in weeks for d in w_["contributionDays"]]
    peak = max(counts) or 1

    def level(count: int) -> int:
        if count <= 0:
            return 0
        ratio = count / peak
        return 1 if ratio < 0.25 else 2 if ratio < 0.5 else 3 if ratio < 0.78 else 4

    palette = ["#0b1f33", "#134e5e", "#0e7490", "#22d3ee", "#a5f3fc"]
    cells, path_points = [], []
    for wi, week in enumerate(weeks):
        for di, day in enumerate(week["contributionDays"]):
            x = left + wi * step
            y = top + di * step
            color = palette[level(day["contributionCount"])]
            delay = wi * 0.018 + di * 0.008
            cells.append(
                f'<rect x="{x}" y="{y}" width="{cell}" height="{cell}" rx="3" fill="{color}">'
                f'<animate attributeName="opacity" values=".25;1" dur=".45s" begin="{delay:.2f}s" fill="freeze"/></rect>'
            )
            path_points.append((x + cell / 2, y + cell / 2))

    # jalur ular: zig-zag boustrophedon yang melewati semua sel
    ordered = []
    for wi, week in enumerate(weeks):
        column = [(left + wi * step + cell / 2, top + di * step + cell / 2) for di in range(len(week["contributionDays"]))]
        ordered.extend(column if wi % 2 == 0 else list(reversed(column)))
    path = f"M {ordered[0][0]:.1f} {ordered[0][1]:.1f} " + " ".join(
        f"L {x:.1f} {y:.1f}" for x, y in ordered[1:]
    )
    defs = f"""
<linearGradient id="snakeg" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{C['cyan']}" stop-opacity=".1"/>
  <stop offset=".5" stop-color="{C['cyan']}" stop-opacity=".95"/>
  <stop offset="1" stop-color="{C['violet']}" stop-opacity=".2"/>
</linearGradient>
<filter id="sglow" x="-20%" y="-20%" width="140%" height="140%">
  <feGaussianBlur stdDeviation="4" result="b"/><feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>
</filter>
"""
    body = f"""
<rect width="{w}" height="{h}" rx="16" fill="#050b15" stroke="{C['line']}"/>
<text x="{left}" y="34" font-family="{MONO}" font-size="10.5" letter-spacing="2.4" fill="{C['cyan']}">CONTRIBUTION SNAKE — 12 MONTHS · {data['total_contributions']} CONTRIBUTIONS</text>
<g opacity=".55">
  <text x="{left}" y="56" font-family="{MONO}" font-size="9.5" fill="{C['dim']}">less</text>
  {''.join(f'<rect x="{left + 34 + i * 16}" y="47" width="11" height="11" rx="2" fill="{palette[i]}"/>' for i in range(5))}
  <text x="{left + 130}" y="56" font-family="{MONO}" font-size="9.5" fill="{C['dim']}">more</text>
</g>
{''.join(cells)}
<g filter="url(#sglow)">
  <path d="{path}" stroke="url(#snakeg)" stroke-width="3" stroke-linecap="round" fill="none" opacity=".75">
    <animate attributeName="stroke-dasharray" values="0 3200;200 3200" dur="9s" repeatCount="indefinite"/>
  </path>
  <circle r="6" fill="{C['cyan']}">
    <animateMotion dur="9s" repeatCount="indefinite" path="{path}"/>
  </circle>
  <circle r="12" fill="{C['cyan']}" opacity=".35">
    <animateMotion dur="9s" repeatCount="indefinite" path="{path}"/>
  </circle>
</g>
<text x="{left}" y="{h - 16}" font-family="{MONO}" font-size="10" fill="{C['dim']}">generated from the public contribution calendar · {esc(stamp_date())}</text>
"""
    return svg(w, h, body, defs)


# ----------------------------------------------------------------------------
# SVG: repo card
# ----------------------------------------------------------------------------


def build_card(repo: dict) -> str:
    w, h = 420, 172
    color = LANG_COLORS.get(repo["lang"], C["cyan"])
    desc_lines = wrap(repo["desc"], 50, 3) or ["No description provided."]
    live = repo["live"]
    body = [
        f'<rect width="{w}" height="{h}" rx="14" fill="#060d19" stroke="{C["line"]}"/>',
        f'<rect width="{w}" height="3" rx="1.5" fill="{color}"/>',
        f'<circle cx="26" cy="34" r="5" fill="{color}"/>',
        f'<text x="40" y="38.5" font-family="{MONO}" font-size="13" font-weight="600" fill="{C["text"]}">{esc(clip(repo["name"], 34))}</text>',
    ]
    if live:
        body.append(
            f'<g><rect x="{w - 74}" y="24" width="52" height="20" rx="10" fill="{C["green"]}" fill-opacity=".12" stroke="{C["green"]}" stroke-opacity=".45"/>'
            f'<circle cx="{w - 60}" cy="34" r="3" fill="{C["green"]}"><animate attributeName="opacity" values="1;.2;1" dur="2s" repeatCount="indefinite"/></circle>'
            f'<text x="{w - 51}" y="38" font-family="{MONO}" font-size="9" fill="{C["green"]}">LIVE</text></g>'
        )
    for i, line in enumerate(desc_lines):
        body.append(
            f'<text x="26" y="{66 + i * 20}" font-family="{FONT}" font-size="12.5" fill="{C["dim"]}">{esc(line)}</text>'
        )
    meta_y = h - 24
    body.append(
        f'<text x="26" y="{meta_y}" font-family="{MONO}" font-size="10" fill="{color}">● {esc(repo["lang"])}</text>'
        f'<text x="132" y="{meta_y}" font-family="{MONO}" font-size="10" fill="{C["dim"]}">★ {repo["stars"]}</text>'
        f'<text x="188" y="{meta_y}" font-family="{MONO}" font-size="10" fill="{C["dim"]}">⑂ {repo["forks"]}</text>'
        f'<text x="{w - 26}" y="{meta_y}" text-anchor="end" font-family="{MONO}" font-size="10" fill="{C["dim"]}">{esc(ago(repo["pushed"]))}</text>'
    )
    body.append(
        f'<rect x="18" y="{meta_y - 16}" width="{w - 36}" height="1" fill="{C["line"]}" opacity=".8"/>'
    )
    return svg(w, h, "".join(body))


# ----------------------------------------------------------------------------
# SVG: footer
# ----------------------------------------------------------------------------


def build_footer(data: dict) -> str:
    w, h = 1280, 150
    defs = f"""
<linearGradient id="fg" x1="0" y1="0" x2="1" y2="0">
  <stop offset="0" stop-color="{C['cyan']}"/><stop offset=".5" stop-color="{C['violet']}"/><stop offset="1" stop-color="{C['amber']}"/>
</linearGradient>
"""
    wave = "M0 70 C 120 30, 240 110, 360 70 S 600 30, 720 70 S 960 110, 1080 70 S 1260 40, 1280 62"
    body = f"""
<rect width="{w}" height="{h}" rx="16" fill="#050b15"/>
<g opacity=".85">
  <path d="{wave}" stroke="url(#fg)" stroke-width="2" fill="none">
    <animateTransform attributeName="transform" type="translate" values="0,0;-60,0;0,0" dur="14s" repeatCount="indefinite"/>
  </path>
  <path d="{wave}" stroke="url(#fg)" stroke-width="2" fill="none" opacity=".35" transform="translate(0,14)">
    <animateTransform attributeName="transform" type="translate" values="0,14;60,14;0,14" dur="18s" repeatCount="indefinite"/>
  </path>
</g>
<text x="{w / 2}" y="46" text-anchor="middle" font-family="{FONT}" font-size="15" font-weight="700" fill="{C['text']}">bikin sampai jalan dulu, lalu perbaiki sampai layak dipakai</text>
<text x="{w / 2}" y="110" text-anchor="middle" font-family="{MONO}" font-size="10.5" fill="{C['dim']}">{len(data['repos'])} repos · {data['live']} live demos · {data['total_contributions']} contributions · generated {esc(stamp_date())}</text>
"""
    return svg(w, h, body, defs)


# ----------------------------------------------------------------------------
# README injection
# ----------------------------------------------------------------------------


def stamp_date() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d")


def stamp_full() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")


def inject(readme: str, name: str, block: str) -> str:
    pattern = re.compile(
        rf"(<!-- AUTO:{name} -->)(.*?)(<!-- /AUTO:{name} -->)", re.DOTALL
    )
    if not pattern.search(readme):
        print(f"  ! marker AUTO:{name} tidak ditemukan", file=sys.stderr)
        return readme
    return pattern.sub(lambda m: f"{m.group(1)}\n{block}\n{m.group(3)}", readme)


def cards_block(data: dict) -> str:
    rows = []
    for i in range(0, len(data["repos"]), 2):
        pair = data["repos"][i : i + 2]
        cells = []
        for repo in pair:
            link = f"https://github.com/{LOGIN}/{repo['name']}"
            extra = f' · <a href="{esc(repo["live"])}">Live ↗</a>' if repo["live"] else ""
            cells.append(
                f'<td width="50%" align="center" valign="top">'
                f'<a href="{link}"><img src="assets/cards/{repo["name"]}.svg" alt="{esc(clip(repo["name"] + " — " + repo["desc"], 110))}" width="420" height="172" /></a>'
                f"<br><sub><a href=\"{link}\">Repo ↗</a>{extra}</sub></td>"
            )
        if len(cells) == 1:
            cells.append('<td width="50%"></td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return "<table>\n" + "\n".join(rows) + "\n</table>"


def live_block(data: dict) -> str:
    live = [r for r in data["repos"] if r["live"]]
    live.sort(key=lambda r: r["name"].lower())
    lines = ["| Project | Live endpoint | Stack |", "|---|---|---|"]
    for repo in live:
        lines.append(
            f"| [`{repo['name']}`](https://github.com/{LOGIN}/{repo['name']}) | <{repo['live']}> | {repo['lang']} |"
        )
    if not live:
        lines.append("| — | — | — |")
    return "\n".join(lines)


def stats_block(data: dict) -> str:
    langs = " · ".join(f"**{k}** {v / max(sum(data['languages'].values()), 1) * 100:.0f}%" for k, v in list(data["languages"].items())[:5])
    return (
        f"`{len(data['repos'])} repos` · `{data['live']} live` · `{data['stars']} stars` · "
        f"`{data['forks']} forks` · `{data['total_contributions']} contributions/12mo` · "
        f"`{data['streak']}d streak`\n\n{langs}"
    )


# ----------------------------------------------------------------------------
# Main
# ----------------------------------------------------------------------------


def main() -> int:
    if not TOKEN:
        print("! GITHUB_TOKEN kosong — memakai batas rate anonim (60/jam).")
    http = Http(TOKEN)
    print("→ mengambil data GitHub …")
    data = collect(http)
    print(
        f"  {len(data['repos'])} repo · {data['live']} live · "
        f"{data['total_contributions']} kontribusi · {len(data['languages'])} bahasa"
    )

    print("→ membangun SVG …")
    write(os.path.join(ASSETS, "hero.svg"), build_hero(data, stamp_full()))
    write(os.path.join(ASSETS, "terminal.svg"), build_terminal(data))
    write(os.path.join(ASSETS, "marquee.svg"), build_marquee())
    write(os.path.join(ASSETS, "dashboard.svg"), build_dashboard(data))
    write(os.path.join(ASSETS, "streak.svg"), build_streak(data))
    write(os.path.join(ASSETS, "activity.svg"), build_activity(data))
    write(os.path.join(ASSETS, "snake.svg"), build_snake(data))
    write(os.path.join(ASSETS, "footer.svg"), build_footer(data))

    for old in os.listdir(CARDS) if os.path.isdir(CARDS) else []:
        if old.endswith(".svg"):
            os.remove(os.path.join(CARDS, old))
    for repo in data["repos"]:
        write(os.path.join(CARDS, f"{repo['name']}.svg"), build_card(repo))
    print(f"  {len(data['repos'])} kartu repo")

    with open(README, encoding="utf-8") as handle:
        readme = handle.read()
    for name, block in (
        ("CARDS", cards_block(data)),
        ("LIVE", live_block(data)),
        ("STATS", stats_block(data)),
        ("STAMP", f"`last sync {stamp_full()}`"),
    ):
        readme = inject(readme, name, block)
    with open(README, "w", encoding="utf-8") as handle:
        handle.write(readme)
    print("→ README disuntik")
    return 0


if __name__ == "__main__":
    sys.exit(main())
