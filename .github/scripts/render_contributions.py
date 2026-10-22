#!/usr/bin/env python3
"""Render GitHub's public contribution calendar into theme-aware SVGs.

The hosted activity-graph service this profile used to embed is offline.
This script reads the same contribution calendar GitHub shows on the profile
and writes a light and a dark SVG into assets/.
"""

from __future__ import annotations

import html
import re
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

USERNAME = "ganttmeredith"
CONTRIBUTIONS_URL = f"https://github.com/users/{USERNAME}/contributions"
ROOT = Path(__file__).resolve().parents[2]
LIGHT_PATH = ROOT / "assets" / "github-contributions.svg"
DARK_PATH = ROOT / "assets" / "github-contributions-dark.svg"
README_PATH = ROOT / "README.md"

CELL = 11
GAP = 3
STEP = CELL + GAP
LEFT = 32
TOP = 46
RIGHT_PAD = 18
LEGEND_GAP = 18

THEMES = {
    "light": {
        "title": "#1f2328",
        "label": "#656d76",
        "levels": ("#ebedf0", "#9be9a8", "#40c463", "#30a14e", "#216e39"),
    },
    "dark": {
        "title": "#e6edf3",
        "label": "#8b949e",
        "levels": ("#161b22", "#0e4429", "#006d32", "#26a641", "#39d353"),
    },
}

FONT = "-apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif"
WEEKDAYS = {1: "Mon", 3: "Wed", 5: "Fri"}
MONTHS = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")


def fetch_calendar() -> str:
    request = urllib.request.Request(
        CONTRIBUTIONS_URL,
        headers={
            "User-Agent": "Mozilla/5.0 (compatible; contribution-calendar/1.0)",
            "Accept": "text/html",
        },
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        if response.status != 200:
            raise SystemExit(f"GitHub contributions page returned {response.status}")
        return response.read().decode("utf-8", "replace")


def parse_calendar(page: str) -> tuple[list[dict], str]:
    tips: dict[str, str] = {}
    for match in re.finditer(r"<tool-tip\b([^>]*)>([^<]*)</tool-tip>", page):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', match.group(1)))
        if "for" in attrs:
            tips[attrs["for"]] = " ".join(match.group(2).split())

    days: list[dict] = []
    for match in re.finditer(r"<td\b([^>]*)>", page):
        attrs = dict(re.findall(r'([\w:-]+)="([^"]*)"', match.group(1)))
        cell_id = attrs.get("id", "")
        id_match = re.fullmatch(r"contribution-day-component-(\d+)-(\d+)", cell_id)
        if "data-date" not in attrs or "data-level" not in attrs or not id_match:
            continue
        label = tips.get(cell_id, "")
        count_match = re.search(r"(\d+)\s+contribution", label)
        count = int(count_match.group(1)) if count_match else 0
        level = max(0, min(4, int(attrs["data-level"])))
        days.append(
            {
                "date": datetime.strptime(attrs["data-date"], "%Y-%m-%d"),
                "dow": int(id_match.group(1)),
                "week": int(id_match.group(2)),
                "level": level,
                "count": count,
                "label": label or f"{count} contributions on {attrs['data-date']}",
            }
        )

    if len(days) < 300:
        raise SystemExit(f"Expected a full year of days, parsed {len(days)}")

    headline = re.search(r"([\d,]+)\s+contributions\s+in the last year", page)
    total = headline.group(1) if headline else f"{sum(day['count'] for day in days):,}"
    return days, total


def month_labels(days: list[dict], week_count: int) -> list[tuple[int, str]]:
    """Match GitHub: a month label starts on the first column whose earliest day is in that month."""
    by_week: dict[int, list[datetime]] = {}
    for day in days:
        by_week.setdefault(day["week"], []).append(day["date"])

    labels: list[tuple[int, str]] = []
    previous = None
    for week in range(week_count):
        dates = by_week.get(week)
        if not dates:
            continue
        month = min(dates).month
        if month == previous:
            continue
        labels.append((week, MONTHS[month - 1]))
        previous = month
    return labels


def render_svg(days: list[dict], total: str, theme_name: str) -> str:
    theme = THEMES[theme_name]
    week_count = max(day["week"] for day in days) + 1
    labels = month_labels(days, week_count)
    grid_width = week_count * STEP - GAP
    width = LEFT + grid_width + RIGHT_PAD
    legend_top = TOP + 7 * STEP - GAP + LEGEND_GAP
    height = legend_top + CELL + 2

    cells = []
    for day in days:
        x = LEFT + day["week"] * STEP
        y = TOP + day["dow"] * STEP
        color = theme["levels"][day["level"]]
        cells.append(
            f'<rect x="{x}" y="{y}" width="{CELL}" height="{CELL}" rx="2" fill="{color}">'
            f"<title>{html.escape(day['label'])}</title></rect>"
        )

    month_nodes = []
    for week, name in labels:
        x = LEFT + week * STEP
        month_nodes.append(
            f'<text x="{x}" y="34" fill="{theme["label"]}" font-size="10">{name}</text>'
        )

    weekday_nodes = []
    for dow, name in WEEKDAYS.items():
        y = TOP + dow * STEP + 9
        weekday_nodes.append(
            f'<text x="0" y="{y}" fill="{theme["label"]}" font-size="11">{name}</text>'
        )

    legend_squares = []
    legend_width = 15 + 28 + 5 * STEP + 32
    legend_x = width - legend_width
    legend_squares.append(
        f'<text x="{legend_x}" y="{legend_top + 9}" fill="{theme["label"]}" font-size="11">Less</text>'
    )
    for level in range(5):
        x = legend_x + 34 + level * STEP
        legend_squares.append(
            f'<rect x="{x}" y="{legend_top}" width="{CELL}" height="{CELL}" rx="2" fill="{theme["levels"][level]}"/>'
        )
    more_x = legend_x + 34 + 5 * STEP + 4
    legend_squares.append(
        f'<text x="{more_x}" y="{legend_top + 9}" fill="{theme["label"]}" font-size="11">More</text>'
    )

    start_day = min(day["date"] for day in days)
    end_day = max(day["date"] for day in days)
    start = f"{start_day:%b} {start_day.day}, {start_day:%Y}"
    end = f"{end_day:%b} {end_day.day}, {end_day:%Y}"
    title = f"{total} contributions in the last year"
    description = f"Daily GitHub contributions for {USERNAME} from {start} to {end}."

    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" role="img" aria-labelledby="title desc">\n'
        f"  <title id=\"title\">{html.escape(title)}</title>\n"
        f"  <desc id=\"desc\">{html.escape(description)}</desc>\n"
        f'  <g font-family="{FONT}">\n'
        f'    <text x="0" y="16" fill="{theme["title"]}" font-size="15" font-weight="600">{html.escape(title)}</text>\n'
        f"    {''.join(month_nodes)}\n"
        f"    {''.join(weekday_nodes)}\n"
        f"    {''.join(cells)}\n"
        f"    {''.join(legend_squares)}\n"
        f"  </g>\n"
        f"</svg>\n"
    )


def bump_readme(token: str) -> None:
    readme = README_PATH.read_text()
    updated, count = re.subn(
        r"(assets/github-contributions(?:-dark)?\.svg\?v=)\w+",
        rf"\g<1>{token}",
        readme,
    )
    if count and updated != readme:
        README_PATH.write_text(updated)


def main() -> None:
    days, total = parse_calendar(fetch_calendar())
    light = render_svg(days, total, "light")
    dark = render_svg(days, total, "dark")
    changed = LIGHT_PATH.read_text() != light if LIGHT_PATH.exists() else True
    changed = changed or (DARK_PATH.read_text() != dark if DARK_PATH.exists() else True)
    active = sum(1 for day in days if day["count"])
    counted = sum(day["count"] for day in days)
    first = min(day["date"] for day in days).date()
    last = max(day["date"] for day in days).date()
    print(f"{total} headline, {counted} counted, {active} active days, {first} to {last}, {len(days)} cells")
    if not changed:
        print("Calendar is already current")
        return
    LIGHT_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIGHT_PATH.write_text(light)
    DARK_PATH.write_text(dark)
    bump_readme(datetime.now(timezone.utc).strftime("%Y%m%d%H%M"))
    print(f"Wrote {LIGHT_PATH.name} and {DARK_PATH.name}")


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"Failed to render contribution calendar: {exc}", file=sys.stderr)
        raise
