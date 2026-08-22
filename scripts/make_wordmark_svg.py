#!/usr/bin/env python3
"""Build a rocking 3D ASCII wordmark as a self-contained SVG."""

from __future__ import annotations

import argparse
import html
import math
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont
from profile_art_config import DEFAULT_CONFIG, load_config, project_path

CHARACTERS = " .,:;-+=*sS#%@"


@dataclass(frozen=True)
class Layout:
    columns: int
    cell_width: float = 8.7
    cell_height: float = 15.0
    row_margin: int = 5
    padding: int = 18
    title_height: int = 28


def text_mask(text: str, font_path: str, font_index: int) -> np.ndarray:
    font = ImageFont.truetype(font_path, 280, index=font_index)
    tracking = 30
    _, top, _, bottom = font.getbbox(text)
    glyph_height = bottom - top
    width = int(
        sum(font.getlength(char) for char in text) + tracking * (len(text) - 1) + 16
    )
    image = Image.new("L", (width, glyph_height + 16), 0)
    draw = ImageDraw.Draw(image)
    cursor = 8.0
    for char in text:
        draw.text((cursor, 8 - top), char, font=font, fill=255)
        cursor += font.getlength(char) + tracking

    mask = np.asarray(image) > 127
    used_rows = np.flatnonzero(mask.any(axis=1))
    used_columns = np.flatnonzero(mask.any(axis=0))
    return mask[
        used_rows[0] : used_rows[-1] + 1, used_columns[0] : used_columns[-1] + 1
    ]


def resolve_font(pattern: str) -> tuple[str, int]:
    font_match = shutil.which("fc-match")
    if not font_match:
        raise RuntimeError("fc-match is required unless --font is provided")
    result = subprocess.run(
        [font_match, "--format=%{file}\n%{index}", pattern],
        check=True,
        capture_output=True,
        text=True,
    )
    path, index = result.stdout.splitlines()
    if not Path(path).is_file():
        raise RuntimeError(f"Fontconfig returned an unavailable font: {path}")
    return path, int(index)


def surface_from(mask: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    height, width = mask.shape
    depth = max(5, round(height * 0.30))
    ys, xs = np.nonzero(mask)

    points = [
        np.column_stack((xs, ys, np.full(len(xs), -0.5))),
        np.column_stack((xs, ys, np.full(len(xs), depth))),
    ]
    normals = [
        np.tile((0.0, 0.0, -1.0), (len(xs), 1)),
        np.tile((0.0, 0.0, 1.0), (len(xs), 1)),
    ]

    padded = np.pad(mask, 1)
    open_right = ~padded[1:-1, 2:]
    open_left = ~padded[1:-1, :-2]
    open_down = ~padded[2:, 1:-1]
    open_up = ~padded[:-2, 1:-1]
    edge = mask & (open_right | open_left | open_down | open_up)
    edge_y, edge_x = np.nonzero(edge)
    normal_x = open_right[edge_y, edge_x].astype(float) - open_left[
        edge_y, edge_x
    ].astype(float)
    normal_y = open_down[edge_y, edge_x].astype(float) - open_up[edge_y, edge_x].astype(
        float
    )
    lengths = np.hypot(normal_x, normal_y)
    lengths[lengths == 0] = 1
    normal_x /= lengths
    normal_y /= lengths

    for z in np.linspace(0, depth, max(4, depth // 2)):
        points.append(np.column_stack((edge_x, edge_y, np.full(len(edge_x), z))))
        normals.append(np.column_stack((normal_x, normal_y, np.zeros(len(edge_x)))))

    xyz = np.concatenate(points).astype(np.float32)
    nxyz = np.concatenate(normals).astype(np.float32)
    xyz -= np.array((width / 2, height / 2, depth / 2), dtype=np.float32)
    xyz /= width
    return xyz, nxyz


def rotation(yaw: float, tilt: float) -> np.ndarray:
    cy, sy = math.cos(yaw), math.sin(yaw)
    cx, sx = math.cos(tilt), math.sin(tilt)
    around_y = np.array(((cy, 0, sy), (0, 1, 0), (-sy, 0, cy)), dtype=np.float32)
    around_x = np.array(((1, 0, 0), (0, cx, -sx), (0, sx, cx)), dtype=np.float32)
    return around_x @ around_y


def project(
    points: np.ndarray, normals: np.ndarray, yaw: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    matrix = rotation(yaw, math.radians(4.5))
    moved = points @ matrix.T
    facing = normals @ matrix.T
    visible = facing[:, 2] < 0
    moved = moved[visible]
    facing = facing[visible]

    distance = moved[:, 2] + 6.4
    perspective = 4.4 / distance
    light = np.array((-0.18, -0.42, -1.0), dtype=np.float32)
    light /= np.linalg.norm(light)
    brightness = 0.24 + 0.76 * np.clip(facing @ light, 0, 1)
    brightness *= 1 - 0.22 * np.clip((distance - 6.4) / 0.6 + 0.5, 0, 1)
    shades = np.clip(
        np.rint(brightness * (len(CHARACTERS) - 1)), 1, len(CHARACTERS) - 1
    ).astype(int)
    return moved[:, 0] * perspective, moved[:, 1] * perspective, distance, shades


def grid_transform(
    projections: list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]],
    layout: Layout,
) -> tuple[float, float, float, int]:
    all_x = np.concatenate([item[0] for item in projections])
    all_y = np.concatenate([item[1] for item in projections])
    x_min, x_max = all_x.min(), all_x.max()
    y_min, y_max = all_y.min(), all_y.max()
    scale = 0.91 * (layout.columns - 1) / (x_max - x_min)
    aspect = layout.cell_width / layout.cell_height
    rows = math.ceil((y_max - y_min) * scale * aspect) + layout.row_margin * 2 + 1
    offset_x = (layout.columns - 1) / 2 - (x_min + x_max) * scale / 2
    offset_y = (rows - 1) / 2 - (y_min + y_max) * scale * aspect / 2
    return scale, offset_x, offset_y, rows


def ascii_frame(
    projection: tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray],
    transform: tuple[float, float, float, int],
    layout: Layout,
) -> list[str]:
    screen_x, screen_y, depth, shades = projection
    scale, offset_x, offset_y, rows = transform
    columns = np.rint(offset_x + screen_x * scale).astype(int)
    row_ids = np.rint(
        offset_y + screen_y * scale * (layout.cell_width / layout.cell_height)
    ).astype(int)
    inside = (
        (columns >= 0) & (columns < layout.columns) & (row_ids >= 0) & (row_ids < rows)
    )
    columns, row_ids, depth, shades = (
        value[inside] for value in (columns, row_ids, depth, shades)
    )

    grid = np.zeros((rows, layout.columns), dtype=np.int8)
    for index in np.argsort(-depth):
        grid[row_ids[index], columns[index]] = shades[index]
    return ["".join(CHARACTERS[value] for value in row) for row in grid]


def frame_markup(
    rows: list[str], layout: Layout, art_top: float, child: str = "", attrs: str = ""
) -> str:
    lines = []
    font_size = layout.cell_height * 0.92
    for row_number, raw_line in enumerate(rows):
        trimmed = raw_line.rstrip()
        if not trimmed.strip():
            continue
        leading = len(trimmed) - len(trimmed.lstrip())
        content = trimmed[leading:]
        x = layout.padding + leading * layout.cell_width
        y = art_top + row_number * layout.cell_height + layout.cell_height * 0.78
        lines.append(
            f'<text xml:space="preserve" x="{x:.1f}" y="{y:.1f}" font-size="{font_size:.1f}" '
            f'textLength="{len(content) * layout.cell_width:.1f}" lengthAdjust="spacing">'
            f"{html.escape(content)}</text>"
        )
    return f'<g fill="#c9d1d9" {attrs}>{"".join(lines)}{child}</g>'


def svg_document(
    frames: list[list[str]],
    layout: Layout,
    terminal_user: str,
    duration: float,
    reveal: float,
    static: bool,
) -> str:
    rows = len(frames[0])
    art_width = layout.columns * layout.cell_width
    art_height = rows * layout.cell_height
    width = round(art_width + layout.padding * 2)
    height = round(layout.title_height + art_height + layout.padding)
    art_top = layout.title_height + layout.padding * 0.3
    parts = [
        (
            f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}" font-family="ui-monospace, SFMono-Regular, Menlo, Consolas, monospace">'
        ),
        (
            '<defs><linearGradient id="panel" x1="0" y1="0" x2="0" y2="1">'
            '<stop offset="0" stop-color="#111722"/><stop offset="1" stop-color="#0d1117"/>'
            "</linearGradient></defs>"
        ),
        f'<rect width="{width}" height="{height}" rx="12" fill="url(#panel)"/>',
        (
            f'<rect x="0.5" y="0.5" width="{width - 1}" height="{height - 1}" rx="12" '
            'fill="none" stroke="#30363d"/>'
        ),
        f'<line x1="0" y1="{layout.title_height}" x2="{width}" y2="{layout.title_height}" stroke="#30363d"/>',
    ]
    for index, color in enumerate(("#ff5f56", "#ffbd2e", "#27c93f")):
        parts.append(
            f'<circle cx="{layout.padding + index * 15}" cy="{layout.title_height / 2}" r="4.5" fill="{color}"/>'
        )
    parts.append(
        f'<text x="{width / 2:.1f}" y="{layout.title_height / 2 + 4:.1f}" fill="#7d8590" '
        f'font-size="11.5" text-anchor="middle">{html.escape(terminal_user)}@github: ~$ ./wordmark.sh --3d</text>'
    )

    if static:
        parts.append(frame_markup(frames[0], layout, art_top))
    else:
        parts.append(
            f'<clipPath id="intro"><rect x="{layout.padding}" y="{art_top:.1f}" height="{art_height:.1f}" width="0">'
            f'<animate attributeName="width" from="0" to="{art_width:.1f}" dur="{reveal:.2f}s" fill="freeze"/>'
            "</rect></clipPath>"
        )
        first = frame_markup(frames[0], layout, art_top)
        parts.append(
            f'<g clip-path="url(#intro)">{first}<set attributeName="opacity" to="0" begin="{reveal:.2f}s"/></g>'
        )
        parts.append(
            f'<rect x="{layout.padding}" y="{art_top + 2:.1f}" width="{layout.cell_width * 1.6:.1f}" '
            f'height="{art_height - 4:.1f}" fill="#c9d1d9" opacity="0.16">'
            f'<animate attributeName="x" from="{layout.padding}" to="{layout.padding + art_width:.1f}" '
            f'dur="{reveal:.2f}s" fill="freeze"/><set attributeName="opacity" to="0" begin="{reveal:.2f}s"/></rect>'
        )
        count = len(frames)
        for index, frame in enumerate(frames):
            if index == 0:
                values = "1;0"
                times = f"0;{1 / count:.5f}"
            else:
                values = "0;1;0"
                times = f"0;{index / count:.5f};{(index + 1) / count:.5f}"
            animation = (
                f'<animate attributeName="opacity" calcMode="discrete" values="{values}" '
                f'keyTimes="{times}" dur="{duration:.2f}s" begin="{reveal:.2f}s" repeatCount="indefinite"/>'
            )
            parts.append(frame_markup(frame, layout, art_top, animation, 'opacity="0"'))

    parts.append("</svg>")
    return "".join(parts)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--text")
    parser.add_argument("--font")
    parser.add_argument("--font-index", type=int)
    parser.add_argument("--columns", type=int)
    parser.add_argument("--row-margin", type=int)
    parser.add_argument("--frames", type=int, default=20)
    parser.add_argument("--duration", type=float, default=5.0)
    parser.add_argument("--reveal", type=float, default=1.6)
    parser.add_argument("--static", action="store_true")
    parser.add_argument("--out", type=Path)
    options = parser.parse_args()

    config = load_config(
        options.config,
        {
            "terminal_user",
            "wordmark",
            "wordmark_output",
            "wordmark_font_pattern",
            "wordmark_columns",
            "wordmark_row_margin",
        },
    )
    text = options.text or config["wordmark"]
    resolved_font, resolved_index = (
        (options.font, 0)
        if options.font
        else resolve_font(config["wordmark_font_pattern"])
    )
    font_index = (
        options.font_index if options.font_index is not None else resolved_index
    )
    columns = (
        options.columns
        if options.columns is not None
        else int(config["wordmark_columns"])
    )
    row_margin = (
        options.row_margin
        if options.row_margin is not None
        else int(config["wordmark_row_margin"])
    )
    output = options.out or project_path(config["wordmark_output"])

    layout = Layout(columns=columns, row_margin=row_margin)
    points, normals = surface_from(text_mask(text, resolved_font, font_index))
    center = math.radians(-12)
    swing = math.radians(10)
    yaws = [
        center + swing * math.sin(2 * math.pi * index / options.frames)
        for index in range(options.frames)
    ]
    projections = [project(points, normals, yaw) for yaw in yaws]
    transform = grid_transform(projections, layout)
    frames = [ascii_frame(item, transform, layout) for item in projections]
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        svg_document(
            frames,
            layout,
            config["terminal_user"],
            options.duration,
            options.reveal,
            options.static,
        ),
        encoding="utf-8",
    )
    print(f"wrote {output} ({len(frames)} frames)")


if __name__ == "__main__":
    main()
