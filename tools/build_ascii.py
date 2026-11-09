"""Convert the GitHub user's profile picture into 87x47 ASCII art portraits
for both Dark Mode and Light Mode, supporting both plain monochrome text
and rich multi-color ANSI/terminal color spans (assets/ascii-art-*.json).

Enhancements:
- UnsharpMask edge enhancement + adaptive contrast so facial contours stay razor-sharp at 87x47.
- Color quantization + Run-Length Encoding (RLE) to sample authentic RGB tones from the avatar.
- Contrast adaptation: lifted shadow highlights for dark mode, deepened tones for light mode.
- Exact 0.54 cell aspect ratio (87 cols x 47 rows).
"""

from __future__ import annotations

import colorsys
import io
import json
import os
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance, ImageFilter

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

# 69-level high-detail character ramp (no space character so outer columns never collapse)
RAMP_LIGHT_BG = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'.`"
RAMP_DARK_BG = RAMP_LIGHT_BG[::-1]


def hex_round(r: int, g: int, b: int, step: int = 28) -> str:
    """Quantize RGB channels to a smooth retro terminal palette step."""
    qr = min(255, max(0, round(r / step) * step))
    qg = min(255, max(0, round(g / step) * step))
    qb = min(255, max(0, round(b / step) * step))
    return f"#{qr:02x}{qg:02x}{qb:02x}"


def color_for_dark(r: int, g: int, b: int) -> str:
    """Map natural RGB values to a vibrant high-contrast palette on #0d1117 background."""
    # Pure studio background (white/off-white)
    if r > 238 and g > 238 and b > 238:
        return "#21262d"

    lum = 0.299 * r + 0.587 * g + 0.114 * b

    # White of the eyes, sclera, specular reflections & glints
    # High luminance in facial region must be CRISP WHITE, never mud brown
    if lum > 185 and min(r, g) > 175 and b > 115:
        return "#f8fafc"

    # Deep shadows & dark hair: lift slightly above #0d1117 so texture is visible
    if lum < 45:
        return "#475569"

    # True color for skin, clothing, denim, hair:
    # Use HLS to preserve natural hue without distortion
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    l_adapted = min(max(l, 0.35), 0.88)
    s_adapted = min(1.0, s * 1.10)

    nr, ng, nb = colorsys.hls_to_rgb(h, l_adapted, s_adapted)
    return hex_round(int(nr * 255), int(ng * 255), int(nb * 255), step=28)


def color_for_light(r: int, g: int, b: int) -> str:
    """Map natural RGB values to a rich deep palette on pure white #ffffff background."""
    # Pure studio background
    if r > 238 and g > 238 and b > 238:
        return "#d0d7de"

    lum = 0.299 * r + 0.587 * g + 0.114 * b

    # White of the eyes, sclera & highlights on white background
    # Keep as clean neutral cool slate, NEVER warm mud brown
    if lum > 185 and min(r, g) > 175 and b > 115:
        return "#475569"

    # Deep shadows & dark hair
    if lum < 50:
        return "#0f172a"

    # True color: preserve exact hue, scale lightness for crisp contrast on white
    h, l, s = colorsys.rgb_to_hls(r / 255.0, g / 255.0, b / 255.0)
    l_adapted = min(max(l * 0.65, 0.18), 0.52)
    s_adapted = min(1.0, s * 1.15)

    nr, ng, nb = colorsys.hls_to_rgb(h, l_adapted, s_adapted)
    return hex_round(int(nr * 255), int(ng * 255), int(nb * 255), step=28)


def fetch_avatar_bytes() -> bytes | None:
    if LOCAL_AVATAR.exists():
        print(f"Using local avatar: {LOCAL_AVATAR}")
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


def image_to_ascii_and_spans(
    img: Image.Image,
    ramp: str,
    color_fn,
    cols: int = COLS,
    rows: int = ROWS,
) -> tuple[str, list[list[tuple[str, str]]]]:
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.6, percent=145, threshold=2))
    gray = ImageEnhance.Contrast(gray).enhance(1.3)
    resized_gray = gray.resize((cols, rows), Image.Resampling.LANCZOS)

    rgb = ImageEnhance.Color(img.convert("RGB")).enhance(1.25)
    resized_rgb = rgb.resize((cols, rows), Image.Resampling.LANCZOS)

    plain_lines = []
    lines_runs = []
    n = len(ramp) - 1

    for y in range(rows):
        row_chars = []
        row_colors = []
        for x in range(cols):
            glum = resized_gray.getpixel((x, y))
            char = ramp[round((glum / 255.0) * n)]
            r, g, b = resized_rgb.getpixel((x, y))
            col = color_fn(r, g, b)
            row_chars.append(char)
            row_colors.append(col)

        plain_lines.append("".join(row_chars))

        # Run-length encode consecutive matching colors
        runs: list[tuple[str, str]] = []
        cur_col = row_colors[0]
        cur_text = [row_chars[0]]
        for c, col in zip(row_chars[1:], row_colors[1:]):
            if col == cur_col:
                cur_text.append(c)
            else:
                runs.append(("".join(cur_text), cur_col))
                cur_col = col
                cur_text = [c]
        runs.append(("".join(cur_text), cur_col))
        lines_runs.append(runs)

    return "\n".join(plain_lines) + "\n", lines_runs


def main() -> None:
    data = fetch_avatar_bytes()
    if not data:
        print("No avatar image available; keeping existing ASCII art files.")
        return

    img = Image.open(io.BytesIO(data))
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        bg_dark = Image.new("RGBA", rgba.size, (22, 27, 34, 255))
        bg_light = Image.new("RGBA", rgba.size, (255, 255, 255, 255))
        img_dark = Image.alpha_composite(bg_dark, rgba)
        img_light = Image.alpha_composite(bg_light, rgba)
    else:
        img_dark = img
        img_light = img

    ASSETS.mkdir(exist_ok=True)

    dark_txt, dark_spans = image_to_ascii_and_spans(img_dark, RAMP_DARK_BG, color_for_dark, COLS, ROWS)
    light_txt, light_spans = image_to_ascii_and_spans(img_light, RAMP_LIGHT_BG, color_for_light, COLS, ROWS)

    ASCII_DARK_OUT.write_text(dark_txt, encoding="utf-8")
    ASCII_LIGHT_OUT.write_text(light_txt, encoding="utf-8")
    ASCII_DARK_JSON.write_text(json.dumps(dark_spans), encoding="utf-8")
    ASCII_LIGHT_JSON.write_text(json.dumps(light_spans), encoding="utf-8")

    dark_span_count = sum(len(r) for r in dark_spans)
    light_span_count = sum(len(r) for r in light_spans)
    print(f"Wrote {ASCII_DARK_OUT.name} and {ASCII_DARK_JSON.name} ({dark_span_count} color spans)")
    print(f"Wrote {ASCII_LIGHT_OUT.name} and {ASCII_LIGHT_JSON.name} ({light_span_count} color spans)")


if __name__ == "__main__":
    main()
