"""Convert the GitHub profile picture into ASCII portraits for the profile card.

Writes assets/ascii-art.txt (dark theme) and assets/ascii-art-light.txt
(light theme). The live GitHub avatar is preferred so a new profile picture
propagates on the next run; the committed assets/avatar.png is the offline
fallback. Near-white studio backdrop is blanked so the face reads as a
silhouette instead of drowning in dense glyphs.

Usage:
    python tools/build_ascii.py
"""

from __future__ import annotations

import io
import json
import os
import urllib.request
from pathlib import Path

from PIL import Image, ImageEnhance, ImageFilter, ImageOps

ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
STATS_SRC = ROOT / "cache" / "stats.json"
LOCAL_AVATAR = ASSETS / "avatar.png"
OUTPUTS = {
    "dark": ASSETS / "ascii-art.txt",
    "light": ASSETS / "ascii-art-light.txt",
}

LOGIN = os.environ.get("GH_LOGIN", "oferchen")

COLS = 87
ROWS = 47

# Pixels brighter than this on every channel are treated as backdrop.
BACKDROP_MIN = 232

# Dense-to-sparse glyph ramp for a light background; reversed for dark.
RAMP_LIGHT_BG = "$@B%8&WM#*oahkbdpqwmZO0QLCJUYXzcvunxrjft/\\|()1{}[]?-_+~<>i!lI;:,\"^`'."
RAMPS = {"light": RAMP_LIGHT_BG, "dark": RAMP_LIGHT_BG[::-1]}
COMPOSITE_BG = {"dark": (13, 17, 23, 255), "light": (255, 255, 255, 255)}


def avatar_urls() -> list[str]:
    urls = []
    if STATS_SRC.exists():
        try:
            url = json.loads(STATS_SRC.read_text(encoding="utf-8")).get("avatar_url")
        except json.JSONDecodeError:
            url = None
        if url:
            urls.append(url)
    urls.append(f"https://github.com/{LOGIN}.png?size=460")
    return urls


def fetch_avatar_bytes() -> bytes | None:
    for url in avatar_urls():
        try:
            print(f"Downloading profile avatar from {url} ...")
            req = urllib.request.Request(url, headers={"User-Agent": "profile-builder"})
            with urllib.request.urlopen(req, timeout=20) as resp:
                data = resp.read()
        except OSError as exc:
            print(f"  warning: could not download {url}: {exc}")
            continue
        if data:
            ASSETS.mkdir(exist_ok=True)
            LOCAL_AVATAR.write_bytes(data)
            return data

    if LOCAL_AVATAR.exists():
        print(f"Using local avatar: {LOCAL_AVATAR}")
        return LOCAL_AVATAR.read_bytes()
    return None


def flatten(img: Image.Image, theme: str) -> Image.Image:
    """Composite transparency onto the theme background; return RGB."""
    if img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info):
        rgba = img.convert("RGBA")
        return Image.alpha_composite(Image.new("RGBA", rgba.size, COMPOSITE_BG[theme]), rgba).convert("RGB")
    return img.convert("RGB")


def to_ascii(img: Image.Image, ramp: str, cols: int = COLS, rows: int = ROWS) -> str:
    gray = ImageOps.autocontrast(img.convert("L"), cutoff=1)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=1.6, percent=145, threshold=2))
    gray = ImageEnhance.Contrast(gray).enhance(1.3).resize((cols, rows), Image.Resampling.LANCZOS)
    rgb = img.resize((cols, rows), Image.Resampling.LANCZOS)

    n = len(ramp) - 1
    lines = []
    for y in range(rows):
        row = []
        for x in range(cols):
            if min(rgb.getpixel((x, y))) > BACKDROP_MIN:
                row.append(" ")
            else:
                row.append(ramp[round(gray.getpixel((x, y)) / 255 * n)])
        lines.append("".join(row).rstrip())
    return "\n".join(lines) + "\n"


def main() -> None:
    data = fetch_avatar_bytes()
    if not data:
        print("No avatar image available; keeping existing ASCII art files.")
        return

    img = Image.open(io.BytesIO(data))
    ASSETS.mkdir(exist_ok=True)
    for theme, out in OUTPUTS.items():
        out.write_text(to_ascii(flatten(img, theme), RAMPS[theme]), encoding="utf-8")
        print(f"Wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
