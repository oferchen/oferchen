"""Convert the GitHub user's profile picture into 87x47 ASCII art portraits
for both Dark Mode (assets/ascii-art.txt) and Light Mode (assets/ascii-art-light.txt).

Matches the exact 0.54 cell aspect ratio expected by build_card.py (87 cols x 47 rows)[cite: 6].
If `assets/avatar.png` is present locally, it uses that image; otherwise it downloads
the live GitHub profile avatar via https://github.com/<login>.png (or avatar_url from cache/stats.json).

Usage:
    python tools/build_ascii.py
"""

from __future__ import annotations

import io
import json
import os
from pathlib import Path
from PIL import Image, ImageOps, ImageEnhance

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
STATS_SRC = ROOT / "cache" / "stats.json"
LOCAL_AVATAR = ASSETS / "avatar.png"
ASCII_DARK_OUT = ASSETS / "ascii-art.txt"
ASCII_LIGHT_OUT = ASSETS / "ascii-art-light.txt"

LOGIN = os.environ.get("GH_LOGIN", "oferchen")

# 87 columns x 47 rows reproduces the exact 0.54 cell aspect ratio (47 / 87 = 0.5402)
# documented in build_card.py so a square avatar renders with zero vertical distortion[cite: 6].
COLS = 87
ROWS = 47

# 69-level high-detail character ramp (no space character so load_art() never trims outer columns)
RAMP_LIGHT_BG = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'.`"
RAMP_DARK_BG = RAMP_LIGHT_BG[::-1]


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


def image_to_ascii(img: Image.Image, ramp: str, cols: int = COLS, rows: int = ROWS) -> str:
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    gray = ImageEnhance.Contrast(gray).enhance(1.25)
    resized = gray.resize((cols, rows), Image.Resampling.LANCZOS)

    pixels = list(resized.getdata())
    n = len(ramp) - 1
    lines = []
    for r in range(rows):
        row_pixels = pixels[r * cols : (r + 1) * cols]
        line = "".join(ramp[round((px / 255.0) * n)] for px in row_pixels)
        lines.append(line)
    return "\n".join(lines) + "\n"


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
    dark_txt = image_to_ascii(img_dark, RAMP_DARK_BG, COLS, ROWS)
    light_txt = image_to_ascii(img_light, RAMP_LIGHT_BG, COLS, ROWS)

    ASCII_DARK_OUT.write_text(dark_txt, encoding="utf-8")
    ASCII_LIGHT_OUT.write_text(light_txt, encoding="utf-8")
    print(f"Wrote {ASCII_DARK_OUT.name} and {ASCII_LIGHT_OUT.name} ({COLS}x{ROWS} portrait grid)")


if __name__ == "__main__":
    main()
