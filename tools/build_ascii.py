"""Convert the GitHub user's Cookie Monster profile picture (1000x1000 RGBA master)
into 87x47 ASCII art portraits for both Dark Mode and Light Mode, supporting both
plain text (assets/ascii-art*.txt) and True-Color ANSI RLE spans (assets/ascii-art-*.json).

Key capabilities:
- Uses 1000x1000 RGBA master with explicit alpha segmentation and spherical eyeball
  geometry so the pure white sclera of Cookie Monster's googly eyes never collides
  with the external studio background or gets tinted brown by compression noise.
- Region-aware glyph density and color mapping for:
  1. External terminal background (subtle '.' dots)
  2. Googly eyeballs: crisp circular rim contour, pure snow-white/ice-silver 3D sclera,
     and high-contrast off-center black pupils with specular catchlights
  3. Shaggy Sesame Street blue fur with 5-level highlight/shadow depth
  4. Wide-open mouth cavity
  5. Golden chocolate-chip cookie with dark chocolate chips
"""

from __future__ import annotations

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

# Textured character ramps (no spaces so outer columns never collapse)
RAMP_FUR_DARK = ".:;i!lI><~+_-?][}{1)(|/\\tfjrxnuvczXYUJCLQ0OZmwqpdbkhao*#MW&8%B@$"
RAMP_FUR_LIGHT = RAMP_FUR_DARK[::-1]
RAMP_SCLERA_DARK = "oO0Q#MW8%B@$"
RAMP_SCLERA_LIGHT = ".:;~+oO0Q"
RAMP_DENSE = "#MW&8%B@$"


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
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            d1 = math.hypot(x - cx1, y - cy1)
            d2 = math.hypot(x - cx2, y - cy2)
            in_eye1 = d1 <= r1
            in_eye2 = d2 <= r2
            in_eye = in_eye1 or in_eye2
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

    # Enhanced local contrast map for fur and cookie texture
    gray = ImageOps.autocontrast(master.convert("L"), cutoff=1)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.6, percent=150, threshold=2))
    gray = ImageEnhance.Contrast(gray).enhance(1.25)
    resized_gray = gray.resize((cols, rows), Image.Resampling.LANCZOS)

    # Normalized eyeball & pupil geometry in 1000x1000 master space
    cx1, cy1, r1 = 273.9, 234.8, 134.8
    cx2, cy2, r2 = 543.5, 143.5, 134.8
    # Pupil centers for subtle specular catchlight
    px1_c, py1_c = 313.6, 262.3
    px2_c, py2_c = 524.6, 169.1

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

            r, g, b, a = pix[ix, iy]
            lum = 0.299 * r + 0.587 * g + 0.114 * b
            glum = resized_gray.getpixel((x, y))

            d1 = math.hypot(px - cx1, py - cy1)
            d2 = math.hypot(px - cx2, py - cy2)
            in_eye1 = d1 <= r1
            in_eye2 = d2 <= r2
            in_eye = in_eye1 or in_eye2

            # 1. External Background
            if a < 128 and not in_eye:
                d_chars.append(".")
                d_cols.append("#21262d")
                l_chars.append(".")
                l_cols.append("#d8dee4")
                continue

            # 2. Googly Eyeballs (Sclera, Circular Rim, and Black Pupils)
            if in_eye and not (b - r > 22 and lum < 175 and py > 205):
                # Check if inside the dark googly pupil
                if r < 115 and g < 115 and b < 115 and (b - r) < 20:
                    # Specular glint at upper-left of each pupil
                    glint1 = math.hypot(px - (px1_c - 15), py - (py1_c - 15)) < 14
                    glint2 = math.hypot(px - (px2_c - 16), py - (py2_c - 16)) < 15
                    if glint1 or glint2:
                        d_chars.append("*")
                        d_cols.append("#e2e8f0")
                        l_chars.append("*")
                        l_cols.append("#64748b")
                    else:
                        d_chars.append("@")
                        d_cols.append("#1e293b")
                        l_chars.append("@")
                        l_cols.append("#090d16")
                    continue

                # Determine normalized radial position on the active eyeball sphere
                if in_eye1 and (not in_eye2 or d1 < d2):
                    dn = d1 / r1
                    nx_s = (px - cx1) / r1
                    ny_s = (py - cy1) / r1
                    rim_zone = (dn >= 0.87 and py < 340)
                else:
                    dn = d2 / r2
                    nx_s = (px - cx2) / r2
                    ny_s = (py - cy2) / r2
                    rim_zone = (dn >= 0.87 and py < 255)

                # Seam where the two eyeballs touch
                seam_zone = (abs(d1 - d2) < 13.5 and d1 <= r1 and d2 <= r2)

                if rim_zone or seam_zone:
                    # Crisp circular eyeball boundary
                    d_chars.append("O")
                    d_cols.append("#94a3b8")
                    l_chars.append("O")
                    l_cols.append("#334155")
                else:
                    # Pure white of the eyes (sclera) with smooth 3D sphere shading
                    sphere_shade = max(0.0, min(1.0, 1.0 - 0.35 * math.hypot(nx_s + 0.28, ny_s + 0.28)))
                    d_idx = min(len(RAMP_SCLERA_DARK) - 1, int(sphere_shade * (len(RAMP_SCLERA_DARK) - 1)))
                    d_chars.append(RAMP_SCLERA_DARK[d_idx])
                    d_cols.append("#ffffff" if sphere_shade > 0.42 else "#e2e8f0")

                    l_idx = min(len(RAMP_SCLERA_LIGHT) - 1, int((1.0 - sphere_shade) * (len(RAMP_SCLERA_LIGHT) - 1)))
                    l_chars.append(RAMP_SCLERA_LIGHT[l_idx])
                    l_cols.append("#cbd5e1" if sphere_shade > 0.45 else "#94a3b8")
                continue

            # 3. Chocolate Chip Cookie (lower-right warm golden region)
            if px > 500 and py > 540 and (r - b) > 16:
                n_fur = len(RAMP_FUR_DARK) - 1
                if lum < 105:
                    # Dark chocolate chip or baked crevice
                    d_chars.append("@")
                    d_cols.append("#78350f")
                    l_chars.append("@")
                    l_cols.append("#451a03")
                else:
                    c_idx_d = max(28, min(n_fur, round((glum / 255.0) * n_fur)))
                    c_idx_l = max(30, min(n_fur - 4, round((glum / 255.0) * n_fur)))
                    d_chars.append(RAMP_FUR_DARK[c_idx_d])
                    l_chars.append(RAMP_FUR_DARK[c_idx_l])
                    if lum > 185:
                        d_cols.append("#fbbf24")
                        l_cols.append("#d97706")
                    elif lum > 145:
                        d_cols.append("#f59e0b")
                        l_cols.append("#b45309")
                    else:
                        d_cols.append("#d97706")
                        l_cols.append("#92400e")
                continue

            # 4. Wide-Open Black Mouth Cavity (& deep dark chin crease)
            if lum < 48 and (b - r) < 22 and 330 < py < 920:
                d_chars.append(":" if lum < 25 else "+")
                d_cols.append("#1e293b" if py < 820 else "#161b22")
                l_chars.append("@" if lum < 25 else "#")
                l_cols.append("#090d16" if py < 820 else "#1e293b")
                continue

            # 5. Iconic Cookie Monster Blue Fur
            n_fur = len(RAMP_FUR_DARK) - 1
            f_idx_d = max(20, min(n_fur, round((glum / 255.0) * n_fur)))
            f_idx_l = max(22, min(n_fur, round(((255 - glum) / 255.0) * n_fur)))
            d_chars.append(RAMP_FUR_DARK[f_idx_d])
            l_chars.append(RAMP_FUR_DARK[f_idx_l])

            if lum < 55:
                d_cols.append("#0369a1")
                l_cols.append("#0c4a6e")
            elif lum < 88:
                d_cols.append("#0284c7")
                l_cols.append("#075985")
            elif lum < 122:
                d_cols.append("#0ea5e9")
                l_cols.append("#0369a1")
            elif lum < 155:
                d_cols.append("#38bdf8")
                l_cols.append("#0284c7")
            else:
                d_cols.append("#7dd3fc")
                l_cols.append("#0ea5e9")

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
    print(f"Wrote {ASCII_DARK_OUT.name} and {ASCII_DARK_JSON.name} ({dark_span_count} RLE color spans)")
    print(f"Wrote {ASCII_LIGHT_OUT.name} and {ASCII_LIGHT_JSON.name} ({light_span_count} RLE color spans)")


if __name__ == "__main__":
    main()
