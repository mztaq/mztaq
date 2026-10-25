#!/usr/bin/env python3
"""Generate a GitHub-safe, animated ASCII profile from public data.

The source photograph is used locally once to make assets/portrait.txt. It is
never committed to GitHub. Subsequent runs only need Python's stdlib.
"""

from __future__ import annotations

import argparse
from collections import Counter, defaultdict
from datetime import date, timedelta
from html.parser import HTMLParser
import json
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
    req = urllib.request.Request(
        url,
        headers={"User-Agent": "mztaq-ascii-profile/1.0", "Accept": "application/vnd.github+json"},
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

    gray = ImageOps.autocontrast(ImageOps.grayscale(cropped), cutoff=3)
    gray = gray.filter(ImageFilter.UnsharpMask(radius=2, percent=160))
    gray = gray.resize((82, 70), Image.Resampling.LANCZOS)
    mask = mask.resize((82, 70), Image.Resampling.LANCZOS)
    ramp = " .:-=+*#%@"
    lines = []
    for y in range(gray.height):
        line = ""
        for x in range(gray.width):
            brightness = gray.getpixel((x, y)) * mask.getpixel((x, y)) / 255
            line += ramp[min(len(ramp) - 1, int(brightness / 256 * len(ramp)))]
        lines.append(line.rstrip())
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")


def visual_lines(days, langs):
    total = sum(x["count"] for x in days.values())
    chronological = sorted(days)
    first = date.fromisoformat(chronological[0])
    # GitHub's public calendar starts on Sunday.
    week_start = first - timedelta(days=(first.weekday() + 1) % 7)
    weeks = []
    for w in range(53):
        start = week_start + timedelta(days=7 * w)
        weeks.append([days.get((start + timedelta(days=d)).isoformat()) for d in range(7)])
    levels = ".:+#@"
    heatmap = []
    for weekday in range(7):
        letters = "".join(levels[(week[weekday] or {"level": 0})["level"]] for week in weeks)
        heatmap.append("  " + "SMTWTFS"[weekday] + "  " + letters)

    weekly = [sum((item or {"count": 0})["count"] for item in week) for week in weeks]
    peak = max(weekly, default=1) or 1
    trend_ramp = "._-:=+*#%@"
    spark = "".join(trend_ramp[round(w / peak * (len(trend_ramp) - 1))] for w in weekly)
    lang_total = sum(langs.values()) or 1
    language_lines = []
    for language, nbytes in sorted(langs.items(), key=lambda item: -item[1])[:6]:
        ratio = nbytes / lang_total
        length = round(20 * ratio)
        language_lines.append(f"  {language[:12]:<12} [{'#' * length}{'.' * (20 - length)}] {ratio * 100:5.1f}%")
    if not language_lines:
        language_lines = ["  No public language data yet."]

    content = []
    def add(txt, color=FG, fontsize=17, gap=28):
        content.append((txt, color, fontsize, gap))

    add("MUSTAQIM.", FG, 32, 44)
    add("student developer  /  automation  /  systems", MUTED, 16, 44)
    add(f"{total:,} contributions in the last year", RED, 25, 36)
    add("  " + spark, FG, 18, 48)
    add("$ whoami", RED, 18, 34)
    add("  I build things I want to use, then keep improving them.")
    add("  Based in Qatar. Roots in Bangladesh.")
    add("  Currently working on Pico with my team.", FG, 17, 48)

    add("$ stack --list", RED, 18, 34)
    add("  Python  Rust  JavaScript  HTML  CSS", FG)
    add("  Linux  Docker  Cloudflare  n8n  FastAPI  Git", FG, 17, 48)

    add("$ ls projects/", RED, 18, 34)
    add("  pico/               interactive computer science tools")
    add("  meta-strip/         file metadata inspector and cleaner")
    add("  newton-competition/ student competition website", FG, 17, 48)

    add("$ languages --public-repos", RED, 18, 36)
    for language_line in language_lines:
        add(language_line, FG, 15, 26)
    content[-1] = (*content[-1][:3], 46)

    add("$ contributions --last-year", RED, 18, 34)
    for line in heatmap:
        add(line, MUTED if line.strip().startswith("S") else FG, 14, 23)
    add("  low . : + # @ high", MUTED, 14, 44)
    add("$ updated daily from public GitHub data", MUTED, 15, 30)
    return content


def render_svg(portrait, content, static=False):
    width = 850
    y = 58
    lines = []
    count = 0

    def typed(txt, x, ypos, font_size, color, begin, duration, char_width=0.62):
        nonlocal count
        count += 1
        rect_width = max(1, len(txt) * font_size * char_width + 12)
        clip = f"reveal{count}"
        return (
            f'<clipPath id="{clip}"><rect x="{x}" y="{ypos-font_size*1.2:.1f}" width="{rect_width if static else 0:.1f}" height="{font_size*1.65:.1f}">'
            + ('' if static else f'<animate attributeName="width" from="0" to="{rect_width:.1f}" begin="{begin:.2f}s" dur="{duration:.2f}s" fill="freeze"/>')
            + '</rect></clipPath>'
            f'<text x="{x}" y="{ypos:.1f}" font-family="Courier New, monospace" font-size="{font_size}" '
            f'fill="{color}" xml:space="preserve" clip-path="url(#{clip})">{escape(txt)}</text>'
        )

    for i, portrait_line in enumerate(portrait):
        lines.append(typed(portrait_line, 174, y + i * 8.3, 10.4, FG, i * 0.045, 0.42))
    y += len(portrait) * 8.3 + 42
    clock = len(portrait) * 0.045 + 0.4
    for txt, color, fontsize, gap in content:
        duration = min(1.6, max(0.28, len(txt) * 0.013))
        x = 76 if fontsize > 20 or txt.startswith("$") else 92
        lines.append(typed(txt, x, y, fontsize, color, clock, duration))
        y += gap
        clock += max(0.26, duration * 0.68)

    height = round(y + 32)
    border = f'<rect x="1" y="1" width="{width-2}" height="{height-2}" rx="12" fill="{BG}" stroke="#29323D" stroke-width="2"/>'
    bar = f'<text x="76" y="34" fill="{MUTED}" font-family="Courier New,monospace" font-size="13">mztaq@github  ~  ./profile</text>'
    cursor = (
        '' if static else
        f'<rect x="{76 + len(content[-1][0]) * 9.1:.1f}" y="{y-49:.1f}" width="9" height="17" fill="{RED}" opacity="0">'
        f'<animate attributeName="opacity" values="0;1;0;1" keyTimes="0;0.01;0.51;1" dur="1s" begin="{clock:.2f}s" repeatCount="indefinite"/>'
        '</rect>'
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">\n'
        f'<title>Mustaqim — animated ASCII GitHub profile</title><desc>Portrait and profile sections typing in sequence. '
        'Stats generated from public repositories and contribution activity.</desc>\n'
        f'{border}{bar}\n' + "\n".join(lines) + cursor + "\n</svg>\n"
    )


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
    svg = render_svg(portrait, visual_lines(data["days"], data["languages"]), static=args.static_preview)
    target = ASSETS / ("profile-preview.svg" if args.static_preview else "profile.svg")
    target.write_text(svg, encoding="utf-8")
    print(f"Created {target.relative_to(ROOT)} ({len(svg):,} characters)")


if __name__ == "__main__":
    main()
