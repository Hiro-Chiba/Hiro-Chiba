#!/usr/bin/env python3
"""Fetch a profile contribution calendar and render its animated SVG."""

from __future__ import annotations

import argparse
import datetime as dt
import html
import json
import time
import urllib.error
import urllib.request
from pathlib import Path

from profile_art_config import DEFAULT_CONFIG, load_config, project_path

PALETTE = ("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353")
MONTHS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)
CELL = 13
GAP = 3
LEFT = 34
TOP = 24


def fetch_calendar(user: str, attempts: int) -> list[dict]:
    url = f"https://github-contributions-api.jogruber.de/v4/{user}?y=last"
    request = urllib.request.Request(
        url, headers={"User-Agent": "profile-art-generator/1.0"}
    )
    payload = None
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=25) as response:
                payload = json.load(response)
            break
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
            if attempt == attempts - 1:
                raise RuntimeError(
                    f"Contribution data request failed after {attempts} attempts"
                ) from error
            time.sleep(2**attempt)
    if payload is None:
        raise RuntimeError("Contribution data request returned no payload")
    contributions = payload.get("contributions", [])
    if not contributions:
        raise RuntimeError(f"No contribution data returned for {user}")
    return sorted(contributions, key=lambda item: item["date"])


def calendar_cells(contributions: list[dict]):
    first_date = dt.date.fromisoformat(contributions[0]["date"])
    first_sunday = first_date - dt.timedelta(days=(first_date.weekday() + 1) % 7)
    cells = []
    month_labels = []
    seen_months = set()
    for item in contributions:
        date = dt.date.fromisoformat(item["date"])
        day_offset = (date - first_sunday).days
        week = day_offset // 7
        weekday = (date.weekday() + 1) % 7
        level = max(0, min(int(item.get("level", 0)), len(PALETTE) - 1))
        count = int(item.get("count", 0))
        cells.append((week, weekday, date.isoformat(), count, level))
        month_key = (date.year, date.month)
        if month_key not in seen_months:
            seen_months.add(month_key)
            month_labels.append((week, MONTHS[date.month - 1]))
    return cells, month_labels, max(cell[0] for cell in cells) + 1


def render(contributions: list[dict], static: bool = False) -> str:
    cells, month_labels, weeks = calendar_cells(contributions)
    step = CELL + GAP
    width = LEFT + weeks * step + 6
    height = TOP + 7 * step + 22
    total = sum(int(item.get("count", 0)) for item in contributions)
    max_order = max((weeks - 1) + 6 * 0.6, 1)

    if static:
        animation_css = ".cell { opacity: 1; }"
    else:
        animation_css = """
        .cell { transform-box: fill-box; transform-origin: center; opacity: 0;
                animation: reveal .55s ease-out both; }
        .active { animation: reveal .55s ease-out both, brighten .70s ease-out both; }
        @keyframes reveal {
          0% { opacity: 0; transform: scale(.2); }
          60% { opacity: 1; transform: scale(1.1); }
          100% { opacity: 1; transform: scale(1); }
        }
        @keyframes brighten {
          0%, 45% { filter: brightness(2.4); }
          100% { filter: brightness(1); }
        }
        @media (prefers-reduced-motion: reduce) {
          .cell { opacity: 1 !important; animation: none !important; }
        }
        """

    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="-apple-system,Segoe UI,Helvetica,Arial,sans-serif" '
            'role="img" aria-labelledby="title desc">'
        ),
        '<title id="title">GitHub contribution graph</title>',
        f'<desc id="desc">{total:,} contributions during the last year</desc>',
        (
            "<style>"
            "text.label{fill:#7d8590;font-size:13px;font-weight:600}"
            "text.total{fill:#e6edf3;font-size:15px;font-weight:700}"
            f"{animation_css}</style>"
        ),
        f'<rect width="{width}" height="{height}" fill="none"/>',
    ]

    for week, label in month_labels:
        parts.append(
            f'<text class="label" x="{LEFT + week * step}" y="{TOP - 8}">{label}</text>'
        )
    for label, row in (("Mon", 1), ("Wed", 3), ("Fri", 5)):
        parts.append(
            f'<text class="label" x="2" y="{TOP + row * step + CELL - 2}">{label}</text>'
        )

    for week, weekday, date, count, level in cells:
        x = LEFT + week * step
        y = TOP + weekday * step
        delay = ((week + weekday * 0.6) / max_order) * 3.6
        active = " active" if count else ""
        parts.append(
            f'<rect class="cell{active}" x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2.5" '
            f'fill="{PALETTE[level]}" style="animation-delay:{delay:.3f}s">'
            f"<title>{html.escape(date)}: {count} contributions</title></rect>"
        )

    parts.append(
        f'<text class="total" x="{LEFT}" y="{height - 6}">{total:,} contributions in the last year</text>'
    )
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--user")
    parser.add_argument("--out", type=Path)
    parser.add_argument("--static", action="store_true")
    options = parser.parse_args()

    config = load_config(
        options.config,
        {
            "github_user",
            "contributions_output",
            "contribution_fetch_attempts",
        },
    )
    user = options.user or config["github_user"]
    output = options.out or project_path(config["contributions_output"])
    contributions = fetch_calendar(user, int(config["contribution_fetch_attempts"]))
    svg = render(contributions, static=options.static)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    print(f"wrote {output} ({len(contributions)} days)")


if __name__ == "__main__":
    main()
