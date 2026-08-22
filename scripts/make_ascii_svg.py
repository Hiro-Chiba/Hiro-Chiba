#!/usr/bin/env python3
"""Wrap an existing text-based ASCII portrait in an animated terminal."""

import argparse
import html
import xml.etree.ElementTree as ET
from pathlib import Path

from profile_art_config import DEFAULT_CONFIG, RevealLoop, load_config, project_path

CANVAS_W = 840
CANVAS_H = 875
TITLEBAR_H = 30
PAD = 20
ART_TOP = TITLEBAR_H + PAD * 0.35
ART_W = CANVAS_W - PAD * 2

BG = "#0d1117"
BG2 = "#111722"
FRAME = "#30363d"
TITLE_TEXT = "#7d8590"
INK = "#c9d1d9"


def read_rows(source: Path):
    root = ET.parse(source).getroot()
    view_box = root.get("viewBox")
    source_width = (
        float(view_box.split()[2]) if view_box else float(root.attrib["width"])
    )
    namespace = {"svg": "http://www.w3.org/2000/svg"}
    portrait_group = root.find(".//svg:g", namespace)
    source_font_size = float(portrait_group.attrib["font-size"])
    rows = []
    for node in root.findall(".//svg:text", namespace):
        rows.append(
            (float(node.get("x", "0")), float(node.get("y", "0")), node.text or "")
        )
    return source_width, source_font_size, sorted(rows, key=lambda row: row[1])


def render(
    rows,
    source_width: float,
    source_font_size: float,
    terminal_user: str,
    display_name: str,
    loop: RevealLoop,
    line_duration: float,
    static: bool,
):
    scale = ART_W / source_width
    font_size = source_font_size * scale
    row_height = source_font_size * scale
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{CANVAS_W}" height="{CANVAS_H}" '
            f'viewBox="0 0 {CANVAS_W} {CANVAS_H}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">'
        ),
        (
            '<defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">'
            f'<stop offset="0" stop-color="{BG2}"/><stop offset="1" stop-color="{BG}"/>'
            "</linearGradient></defs>"
        ),
        (
            ""
            if static
            else """<style>
            .portrait-static { display: none; }
            @media (prefers-reduced-motion: reduce) {
              .portrait-motion { display: none; }
              .portrait-static { display: inline; }
            }
            </style>"""
        ),
        f'<rect width="{CANVAS_W}" height="{CANVAS_H}" rx="12" fill="url(#bg)"/>',
        (
            f'<rect x="0.5" y="0.5" width="{CANVAS_W - 1}" height="{CANVAS_H - 1}" rx="12" '
            f'fill="none" stroke="{FRAME}" stroke-width="1"/>'
        ),
        f'<line x1="0" y1="{TITLEBAR_H}" x2="{CANVAS_W}" y2="{TITLEBAR_H}" stroke="{FRAME}"/>',
    ]

    for index, color in enumerate(["#ff5f56", "#ffbd2e", "#27c93f"]):
        parts.append(
            f'<circle cx="{PAD + index * 16}" cy="{TITLEBAR_H / 2}" r="5" fill="{color}"/>'
        )

    parts.append(
        f'<text x="{CANVAS_W / 2}" y="{TITLEBAR_H / 2 + 4}" fill="{TITLE_TEXT}" '
        f'font-size="12" text-anchor="middle">{html.escape(terminal_user)}@github: ~$ ./portrait.sh</text>'
    )

    static_rows = []
    motion_rows = []
    for index, (source_x, source_y, line) in enumerate(rows):
        x = PAD + source_x * scale
        y = ART_TOP + source_y * scale
        row_y = y - row_height * 0.82
        delay = index * line_duration
        safe = html.escape(line)
        text = (
            f'<text xml:space="preserve" x="{x:.1f}" y="{y:.1f}" fill="{INK}" '
            f'font-size="{font_size:.1f}">{safe}</text>'
        )
        if static:
            parts.append(text)
            continue
        static_rows.append(text)
        reveal_end, fade_start, fade_end = loop.opacity_key_times(delay, line_duration)
        parts.append(
            f'<clipPath id="r{index}"><rect x="{PAD}" y="{row_y:.1f}" height="{row_height:.1f}" width="0">'
            f'<animate attributeName="width" values="0;{ART_W};{ART_W}" '
            f'keyTimes="0;{reveal_end:.5f};1" begin="{delay:.3f}s" '
            f'dur="{loop.duration:.2f}s" repeatCount="indefinite"/></rect></clipPath>'
        )
        opacity = (
            f'<animate attributeName="opacity" values="0;1;1;0;0" '
            f'keyTimes="0;{reveal_end:.5f};{fade_start:.5f};{fade_end:.5f};1" '
            f'begin="{delay:.3f}s" dur="{loop.duration:.2f}s" repeatCount="indefinite"/>'
        )
        cursor = (
            f'<rect y="{row_y + 1:.1f}" width="6" height="{row_height - 2:.1f}" fill="{INK}" opacity="0">'
            f'<animate attributeName="x" values="{PAD};{PAD + ART_W};{PAD + ART_W}" '
            f'keyTimes="0;{reveal_end:.5f};1" begin="{delay:.3f}s" '
            f'dur="{loop.duration:.2f}s" repeatCount="indefinite"/>'
            f'<animate attributeName="opacity" values=".85;.85;0;0" '
            f'keyTimes="0;{reveal_end:.5f};{min(reveal_end + 0.0001, 0.9999):.5f};1" '
            f'begin="{delay:.3f}s" dur="{loop.duration:.2f}s" repeatCount="indefinite"/></rect>'
        )
        motion_rows.append(
            f'<g class="portrait-motion" opacity="0">{opacity}'
            f'<g clip-path="url(#r{index})">{text}</g>{cursor}</g>'
        )

    if not static:
        parts.append(f'<g class="portrait-static">{"".join(static_rows)}</g>')
        parts.extend(motion_rows)

    status_line_y = CANVAS_H - 43
    status_y = CANVAS_H - 17
    parts.append(
        f'<line x1="0" y1="{status_line_y}" x2="{CANVAS_W}" y2="{status_line_y}" stroke="{FRAME}"/>'
    )
    parts.append(
        f'<text x="{PAD}" y="{status_y}" fill="{TITLE_TEXT}" font-size="13">'
        f"{html.escape(terminal_user)}@github:~$ whoami "
        f'<tspan fill="{INK}">{html.escape(display_name)}</tspan></text>'
    )
    cursor_x = PAD + len(f"{terminal_user}@github:~$ whoami {display_name}") * 7.5 + 8
    parts.append(
        f'<rect x="{cursor_x:.1f}" y="{status_y - 12}" width="8" height="14" fill="{INK}">'
        '<animate attributeName="opacity" values="1;1;0;0" keyTimes="0;0.5;0.51;1" '
        'dur="1s" repeatCount="indefinite"/></rect>'
    )
    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--source", type=Path)
    parser.add_argument("--out", type=Path)
    parser.add_argument("--static", action="store_true")
    options = parser.parse_args()

    config = load_config(
        options.config,
        {
            "terminal_user",
            "display_name",
            "portrait_source",
            "portrait_output",
            "portrait_animation",
        },
    )
    source = options.source or project_path(config["portrait_source"])
    output = options.out or project_path(config["portrait_output"])
    source_width, source_font_size, rows = read_rows(source)
    loop = RevealLoop.from_config(config["portrait_animation"])
    svg = render(
        rows,
        source_width,
        source_font_size,
        config["terminal_user"],
        config["display_name"],
        loop,
        float(config["portrait_animation"]["line_seconds"]),
        options.static,
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(svg, encoding="utf-8")
    print(f"wrote {output} ({len(svg)} bytes)")


if __name__ == "__main__":
    main()
