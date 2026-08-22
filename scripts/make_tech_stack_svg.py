#!/usr/bin/env python3
"""Build the animated, branded technology stack map."""

from __future__ import annotations

import re
import time
import urllib.request
from dataclasses import dataclass
from xml.sax.saxutils import escape

from profile_art_config import load_config, project_path

SIMPLE_ICONS_VERSION = "16.28.0"
LOOP_DURATION = 12.0
LINE_SPEED = 88.0
FADE_START = 0.88
ICON_FETCH_ATTEMPTS = 3
ICON_URL = (
    "https://cdn.jsdelivr.net/npm/simple-icons@"
    f"{SIMPLE_ICONS_VERSION}/icons/{{slug}}.svg"
)


@dataclass(frozen=True)
class Tech:
    name: str
    slug: str
    color: str
    text_color: str
    x: int
    y: int
    width: int


@dataclass(frozen=True)
class Branch:
    slug: str
    points: tuple[tuple[int, int], ...]
    start_seconds: float


TECHS = (
    Tech("TypeScript", "typescript", "#3178C6", "#FFFFFF", 121, 103, 130),
    Tech("JavaScript", "javascript", "#F7DF1E", "#111111", 121, 145, 130),
    Tech("PHP", "php", "#777BB4", "#FFFFFF", 121, 187, 86),
    Tech("Next.js", "nextdotjs", "#000000", "#FFFFFF", 315, 104, 112),
    Tech("React", "react", "#61DAFB", "#111111", 430, 104, 90),
    Tech("TailwindCSS", "tailwindcss", "#38B2AC", "#FFFFFF", 555, 104, 120),
    Tech("Laravel", "laravel", "#FF2D20", "#FFFFFF", 740, 115, 120),
    Tech("PostgreSQL", "postgresql", "#336791", "#FFFFFF", 743, 238, 138),
    Tech("MySQL", "mysql", "#4479A1", "#FFFFFF", 740, 280, 120),
    Tech("Git", "git", "#F05032", "#FFFFFF", 310, 372, 76),
    Tech("GitHub Actions", "githubactions", "#2088FF", "#FFFFFF", 435, 372, 144),
    Tech("Docker", "docker", "#2496ED", "#FFFFFF", 575, 372, 100),
    Tech("Python", "python", "#3776AB", "#FFFFFF", 116, 330, 100),
    Tech("Rust", "rust", "#000000", "#FFFFFF", 116, 370, 100),
)


BRANCHES = (
    Branch("typescript", ((360, 210), (244, 210), (244, 103), (186, 103)), 0.35),
    Branch("javascript", ((360, 222), (276, 222), (276, 145), (186, 145)), 0.75),
    Branch("php", ((360, 234), (260, 234), (260, 187), (164, 187)), 1.15),
    Branch("nextdotjs", ((392, 190), (392, 150), (315, 150), (315, 120)), 0.25),
    Branch("react", ((430, 190), (430, 120)), 0.95),
    Branch("tailwindcss", ((468, 190), (468, 150), (555, 150), (555, 120)), 0.15),
    Branch(
        "laravel", ((500, 210), (648, 210), (648, 135), (680, 135), (680, 115)), 0.45
    ),
    Branch("postgresql", ((500, 234), (640, 234), (640, 238), (674, 238)), 0.65),
    Branch("mysql", ((500, 246), (624, 246), (624, 280), (680, 280)), 1.05),
    Branch("git", ((392, 268), (392, 306), (310, 306), (310, 356)), 1.25),
    Branch("githubactions", ((430, 268), (430, 306), (435, 306), (435, 356)), 0.85),
    Branch("docker", ((468, 268), (468, 306), (575, 306), (575, 356)), 1.45),
    Branch("python", ((360, 246), (244, 246), (244, 330), (166, 330)), 0.55),
    Branch("rust", ((360, 258), (228, 258), (228, 370), (166, 370)), 1.35),
)


CATEGORIES = (
    ("[ CORE LANGUAGES ]", 56, 66, "start", ("typescript", "javascript", "php")),
    ("[ FRONTEND ]", 430, 65, "middle", ("nextdotjs", "react", "tailwindcss")),
    ("[ BACKEND ]", 680, 76, "start", ("laravel",)),
    ("[ DATABASE ]", 674, 198, "start", ("postgresql", "mysql")),
    ("[ DEVOPS ]", 430, 330, "middle", ("git", "githubactions", "docker")),
    ("[ LEARNING / HOBBY ]", 56, 298, "start", ("python", "rust")),
)


def fetch_icon_path(slug: str) -> str:
    request = urllib.request.Request(
        ICON_URL.format(slug=slug),
        headers={"User-Agent": "Hiro-Chiba profile SVG generator"},
    )
    for attempt in range(ICON_FETCH_ATTEMPTS):
        try:
            with urllib.request.urlopen(request, timeout=20) as response:
                svg = response.read().decode("utf-8")
            break
        except OSError:
            if attempt == ICON_FETCH_ATTEMPTS - 1:
                raise
            time.sleep(0.5 * 2**attempt)
    match = re.search(r'<path d="([^"]+)"', svg)
    if not match:
        raise ValueError(f"Simple Icons path not found for {slug}")
    return match.group(1)


def icon_symbols(paths: dict[str, str]) -> str:
    return "\n".join(
        f'    <symbol id="icon-{tech.slug}" viewBox="0 0 24 24">'
        f'<path d="{paths[tech.slug]}"/></symbol>'
        for tech in TECHS
    )


def branch_path(branch: Branch) -> str:
    first_x, first_y = branch.points[0]
    commands = [f"M{first_x} {first_y}"]
    previous_x, previous_y = first_x, first_y
    for x, y in branch.points[1:]:
        if x == previous_x:
            commands.append(f"V{y}")
        elif y == previous_y:
            commands.append(f"H{x}")
        else:
            raise ValueError(f"Branch {branch.slug} contains a diagonal segment")
        previous_x, previous_y = x, y
    return "".join(commands)


def branch_reveal(branch: Branch) -> float:
    length = sum(
        abs(x2 - x1) + abs(y2 - y1)
        for (x1, y1), (x2, y2) in zip(branch.points, branch.points[1:])
    )
    reveal = (branch.start_seconds + length / LINE_SPEED) / LOOP_DURATION
    if reveal >= FADE_START:
        raise ValueError(f"Branch {branch.slug} reaches its node after the fade starts")
    return reveal


def tech_node(tech: Tech, reveal: float) -> str:
    half = tech.width / 2
    left = -half
    reveal_end = reveal + 0.002
    pop_peak = reveal + 0.025
    settle = reveal + 0.06
    icon_x = left + 10
    text_x = left + 34
    border = "#30363D" if tech.color == "#000000" else tech.color
    return f"""
  <g transform="translate({tech.x} {tech.y})" opacity="1">
    <animate attributeName="opacity" values="0;0;1;1;0"
      keyTimes="0;{reveal:.5f};{reveal_end:.5f};{FADE_START};1" dur="{LOOP_DURATION:g}s" repeatCount="indefinite"/>
    <g>
      <animateTransform attributeName="transform" type="scale"
        values=".82;.82;1.08;1;1;.92"
        keyTimes="0;{reveal:.5f};{pop_peak:.5f};{settle:.5f};{FADE_START};1"
        dur="{LOOP_DURATION:g}s" repeatCount="indefinite"/>
      <rect x="{left:g}" y="-16" width="{tech.width}" height="32" rx="6"
        fill="{tech.color}" stroke="{border}" stroke-width="1.2"/>
      <use href="#icon-{tech.slug}" x="{icon_x:g}" y="-8" width="16" height="16" fill="{tech.text_color}"/>
      <text x="{text_x:g}" y="4" class="node-text" fill="{tech.text_color}">{escape(tech.name)}</text>
    </g>
  </g>"""


def main() -> None:
    config = load_config(required={"tech_stack_output", "terminal_user"})
    paths = {tech.slug: fetch_icon_path(tech.slug) for tech in TECHS}
    reveal_by_slug = {branch.slug: branch_reveal(branch) for branch in BRANCHES}
    symbols = icon_symbols(paths)
    nodes = "".join(tech_node(tech, reveal_by_slug[tech.slug]) for tech in TECHS)
    branches = "\n".join(
        f"""    <path class="wire" d="{branch_path(branch)}" pathLength="1" stroke-dasharray="1" stroke-dashoffset="0">
      <animate attributeName="stroke-dashoffset" values="1;1;0;0"
        keyTimes="0;{branch.start_seconds / LOOP_DURATION:.5f};{reveal_by_slug[branch.slug]:.5f};1"
        dur="{LOOP_DURATION:g}s" repeatCount="indefinite"/>
      <animate attributeName="opacity" values="1;1;0" keyTimes="0;{FADE_START};1"
        dur="{LOOP_DURATION:g}s" repeatCount="indefinite"/>
    </path>"""
        for branch in BRANCHES
    )
    categories = "\n".join(
        f"""    <text x="{x}" y="{y}" text-anchor="{anchor}" opacity="1">{escape(label)}
      <animate attributeName="opacity" values="0;0;1;1;0"
        keyTimes="0;{reveal:.5f};{reveal + 0.02:.5f};{FADE_START};1"
        dur="{LOOP_DURATION:g}s" repeatCount="indefinite"/>
    </text>"""
        for label, x, y, anchor, slugs in CATEGORIES
        for reveal in (min(reveal_by_slug[slug] for slug in slugs),)
    )

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="860" height="460" viewBox="0 0 860 460"
  role="img" aria-labelledby="title description"
  font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">
  <title id="title">Hiro's animated branded technology network</title>
  <desc id="description">Circuit branches grow from TECH to fourteen technology badges.</desc>
  <defs>
    <linearGradient id="panel-bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#111722"/>
      <stop offset="1" stop-color="#0D1117"/>
    </linearGradient>
    <filter id="soft-glow" x="-40%" y="-40%" width="180%" height="180%">
      <feGaussianBlur stdDeviation="5"/>
    </filter>
{symbols}
    <style>
      .wire {{ fill:none; stroke:#7D8590; stroke-width:1.35; stroke-linecap:round; stroke-linejoin:round; }}
      .category {{ fill:#7D8590; font-size:11px; font-weight:700; letter-spacing:.8px; }}
      .node-text {{ font-size:12px; font-weight:650; dominant-baseline:auto; }}
    </style>
  </defs>

  <rect width="860" height="460" rx="12" fill="url(#panel-bg)"/>
  <rect x=".5" y=".5" width="859" height="459" rx="12" fill="none" stroke="#30363D"/>
  <line x1="0" y1="32" x2="860" y2="32" stroke="#30363D"/>
  <circle cx="20" cy="16" r="5" fill="#FF5F56"/>
  <circle cx="36" cy="16" r="5" fill="#FFBD2E"/>
  <circle cx="52" cy="16" r="5" fill="#27C93F"/>
  <text x="430" y="20" fill="#7D8590" font-size="12" text-anchor="middle">{escape(str(config["terminal_user"]))}@github: ~$ ./stack-map.sh</text>

  <g>
{branches}
  </g>

  <g class="category">
{categories}
  </g>

{nodes}

  <rect x="355" y="185" width="150" height="88" rx="13" fill="none" stroke="#C9D1D9" stroke-width="8" opacity=".14" filter="url(#soft-glow)"/>
  <g>
    <rect x="360" y="190" width="140" height="78" rx="10" fill="#0D1117" stroke="#C9D1D9" stroke-width="1.5"/>
    <text x="430" y="226" fill="#C9D1D9" font-size="25" font-weight="700" text-anchor="middle" letter-spacing="4">TECH</text>
    <line x1="391" y1="237" x2="469" y2="237" stroke="#30363D"/>
    <text x="430" y="253" fill="#7D8590" font-size="10" text-anchor="middle" letter-spacing="3">STACK</text>
  </g>
</svg>
"""
    output = project_path(str(config["tech_stack_output"]))
    output.write_text(svg, encoding="utf-8")
    print(f"wrote {output} ({output.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
