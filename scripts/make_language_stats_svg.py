#!/usr/bin/env python3
"""Build the animated terminal panel that reports language usage."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from xml.sax.saxutils import escape

from profile_art_config import DEFAULT_CONFIG, load_config, project_path

GRAPHQL_URL = "https://api.github.com/graphql"
FETCH_ATTEMPTS = 3
LOOP_DURATION = 16.0
FADE_START = 0.9
WIDTH = 860
PANEL_TOP = 32
GLYPH = 7.5  # advance width of the 12.5px monospace face
FALLBACK_COLOR = "#7D8590"
REPOSITORY_PAGE = 100

# Cleared by --static so a still frame can be inspected.
ANIMATE = True

QUERY = """
query($login: String!, $page: Int!) {
  user(login: $login) {
    repositories(first: $page, ownerAffiliations: OWNER, isFork: false) {
      totalCount
      nodes {
        isPrivate
        languages(first: 12, orderBy: {field: SIZE, direction: DESC}) {
          edges { size node { name color } }
        }
      }
    }
  }
}
"""


@dataclass(frozen=True)
class Language:
    name: str
    color: str
    size: int
    share: float


@dataclass(frozen=True)
class Report:
    languages: list[Language]
    public: int
    private: int
    total: int
    stamp: str
    user: str


def human_size(value: int) -> str:
    if value >= 1_000_000:
        return f"{value / 1_000_000:.2f} MB"
    if value >= 1_000:
        return f"{value / 1_000:.1f} kB"
    return f"{value} B"


def github_token() -> str:
    """A token with repo scope, so private repositories are counted too."""
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        return token
    try:
        result = subprocess.run(
            ["gh", "auth", "token"], capture_output=True, text=True, check=True
        )
    except (OSError, subprocess.CalledProcessError) as error:
        raise RuntimeError(
            "A GitHub token is required. Set GITHUB_TOKEN or run 'gh auth login'."
        ) from error
    return result.stdout.strip()


def fetch_languages(user: str, token: str) -> tuple[dict[str, int], dict[str, str], int, int]:
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps(
            {"query": QUERY, "variables": {"login": user, "page": REPOSITORY_PAGE}}
        ).encode("utf-8"),
        headers={
            "Authorization": f"bearer {token}",
            "Content-Type": "application/json",
            "User-Agent": "Hiro-Chiba profile SVG generator",
        },
    )
    payload = None
    for attempt in range(FETCH_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.load(response)
            break
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
            if attempt == FETCH_ATTEMPTS - 1:
                raise RuntimeError(
                    f"Language data request failed after {FETCH_ATTEMPTS} attempts"
                ) from error
            time.sleep(2**attempt)
    if payload is None:
        raise RuntimeError("Language data request returned no payload")
    if "errors" in payload:
        raise RuntimeError(f"Language data request returned errors: {payload['errors']}")

    repositories = payload["data"]["user"]["repositories"]
    nodes = repositories["nodes"]
    if len(nodes) < int(repositories["totalCount"]):
        raise RuntimeError(
            f"{repositories['totalCount']} repositories exceed the {REPOSITORY_PAGE} "
            "fetched in one page; the query needs pagination before it stays accurate"
        )
    sizes: dict[str, int] = {}
    colors: dict[str, str] = {}
    private = 0
    for node in nodes:
        private += bool(node["isPrivate"])
        for edge in node["languages"]["edges"]:
            name = edge["node"]["name"]
            sizes[name] = sizes.get(name, 0) + int(edge["size"])
            colors[name] = edge["node"]["color"] or FALLBACK_COLOR
    return sizes, colors, len(nodes) - private, private


def rank_languages(
    sizes: dict[str, int], colors: dict[str, str], excluded: set[str], top: int
) -> tuple[list[Language], int]:
    kept = {name: size for name, size in sizes.items() if name not in excluded}
    total = sum(kept.values())
    if not total:
        raise RuntimeError("No language data left after applying the exclusion list")
    ordered = sorted(kept.items(), key=lambda item: item[1], reverse=True)[:top]
    return [
        Language(name, colors[name], size, size / total) for name, size in ordered
    ], total


def loop_animation(reveal: float, hold: float = 0.02) -> str:
    """Fade a group in at `reveal` and out with the rest of the panel."""
    if not ANIMATE:
        return ""
    return (
        f'<animate attributeName="opacity" values="0;0;1;1;0" '
        f'keyTimes="0;{reveal:.5f};{min(reveal + hold, FADE_START):.5f};{FADE_START};1" '
        f'dur="{LOOP_DURATION:g}s" repeatCount="indefinite"/>'
    )


def prompt_line(y: int, command: str, reveal: float = 0.02) -> str:
    """The typed command, followed by a cursor that keeps blinking."""
    cursor_x = 40 + (len(command) + 3) * GLYPH
    blink = (
        '<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;.5;.5;1" '
        'dur="1.06s" repeatCount="indefinite"/>'
        if ANIMATE
        else ""
    )
    return (
        f'  <g opacity="1"><text class="prompt" x="40" y="{y}">'
        f'<tspan class="accent">$</tspan> {escape(command)}</text>'
        f'<rect x="{cursor_x:.1f}" y="{y - 11}" width="8" height="14" fill="#39D353" '
        f'opacity="1">{blink}</rect>'
        f"{loop_animation(reveal)}</g>"
    )


def panel_chrome(height: int, command: str, user: str) -> str:
    return f"""  <rect width="{WIDTH}" height="{height}" rx="12" fill="url(#panel-bg)"/>
  <rect x=".5" y=".5" width="{WIDTH - 1}" height="{height - 1}" rx="12" fill="none" stroke="#30363D"/>
  <line x1="0" y1="{PANEL_TOP}" x2="{WIDTH}" y2="{PANEL_TOP}" stroke="#30363D"/>
  <circle cx="20" cy="16" r="5" fill="#FF5F56"/>
  <circle cx="36" cy="16" r="5" fill="#FFBD2E"/>
  <circle cx="52" cy="16" r="5" fill="#27C93F"/>
  <text x="{WIDTH / 2:g}" y="20" fill="#7D8590" font-size="12" text-anchor="middle">{escape(user)}@github: ~$ {escape(command)}</text>"""


def summary(report: Report) -> str:
    repositories = report.public + report.private
    return (
        f"{repositories} repos  ({report.public} public · {report.private} private)"
        f"   ·   {human_size(report.total)} of code   ·   "
        f"refreshed {report.stamp} UTC"
    )


CELLS = 100  # one cell per percentage point
CELL_W = 3.6
CELL_GAP = 0.9
BAR_X = 196
SIZE_X = 736
ROW_STEP = 32


def render(report: Report) -> str:
    languages = report.languages
    prompt_y = PANEL_TOP + 30
    header_y = prompt_y + 30
    rows_top = header_y + 26
    rule_y = rows_top + len(languages) * ROW_STEP + 10
    footer_y = rule_y + 26
    height = footer_y + 22

    parts = [
        panel_chrome(height, "./lang-stats.sh --by bytes", report.user),
        prompt_line(prompt_y, "tokei --sort bytes --languages"),
        f'  <g opacity="1">'
        f'<text class="column" x="40" y="{header_y}">LANGUAGE</text>'
        f'<text class="column" x="{BAR_X}" y="{header_y}">SHARE</text>'
        f'<text class="column" x="{SIZE_X}" y="{header_y}" text-anchor="end">SIZE</text>'
        f'<text class="column" x="{WIDTH - 40}" y="{header_y}" text-anchor="end">%</text>'
        f'<line class="rule" x1="40" y1="{header_y + 10}" x2="{WIDTH - 40}" y2="{header_y + 10}"/>'
        f"{loop_animation(0.05)}</g>",
    ]

    row_span = 0.72 / max(len(languages), 1)
    for index, language in enumerate(languages):
        y = rows_top + index * ROW_STEP
        start = 0.1 + index * row_span * 0.6
        baseline = y + 11
        parts.append(
            f'  <g opacity="1">'
            f'<circle cx="45" cy="{baseline - 4}" r="4" fill="{language.color}"/>'
            f'<text class="name" x="58" y="{baseline}">{escape(language.name)}</text>'
            f"{loop_animation(start)}</g>"
        )
        exact = language.share * CELLS
        full = int(exact)
        remainder = exact - full
        for cell in range(CELLS):
            x = f"{BAR_X + cell * (CELL_W + CELL_GAP):.2f}"
            parts.append(
                f'  <rect x="{x}" y="{y}" width="{CELL_W}" height="14" rx="1.2" '
                f'fill="#1C222B" opacity="1">{loop_animation(start, 0.01)}</rect>'
            )
            if cell > full or (cell == full and remainder < 0.02):
                continue
            # the last cell keeps the fraction, so sub-percent shares stay visible
            width = CELL_W if cell < full else max(CELL_W * remainder, 1.5)
            delay = start + (cell / CELLS) * row_span * 0.55
            parts.append(
                f'  <rect x="{x}" y="{y}" width="{width:.2f}" height="14" rx="1.2" '
                f'fill="{language.color}" opacity="1">{loop_animation(delay, 0.008)}</rect>'
            )
        parts.append(
            f'  <g opacity="1">'
            f'<text class="key" x="{SIZE_X}" y="{baseline}" text-anchor="end">'
            f"{human_size(language.size)}</text>"
            f'<text class="value" x="{WIDTH - 40}" y="{baseline}" text-anchor="end">'
            f"{language.share * 100:.2f}%</text>"
            f"{loop_animation(start + row_span * 0.55)}</g>"
        )

    parts.append(
        f'  <g opacity="1">'
        f'<line class="rule" x1="40" y1="{rule_y}" x2="{WIDTH - 40}" y2="{rule_y}"/>'
        f'<text class="muted" x="40" y="{footer_y}">{escape(summary(report))}</text>'
        f"{loop_animation(0.68)}</g>"
    )

    body = "\n".join(parts)
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{WIDTH}" height="{height}" viewBox="0 0 {WIDTH} {height}"
  role="img" aria-labelledby="title description"
  font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">
  <title id="title">Hiro's animated language usage panel</title>
  <desc id="description">A terminal bar chart of language usage measured in bytes.</desc>
  <defs>
    <linearGradient id="panel-bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#111722"/>
      <stop offset="1" stop-color="#0D1117"/>
    </linearGradient>
    <style>
      .prompt {{ fill:#7D8590; font-size:12.5px; }}
      .accent {{ fill:#39D353; }}
      .name {{ fill:#C9D1D9; font-size:13px; font-weight:650; }}
      .value {{ fill:#C9D1D9; font-size:12.5px; }}
      .key {{ fill:#7D8590; font-size:12.5px; }}
      .muted {{ fill:#7D8590; font-size:11.5px; }}
      .column {{ fill:#59636E; font-size:10.5px; font-weight:700; letter-spacing:1.1px; }}
      .rule {{ stroke:#21262D; }}
    </style>
  </defs>
{body}
</svg>
"""


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--static", action="store_true")
    options = parser.parse_args()

    global ANIMATE
    ANIMATE = not options.static

    config = load_config(
        options.config,
        {"github_user", "terminal_user", "language_stats_output", "language_stats"},
    )
    settings = config["language_stats"]
    sizes, colors, public, private = fetch_languages(
        config["github_user"], github_token()
    )
    languages, total = rank_languages(
        sizes,
        colors,
        set(settings.get("excluded", [])),
        int(settings.get("top", 6)),
    )
    report = Report(
        languages=languages,
        public=public,
        private=private,
        total=total,
        stamp=time.strftime("%Y-%m-%d", time.gmtime()),
        user=str(config["terminal_user"]),
    )
    output = options.out or project_path(str(config["language_stats_output"]))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(render(report), encoding="utf-8")
    print(f"wrote {output} ({len(languages)} languages, {public + private} repos)")


if __name__ == "__main__":
    main()
