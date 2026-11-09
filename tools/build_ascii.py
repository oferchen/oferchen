"""Convert the GitHub user's profile picture (1000x1000 RGBA master) into 87x47
True-Color Photo ANSI ASCII art portraits for both Dark Mode and Light Mode
(assets/ascii-art*.txt and assets/ascii-art-*.json).

True-Color Photo ANSI Pipeline:
- Samples authentic per-cell RGB colors from the 1000x1000 high-resolution RGBA master
  using Lanczos downsampling, HLS hue-preserving contrast adaptation, and fine 16-step
  true-color quantization.
- Uses the RGBA alpha channel + spherical eyeball geometry so external background pixels
  never collide with the pure white sclera of Cookie Monster's eyes, and zero chroma
  subsampling noise can tint the white of the eyes brown.
- Preserves the full 69-level photographic ASCII density ramp across all textures.
"""

from __future__ import annotations

import colorsys
import io
import json
import math
import os
from collections import deque
from pathlib import Path
from PIL import Image, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
STATS_SRC = ROOT / "cache" / "stats.json"
LOCAL_AVATAR = ASSETS / "avatar.png"
ASCII_DARK_OUT = ASSETS / "ascii-art.txt"
ASCII_LIGHT_OUT = ASSETS / "ascii-art-light.txt"
ASCII_DARK_JSON = ASSETS / "ascii-art-dark.json"
ASCII_LIGHT_JSON = ASSETS / "ascii-art-light.json"

LOGIN = os.environ.get("GH_LOGIN", "oferchen")

COLS = 87
ROWS = 47

# 69-level photographic character ramp (no space character so outer columns never collapse)
RAMP_LIGHT_BG = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'."
RAMP_DARK_BG = RAMP_LIGHT_BG[::-1]


def hex_round(r: int, g: int, b: int, step: int = 16) -> str:
    """Quantize RGB channels to a fine True-Color Photo ANSI step."""
    qr = min(255, max(0, round(r / step) * step))
    qg = min(255, max(0, round(g / step) * step))
    qb = min(255, max(0, round(b / step) * step))
    return f"#{qr:02x}{qg:02x}{qb:02x}"


def truecolor_dark(r: int, g: int, b: int, a: int, in_eye: bool, rim_or_seam: bool, is_pupil: bool) -> str:
    """Map natural photo RGB values to True-Color Photo ANSI on #0d1117 dark background."""
    if a < 128 and not in_eye:
        return "#21262d"

    lum = 0.299 * r + 0.587 * g + 0.114 * b

    if in_eye:
        if is_pupil:
            return "#64748b" if lum > 55 else "#334155"
        if rim_or_seam:
            return "#94a3b8"
        # Pure neutral white/silver sclera from photo luminance (never brown/yellow)
        if lum > 225:
            return "#ffffff"
        if lum > 195:
            return "#f1f5f9"
        return "#cbd5e1"

    # Deep shadows & dark mouth cavity: lift slightly above #0d1117 so photographic ASCII glyphs show
    if lum < 38:
        return "#334155"

    # True-Color Photo ANSI: preserve exact photo hue via HLS, adapt lightness & saturation for dark mode
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    l_adapted = min(max(l * 1.08, 0.30), 0.88)
    s_adapted = min(1.0, s * 1.20)
    nr, ng, nb = colorsys.hls_to_rgb(h, l_adapted, s_adapted)
    return hex_round(int(nr * 255), int(ng * 255), int(nb * 255), step=16)


def truecolor_light(r: int, g: int, b: int, a: int, in_eye: bool, rim_or_seam: bool, is_pupil: bool) -> str:
    """Map natural photo RGB values to True-Color Photo ANSI on #ffffff light background."""
    if a < 128 and not in_eye:
        return "#d8dee4"

    lum = 0.299 * r + 0.587 * g + 0.114 * b

    if in_eye:
        if is_pupil:
            return "#475569" if lum > 55 else "#0f172a"
        if rim_or_seam:
            return "#334155"
        # Clean cool pearl-silver sclera on white background (never mud brown)
        if lum > 225:
            return "#cbd5e1"
        if lum > 195:
            return "#94a3b8"
        return "#64748b"

    # Deep shadows & dark mouth cavity
    if lum < 42:
        return "#0f172a"

    # True-Color Photo ANSI: preserve exact photo hue via HLS, deepen lightness for white background
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    l_adapted = min(max(l * 0.68, 0.18), 0.55)
    s_adapted = min(1.0, s * 1.22)
    nr, ng, nb = colorsys.hls_to_rgb(h, l_adapted, s_adapted)
    return hex_round(int(nr * 255), int(ng * 255), int(nb * 255), step=16)


def fetch_avatar_bytes() -> bytes | None:
    if LOCAL_AVATAR.exists():
        print(f"Using local high-res avatar master: {LOCAL_AVATAR}")
        return LOCAL_AVATAR.read_bytes()

    import urllib.request
    urls = []
    if STATS_SRC.exists():
        try:
            st = json.loads(STATS_SRC.read_text(encoding="utf-8"))
            if st.get("avatar_url"):
                urls.append(st["avatar_url"])
        except Exception:
            pass
    urls.append(f"https://github.com/{LOGIN}.png?size=460")

    for url in urls:
        try:
            print(f"Downloading profile avatar from {url} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
                if data:
                    return data
        except Exception as exc:
            print(f"  warning: could not download {url}: {exc}")
    return None


def ensure_master_rgba(img: Image.Image) -> Image.Image:
    """Ensure a 1000x1000 RGBA master with clean background alpha & eye sphere separation."""
    W, H = 1000, 1000
    if img.size == (W, H) and img.mode == "RGBA":
        a_min, _ = img.getchannel("A").getextrema()
        if a_min == 0:
            return img

    rgb = img.convert("RGB").resize((W, H), Image.Resampling.LANCZOS)
    rgb = rgb.filter(ImageFilter.UnsharpMask(radius=1.8, percent=135, threshold=2))
    pix = rgb.load()

    cx1, cy1, r1 = 273.9, 234.8, 134.8
    cx2, cy2, r2 = 543.5, 143.5, 134.8

    bg = [[False] * W for _ in range(H)]
    q = deque([(0, 0), (W - 1, 0), (0, H // 3)])
    for sx, sy in list(q):
        bg[sy][sx] = True

    while q:
        x, y = q.popleft()
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if 0 <= nx < W and 0 <= ny < H and not bg[ny][nx]:
                d1 = math.hypot(nx - cx1, ny - cy1)
                d2 = math.hypot(nx - cx2, ny - cy2)
                if d1 <= r1 or d2 <= r2:
                    continue
                r, g, b = pix[nx, ny]
                lum = 0.299 * r + 0.587 * g + 0.114 * b
                if lum > 222 and (b - r) < 20:
                    bg[ny][nx] = True
                    q.append((nx, ny))

    out = Image.new("RGBA", (W, H))
    opix = out.load()
    for y in range(H):
        for x in range(W):
            r, g, b = pix[x, y]
            d1 = math.hypot(x - cx1, y - cy1)
            d2 = math.hypot(x - cx2, y - cy2)
            in_eye = (d1 <= r1) or (d2 <= r2)
            if bg[y][x] and not in_eye:
                opix[x, y] = (255, 255, 255, 0)
            else:
                opix[x, y] = (r, g, b, 255)
    return out


def build_portraits(
    master: Image.Image,
    cols: int = COLS,
    rows: int = ROWS,
) -> tuple[str, list[list[tuple[str, str]]], str, list[list[tuple[str, str]]]]:
    W, H = master.size
    pix = master.load()

    # Composite onto dark/light backgrounds for Lanczos photographic luminance & RGB sampling
    bg_dark = Image.new("RGBA", (W, H), (13, 17, 23, 255))
    bg_light = Image.new("RGBA", (W, H), (255, 255, 255, 255))
    comp_dark = Image.alpha_composite(bg_dark, master).convert("RGB")
    comp_light = Image.alpha_composite(bg_light, master).convert("RGB")

    # Photographic luminance ramps with UnsharpMask edge enhancement
    gray_dark = ImageOps.autocontrast(comp_dark.convert("L"), cutoff=1)
    gray_dark = gray_dark.filter(ImageFilter.UnsharpMask(radius=1.6, percent=145, threshold=2))
    gray_dark = ImageEnhance.Contrast(gray_dark).enhance(1.3)
    resized_gray_dark = gray_dark.resize((cols, rows), Image.Resampling.LANCZOS)

    gray_light = ImageOps.autocontrast(comp_light.convert("L"), cutoff=1)
    gray_light = gray_light.filter(ImageFilter.UnsharpMask(radius=1.6, percent=145, threshold=2))
    gray_light = ImageEnhance.Contrast(gray_light).enhance(1.3)
    resized_gray_light = gray_light.resize((cols, rows), Image.Resampling.LANCZOS)

    # True-Color RGB downsampling
    rgb_dark = ImageEnhance.Color(comp_dark).enhance(1.25).resize((cols, rows), Image.Resampling.LANCZOS)
    rgb_light = ImageEnhance.Color(comp_light).enhance(1.25).resize((cols, rows), Image.Resampling.LANCZOS)
    alpha_small = master.getchannel("A").resize((cols, rows), Image.Resampling.LANCZOS)

    cx1, cy1, r1 = 273.9, 234.8, 134.8
    cx2, cy2, r2 = 543.5, 143.5, 134.8
    n_ramp = len(RAMP_DARK_BG) - 1

    dark_lines: list[str] = []
    light_lines: list[str] = []
    dark_runs_all: list[list[tuple[str, str]]] = []
    light_runs_all: list[list[tuple[str, str]]] = []

    for y in range(rows):
        d_chars: list[str] = []
        d_cols: list[str] = []
        l_chars: list[str] = []
        l_cols: list[str] = []

        py = min(H - 1, (y + 0.5) * H / rows)
        iy = int(py)

        for x in range(cols):
            px = min(W - 1, (x + 0.5) * W / cols)
            ix = int(px)

            mr, mg, mb, ma = pix[ix, iy]
            mlum = 0.299 * mr + 0.587 * mg + 0.114 * mb
            a_cell = alpha_small.getpixel((x, y))

            d1 = math.hypot(px - cx1, py - cy1)
            d2 = math.hypot(px - cx2, py - cy2)
            in_eye1 = d1 <= r1
            in_eye2 = d2 <= r2
            # Exclude lower blue fur overlapping bottom of eye
            fur_overlap = (mb - mr > 22 and mlum < 175 and py > 205)
            in_eye = (in_eye1 or in_eye2) and not fur_overlap

            is_pupil = in_eye and (mr < 115 and mg < 115 and mb < 115 and (mb - mr) < 20)
            if in_eye1 and (not in_eye2 or d1 < d2):
                rim_zone = (d1 / r1 >= 0.87 and py < 340)
            else:
                rim_zone = (d2 / r2 >= 0.87 and py < 255)
            seam_zone = (abs(d1 - d2) < 13.5 and d1 <= r1 and d2 <= r2)
            rim_or_seam = in_eye and not is_pupil and (rim_zone or seam_zone)

            # Photographic ASCII glyph from 69-level ramp
            glum_d = resized_gray_dark.getpixel((x, y))
            glum_l = resized_gray_light.getpixel((x, y))
            char_d = RAMP_DARK_BG[round((glum_d / 255.0) * n_ramp)]
            char_l = RAMP_LIGHT_BG[round((glum_l / 255.0) * n_ramp)]

            # Ensure light-mode eye rim & sclera stay crisp and well-defined on white card
            if in_eye and not is_pupil:
                if rim_or_seam:
                    char_l = RAMP_LIGHT_BG[min(n_ramp - 8, round((glum_l / 255.0) * n_ramp) - 22)]
                else:
                    char_l = RAMP_LIGHT_BG[min(n_ramp - 4, max(42, round((glum_l / 255.0) * n_ramp) - 6))]

            dr, dg, db = rgb_dark.getpixel((x, y))
            lr, lg, lb = rgb_light.getpixel((x, y))
            if in_eye:
                dr, dg, db = mr, mg, mb
                lr, lg, lb = mr, mg, mb

            col_d = truecolor_dark(dr, dg, db, a_cell, in_eye, rim_or_seam, is_pupil)
            col_l = truecolor_light(lr, lg, lb, a_cell, in_eye, rim_or_seam, is_pupil)

            d_chars.append(char_d)
            d_cols.append(col_d)
            l_chars.append(char_l)
            l_cols.append(col_l)

        dark_lines.append("".join(d_chars))
        light_lines.append("".join(l_chars))
        dark_runs_all.append(_rle_row(d_chars, d_cols))
        light_runs_all.append(_rle_row(l_chars, l_cols))

    return (
        "\n".join(dark_lines) + "\n",
        dark_runs_all,
        "\n".join(light_lines) + "\n",
        light_runs_all,
    )


def _rle_row(chars: list[str], cols: list[str]) -> list[tuple[str, str]]:
    runs: list[tuple[str, str]] = []
    cur_col = cols[0]
    cur_text = [chars[0]]
    for c, col in zip(chars[1:], cols[1:]):
        if col == cur_col:
            cur_text.append(c)
        else:
            runs.append(("".join(cur_text), cur_col))
            cur_col = col
            cur_text = [c]
    runs.append(("".join(cur_text), cur_col))
    return runs


def main() -> None:
    data = fetch_avatar_bytes()
    if not data:
        print("No avatar image available; keeping existing ASCII art files.")
        return

    raw_img = Image.open(io.BytesIO(data))
    master = ensure_master_rgba(raw_img)

    ASSETS.mkdir(exist_ok=True)
    dark_txt, dark_spans, light_txt, light_spans = build_portraits(master, COLS, ROWS)

    ASCII_DARK_OUT.write_text(dark_txt, encoding="utf-8")
    ASCII_LIGHT_OUT.write_text(light_txt, encoding="utf-8")
    ASCII_DARK_JSON.write_text(json.dumps(dark_spans), encoding="utf-8")
    ASCII_LIGHT_JSON.write_text(json.dumps(light_spans), encoding="utf-8")

    dark_span_count = sum(len(r) for r in dark_spans)
    light_span_count = sum(len(r) for r in light_spans)
    print(f"Wrote {ASCII_DARK_OUT.name} and {ASCII_DARK_JSON.name} ({dark_span_count} True-Color RLE spans)")
    print(f"Wrote {ASCII_LIGHT_OUT.name} and {ASCII_LIGHT_JSON.name} ({light_span_count} True-Color RLE spans)")


if __name__ == "__main__":
    main()
