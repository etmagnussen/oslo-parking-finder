"""Generate PWA icons (PNG) from a tiny SVG template.

Run:

    python scripts/make_icons.py

Writes web/static/icons/icon-{192,512}.png and icon-maskable-512.png.

Implementation note: we avoid Pillow to keep dependencies minimal.
Instead we use ``cairosvg`` if available, falling back to a pure-Python
PNG writer that paints a rounded square with a white "P" glyph.
"""
from __future__ import annotations

import struct
import zlib
from pathlib import Path

# Brand color = the "free" marker green.
BG = (46, 204, 113)            # #2ecc71
FG = (255, 255, 255)
MASKABLE_BG = (46, 204, 113)   # safe zone fully filled


def _png_bytes(width: int, height: int, pixels: bytes) -> bytes:
    """Encode RGBA pixel bytes as a minimal PNG (no external deps)."""

    def chunk(tag: bytes, data: bytes) -> bytes:
        return (
            struct.pack(">I", len(data))
            + tag
            + data
            + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        )

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    # Add filter byte (0 = None) at the start of each row.
    raw = b"".join(b"\x00" + pixels[y * width * 4 : (y + 1) * width * 4] for y in range(height))
    idat = zlib.compress(raw, 9)
    return signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")


def _draw_icon(size: int, *, maskable: bool = False) -> bytes:
    """Paint a rounded square (or full square if maskable) with a white 'P'."""
    radius = 0 if maskable else int(size * 0.22)
    px = bytearray(size * size * 4)

    # Parameters for the "P" glyph — a vertical bar plus a top loop.
    # We model the P inside a centered square of side ~0.6*size.
    cx, cy = size / 2, size / 2
    glyph_side = size * 0.6
    left = cx - glyph_side * 0.32
    right = cx + glyph_side * 0.18
    top = cy - glyph_side * 0.45
    bottom = cy + glyph_side * 0.45

    bar_left = left
    bar_right = left + glyph_side * 0.20
    loop_outer_r = glyph_side * 0.30
    loop_inner_r = glyph_side * 0.12
    loop_cx = bar_right - glyph_side * 0.02
    loop_cy = top + loop_outer_r

    def inside_rounded_square(x: float, y: float) -> bool:
        # Distance to the nearest corner — rounded if maskable=False.
        if x < radius and y < radius:
            return (radius - x) ** 2 + (radius - y) ** 2 <= radius * radius
        if x > size - radius and y < radius:
            return (x - (size - radius)) ** 2 + (radius - y) ** 2 <= radius * radius
        if x < radius and y > size - radius:
            return (radius - x) ** 2 + (y - (size - radius)) ** 2 <= radius * radius
        if x > size - radius and y > size - radius:
            return (x - (size - radius)) ** 2 + (y - (size - radius)) ** 2 <= radius * radius
        return True

    def inside_p(x: float, y: float) -> bool:
        # Vertical bar.
        if bar_left <= x <= bar_right and top <= y <= bottom:
            return True
        # Loop = ring on the upper-right.
        dx = x - loop_cx
        dy = y - loop_cy
        d2 = dx * dx + dy * dy
        if loop_inner_r ** 2 <= d2 <= loop_outer_r ** 2 and x >= bar_left:
            return True
        return False

    bg = MASKABLE_BG if maskable else BG
    for y in range(size):
        for x in range(size):
            idx = (y * size + x) * 4
            if not inside_rounded_square(x + 0.5, y + 0.5):
                # Transparent corner.
                px[idx : idx + 4] = bytes((0, 0, 0, 0))
                continue
            if inside_p(x + 0.5, y + 0.5):
                px[idx : idx + 4] = bytes((*FG, 255))
            else:
                px[idx : idx + 4] = bytes((*bg, 255))
    return _png_bytes(size, size, bytes(px))


def main() -> int:
    out = Path(__file__).resolve().parent.parent / "web" / "static" / "icons"
    out.mkdir(parents=True, exist_ok=True)
    (out / "icon-192.png").write_bytes(_draw_icon(192))
    (out / "icon-512.png").write_bytes(_draw_icon(512))
    (out / "icon-maskable-512.png").write_bytes(_draw_icon(512, maskable=True))
    print(f"OK: wrote 3 icons to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
