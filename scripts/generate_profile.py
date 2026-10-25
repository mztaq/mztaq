#!/usr/bin/env python3
"""Generate an animated ASCII portrait and ordinary GitHub stats SVGs.

The source photograph is used locally once to make assets/portrait.txt. It is
never committed to GitHub. Subsequent runs only need Python's stdlib.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
from html.parser import HTMLParser
import json
import os
from pathlib import Path
import re
import urllib.request
from xml.sax.saxutils import escape


ROOT = Path(__file__).resolve().parent.parent
ASSETS = ROOT / "assets"
USERNAME = "mztaq"
BG = "#0D1117"
FG = "#CDD9E5"
MUTED = "#8692A0"
RED = "#E36366"


def request(url: str):
    headers = {"User-Agent": "mztaq-ascii-profile/1.0", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token and url.startswith("https://api.github.com/"):
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(
        url,
        headers=headers,
    )
    with urllib.request.urlopen(req, timeout=35) as resp:
        return resp.read()


class ContributionParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.by_id: dict[str, dict] = {}
        self.tip_id = None
        self.tip_text = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "td" and "ContributionCalendar-day" in a.get("class", ""):
            if a.get("data-date"):
                self.by_id[a.get("id", "")] = {
                    "date": a["data-date"],
                    "level": int(a.get("data-level", "0")),
                    "count": 0,
                }
        if tag == "tool-tip" and a.get("for") in self.by_id:
            self.tip_id = a["for"]
            self.tip_text = []

    def handle_data(self, data):
        if self.tip_id:
            self.tip_text.append(data)

    def handle_endtag(self, tag):
        if tag == "tool-tip" and self.tip_id:
            txt = "".join(self.tip_text)
            m = re.search(r"([\d,]+) contributions?", txt)
            if m:
                self.by_id[self.tip_id]["count"] = int(m.group(1).replace(",", ""))
            self.tip_id = None


def fetch_calendar():
    parser = ContributionParser()
    parser.feed(request(f"https://github.com/users/{USERNAME}/contributions").decode("utf-8"))
    days = {r["date"]: r for r in parser.by_id.values()}
    if len(days) < 350:
        raise RuntimeError(f"GitHub returned only {len(days)} contribution days")
    return days


def fetch_languages():
    repos = json.loads(request(f"https://api.github.com/users/{USERNAME}/repos?per_page=100&type=owner"))
    totals = Counter()
    for repo in repos:
        if repo.get("fork") or repo.get("private") or repo["name"] == USERNAME:
            continue
        langs = json.loads(request(repo["languages_url"]))
        totals.update({key: int(value) for key, value in langs.items()})
    return dict(totals)


def make_portrait(photo: Path, out: Path):
    from PIL import Image, ImageDraw, ImageFilter, ImageOps

    photo_img = Image.open(photo).convert("RGB")
    # Coordinates belong to the user's supplied 1152x1536 selfie.
    scale_x = photo_img.width / 1152
    scale_y = photo_img.height / 1536
    box = tuple(round(v * (scale_x if i % 2 == 0 else scale_y)) for i, v in enumerate((290, 180, 945, 1020)))
    cropped = photo_img.crop(box)
    mask = Image.new("L", cropped.size, 0)
    polygon = [
        (110, 210), (150, 105), (240, 35), (365, 10), (495, 64),
        (570, 150), (600, 265), (566, 443), (486, 685), (373, 820),
        (220, 820), (95, 650), (40, 480), (25, 320),
    ]
    draw = ImageDraw.Draw(mask)
    draw.polygon([(int(x * scale_x), int(y * scale_y)) for x, y in polygon], fill=255)
    mask = mask.filter(ImageFilter.GaussianBlur(10 * scale_x))

    gray = ImageOps.autocontrast(ImageOps.grayscale(cropped), cutoff=2)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=2.5, percent=190))
    # Preserve thin glasses rims after reduction to character cells.
    gray = Image.blend(gray, gray.filter(ImageFilter.MinFilter(7)), 0.36)
    gray = gray.resize((96, 76), Image.Resampling.LANCZOS)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    mask = mask.resize((96, 76), Image.Resampling.LANCZOS)
    ramp = " .:-=+*#%@"
    lines = []
    for y in range(gray.height):
        line = ""
        for x in range(gray.width):
            # Darker features become denser characters. Thin frames and facial
            # edges get a slight extra weight, while the background stays blank.
            darkness = (1 - gray.getpixel((x, y)) / 255) ** 1.25
            edge_detail = edges.getpixel((x, y)) / 255
            density = min(1, darkness * 0.86 + edge_detail * 0.20)
            density *= mask.getpixel((x, y)) / 255
            line += ramp[min(len(ramp) - 1, int(density * len(ramp)))]
        lines.append(line.rstrip())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def calendar_weeks(days):
    first = date.fromisoformat(min(days))
    start = first - timedelta(days=(first.weekday() + 1) % 7)
    return [
        [days.get((start + timedelta(days=week * 7 + weekday)).isoformat()) for weekday in range(7)]
        for week in range(53)
    ]


def svg_shell(width, height, title, inner):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
            f'viewBox="0 0 {width} {height}"><title>{escape(title)}</title>'
            + inner + '</svg>\n')


def render_face(lines, static=False):
    """Only the portrait types in. The rest of the README stays regular Markdown."""
    char_width, line_height, pad = 5.7, 9.7, 15
    width = round(max(map(len, lines)) * char_width + 2 * pad)
    height = round(len(lines) * line_height + 2 * pad)
    parts = [
        '<style>.ink{fill:#656d76}@media(prefers-color-scheme:dark){.ink{fill:#c9d1d9}}</style>'
    ]
    for i, line in enumerate(lines):
        ypos = pad + i * line_height
        length = max(1, len(line) * char_width)
        reveal = f'<animate attributeName="width" from="0" to="{length:.1f}" begin="{i * .068:.2f}s" dur=".32s" fill="freeze"/>'
        parts.append(
            f'<clipPath id="row{i}"><rect x="{pad}" y="{ypos:.1f}" width="{length if static else 0:.1f}" height="{line_height:.1f}">'
            + ('' if static else reveal) + '</rect></clipPath>'
        )
        parts.append(
            f'<text class="ink" x="{pad}" y="{ypos + line_height * .79:.1f}" '
            f'font-family="Courier New,monospace" font-size="9.5" xml:space="preserve" '
            f'clip-path="url(#row{i})">{escape(line)}</text>'
        )
    return svg_shell(width, height, 'Animated ASCII portrait of Mustaqim', ''.join(parts))


def render_stats(days):
    weeks = calendar_weeks(days)
    counts = [sum((d or {"count": 0})["count"] for d in w) for w in weeks]
    peak = max(counts) or 1
    total = sum(d["count"] for d in days.values())
    x0, x1, y0, y1 = 34, 746, 178, 87
    points = [(x0 + i * (x1 - x0) / (len(counts) - 1), y0 - val / peak * (y0-y1)) for i, val in enumerate(counts)]
    line = ' '.join(f'{x:.1f},{y:.1f}' for x, y in points)
    area = f'{x0},{y0} {line} {x1},{y0}'
    parts = [
        f'<rect x="1" y="1" width="778" height="218" rx="8" fill="{BG}" stroke="#2B313A"/>',
        f'<text x="34" y="59" font-size="36" font-family="monospace" fill="{FG}">{total:,}</text>',
        f'<text x="150" y="56" font-size="13" font-family="monospace" fill="{MUTED}">contributions in the last year</text>',
        f'<line x1="34" y1="178" x2="746" y2="178" stroke="#36404A"/>',
        f'<polygon points="{area}" fill="{RED}" opacity="0.13"/>',
        f'<polyline points="{line}" fill="none" stroke="{RED}" stroke-width="2.2" stroke-linejoin="round"/>',
        f'<text x="34" y="201" font-size="11" font-family="monospace" fill="{MUTED}">52-week activity</text>',
        f'<text x="746" y="201" text-anchor="end" font-size="11" font-family="monospace" fill="{MUTED}">updated daily</text>',
    ]
    return svg_shell(780, 220, 'GitHub contribution activity', ''.join(parts))


def render_languages(langs):
    ranked = sorted(langs.items(), key=lambda item: (-item[1], item[0]))[:6]
    total = sum(langs.values()) or 1
    height = 86 + max(1, len(ranked)) * 36
    parts = [
        f'<rect x="1" y="1" width="778" height="{height-2}" rx="8" fill="{BG}" stroke="#2B313A"/>',
        f'<text x="34" y="36" font-family="monospace" font-size="17" fill="{FG}">Languages in public repositories</text>',
        f'<text x="34" y="56" font-family="monospace" font-size="11" fill="{MUTED}">Measured by GitHub language bytes, not coding hours</text>',
    ]
    for i, (name, nbytes) in enumerate(ranked):
        ypos = 80 + i * 36
        ratio = nbytes / total
        parts.extend([
            f'<text x="34" y="{ypos+13}" font-family="monospace" font-size="13" fill="{FG}">{escape(name)}</text>',
            f'<rect x="198" y="{ypos+1}" width="492" height="13" fill="#29313A" rx="2"/>',
            f'<rect x="198" y="{ypos+1}" width="{max(1,492*ratio):.1f}" height="13" fill="{RED}" rx="2"/>',
            f'<text x="746" y="{ypos+13}" text-anchor="end" font-family="monospace" font-size="13" fill="{FG}">{ratio*100:.1f}%</text>',
        ])
    return svg_shell(780, height, 'Programming language usage', ''.join(parts))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--portrait-photo", type=Path)
    parser.add_argument("--offline", action="store_true")
    parser.add_argument("--static-preview", action="store_true")
    args = parser.parse_args()
    ASSETS.mkdir(parents=True, exist_ok=True)
    if args.portrait_photo:
        make_portrait(args.portrait_photo, ASSETS / "portrait.txt")

    data_file = ASSETS / "stats.json"
    if args.offline:
        data = json.loads(data_file.read_text(encoding="utf-8"))
    else:
        try:
            data = {"days": fetch_calendar(), "languages": fetch_languages()}
            data_file.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        except Exception as err:
            if not data_file.exists():
                raise
            print(f"Data fetch failed, rendering cached public data: {err}")
            data = json.loads(data_file.read_text(encoding="utf-8"))

    portrait = (ASSETS / "portrait.txt").read_text(encoding="utf-8").splitlines()
    target = ASSETS / ("face-preview.svg" if args.static_preview else "face.svg")
    target.write_text(render_face(portrait, static=args.static_preview), encoding="utf-8")
    if not args.static_preview:
        (ASSETS / "stats.svg").write_text(render_stats(data["days"]), encoding="utf-8")
        (ASSETS / "languages.svg").write_text(render_languages(data["languages"]), encoding="utf-8")
    print(f"Created {target.relative_to(ROOT)}")


if __name__ == "__main__":
    main()
