#!/usr/bin/env python
"""Generate the integration's local brand images (pure standard library).

Home Assistant >= 2025.7 renders ``custom_components/<domain>/brand/`` images on
the integration page, in the "Add integration" dialog and in HACS, so the
integration looks native instead of falling back to a generic placeholder.

The art is the product in one glyph: a slate ceiling panel with a staggered grid
of recessed fixtures glowing along the palette used by the engine
(#38BDF8 cyan -> #A78BFA violet -> #FB7185 rose).

usage:  python tools/make_brand.py        # rewrites custom_components/.../brand/*
"""

from __future__ import annotations

import math
import pathlib
import struct
import zlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
BRAND = ROOT / "custom_components" / "ceiling_scene_generator" / "brand"

BG_TOP = (15, 23, 42)        # #0F172A
BG_BOTTOM = (30, 41, 59)     # #1E293B
ACCENT = (56, 189, 248)      # #38BDF8
HALO = (13, 148, 136)


# --------------------------------------------------------------------------- #
# Minimal RGBA PNG writer
# --------------------------------------------------------------------------- #

def write_png(path: pathlib.Path, pixels: list[list[tuple[int, int, int, int]]]) -> None:
    height = len(pixels)
    width = len(pixels[0])
    raw = bytearray()
    for row in pixels:
        raw.append(0)  # filter type 0 (None)
        for r, g, b, a in row:
            raw += bytes((r, g, b, a))

    def chunk(tag: bytes, payload: bytes) -> bytes:
        return (
            struct.pack(">I", len(payload))
            + tag
            + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    header = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
        + chunk(b"IEND", b"")
    )


# --------------------------------------------------------------------------- #
# Drawing helpers
# --------------------------------------------------------------------------- #

def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def mix(c1: tuple[int, int, int], c2: tuple[int, int, int], t: float) -> tuple[int, int, int]:
    return (
        int(round(lerp(c1[0], c2[0], t))),
        int(round(lerp(c1[1], c2[1], t))),
        int(round(lerp(c1[2], c2[2], t))),
    )


def pal(t: float) -> tuple[int, int, int]:
    """cyan -> teal -> violet -> rose, cyclic (matches the engine's default palette)."""
    stops = [(56, 189, 248), (45, 212, 191), (167, 139, 250), (251, 113, 133)]
    t = t % 1.0
    span = 1.0 / len(stops)
    index = min(int(t / span), len(stops) - 1)
    local = (t - index * span) / span
    return mix(stops[index], stops[(index + 1) % len(stops)], local)


def rounded_mask(size: int, radius_ratio: float = 0.22) -> list[list[bool]]:
    r = size * radius_ratio
    mask = [[False] * size for _ in range(size)]
    for y in range(size):
        for x in range(size):
            cx = min(x + 0.5, size - (x + 0.5))
            cy = min(y + 0.5, size - (y + 0.5))
            if cx >= r or cy >= r:
                mask[y][x] = True
                continue
            if math.hypot(r - cx, r - cy) <= r + 0.5:
                mask[y][x] = True
    return mask


def ceiling_icon(size: int, glow_scale: float = 1.0) -> list[list[tuple[int, int, int, int]]]:
    """Square icon: staggered 4x5 fixture grid over a slate gradient."""
    mask = rounded_mask(size)
    rows, cols = 5, 4
    dots: list[tuple[float, float, float, tuple[int, int, int]]] = []
    margin = size * 0.16
    cell_w = (size - 2 * margin) / cols
    cell_h = (size - 2 * margin) / rows
    for row in range(rows):
        offset = cell_w / 2 if row % 2 else 0.0
        for col in range(cols):
            x = margin + cell_w * (col + 0.5) + offset
            if x > size - margin * 0.6:
                continue
            y = margin + cell_h * (row + 0.5)
            t = (col / max(cols - 1, 1)) * 0.75 + (row / max(rows - 1, 1)) * 0.25
            dots.append((x, y, cell_w * 0.30, pal(t)))

    pixels: list[list[tuple[int, int, int, int]]] = []
    halo = cell_w * 1.15 * glow_scale
    for y in range(size):
        row_out = []
        ty = y / max(size - 1, 1)
        base = mix(BG_TOP, BG_BOTTOM, ty)
        for x in range(size):
            if not mask[y][x]:
                row_out.append((0, 0, 0, 0))
                continue
            r, g, b = base
            # ambient ceiling sheen: soft violet wash from the top-left
            sheen = max(0.0, 1.0 - math.hypot(x * 0.9, y) / (size * 1.35))
            r, g, b = mix((r, g, b), (45, 32, 72), sheen * 0.35)
            for dx, dy, dot_r, colour in dots:
                dist = math.hypot(x - dx, y - dy)
                if dist < dot_r:
                    r, g, b = mix(colour, (255, 255, 255), 0.45 * (1 - dist / dot_r))
                elif dist < halo:
                    falloff = (1 - (dist - dot_r) / (halo - dot_r)) ** 2.4
                    r, g, b = mix((r, g, b), colour, falloff * 0.42)
            row_out.append((min(r, 255), min(g, 255), min(b, 255), 255))
        pixels.append(row_out)
    return pixels


def ceiling_logo(width: int) -> list[list[tuple[int, int, int, int]]]:
    """Wide logo: the icon's ceiling plus a travelling brightness wave."""
    height = width // 2
    rows, cols = 3, 6
    dots: list[tuple[float, float, float, tuple[int, int, int]]] = []
    margin = height * 0.24
    usable_w = width - 2 * margin * 1.4
    cell_w = usable_w / cols
    cell_h = (height - 2 * margin) / rows
    for row in range(rows):
        offset = cell_w / 2 if row % 2 else 0.0
        for col in range(cols):
            x = margin + cell_w * (col + 0.5) + offset
            y = margin + cell_h * (row + 0.5)
            dots.append((x, y, cell_h * 0.26, pal(col / (cols - 1) * 0.85)))

    pixels = []
    halo = cell_h * 1.25
    for y in range(height):
        ty = y / max(height - 1, 1)
        base = mix(BG_TOP, BG_BOTTOM, ty)
        row_out = []
        for x in range(width):
            r, g, b = base
            wave = 0.5 + 0.5 * math.sin(2 * math.pi * (x / width * 1.15 - 0.25))
            r, g, b = mix((r, g, b), HALO, wave * 0.10)
            for dx, dy, dot_r, colour in dots:
                dist = math.hypot(x - dx, y - dy)
                if dist < dot_r:
                    r, g, b = mix(colour, (255, 255, 255), 0.40 * (1 - dist / dot_r))
                elif dist < halo:
                    falloff = (1 - (dist - dot_r) / (halo - dot_r)) ** 2.6
                    r, g, b = mix((r, g, b), colour, falloff * (0.22 + 0.30 * wave))
            row_out.append((min(r, 255), min(g, 255), min(b, 255), 255))
        pixels.append(row_out)
    return pixels


def main() -> int:
    written = []
    for name, pixels in (
        ("icon.png", ceiling_icon(256)),
        ("icon@2x.png", ceiling_icon(512)),
        ("logo.png", ceiling_logo(256)),
        ("logo@2x.png", ceiling_logo(512)),
    ):
        path = BRAND / name
        write_png(path, pixels)
        written.append((name, path.stat().st_size))
    width = max(len(name) for name, _ in written)
    for name, size in written:
        print(f"{name:<{width}}  {size:>7} bytes  {BRAND / name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
