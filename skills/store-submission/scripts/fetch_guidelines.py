#!/usr/bin/env python3
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Fetch the official App Store and Google Play rules and report what changed.

Reads every page in references/sources.json, saves each as plain text, cuts it
into sections and compares their hashes with references/baseline.json, the
state the skill's reference files were last checked against. A changed or new
section means the live text overrides the vendored reference for that rule.

Also pulls the facts a scan needs to be current: Play's target API levels, the
upcoming Play policy deadlines and recent Apple developer news about review,
privacy or SDK requirements.

Usage:
    uv run fetch_guidelines.py --out DIR                      # fetch, compare, write DIR/report.json
    uv run fetch_guidelines.py --out DIR --update-baseline    # also accept the live text as the new baseline
"""

from __future__ import annotations

import argparse
import datetime as dt
import email.utils
import hashlib
import html
import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from html.parser import HTMLParser
from pathlib import Path

SKILL = Path(__file__).resolve().parent.parent
SOURCES = SKILL / "references" / "sources.json"
BASELINE = SKILL / "references" / "baseline.json"
USER_AGENT = "store-submission-skill/1.0 (guideline check)"
SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "header", "footer", "form", "button", "template"}
BLOCK_TAGS = {"p", "li", "td", "th", "tr", "div", "section", "article", "dd", "dt", "br", "table", "ul", "ol"}
HEADINGS = {"h1", "h2", "h3", "h4"}
APPLE_ID = re.compile(r"^\d+(\.\d+)*$")
# Help-centre chrome that follows the article body
END_MARKERS = (
    "Was this helpful?",
    "Need more help?",
    "Try these next steps",
    "Try your keywords on Google Web Search",
    "Developer Footer",
    "Related content",
)
NEWS_TOPICS = re.compile(
    r"review guideline|app review|requirement|privacy|sdk|age rating|deadline|upload|xcode|tracking|account deletion",
    re.I,
)
NEWS_WINDOW_DAYS = 180


class _TextParser(HTMLParser):
    """Turns HTML into blocks of (section marker, text), dropping page chrome."""

    def __init__(self, split: str):
        super().__init__(convert_charrefs=True)
        self.split = split
        self.skip_depth = 0
        self.heading: str | None = None
        self.heading_text: list[str] = []
        self.blocks: list[tuple[str | None, str]] = []  # (new-section key or None, text)
        self.buf: list[str] = []

    def _flush(self) -> None:
        text = re.sub(r"\s+", " ", "".join(self.buf)).strip()
        if text:
            self.blocks.append((None, text))
        self.buf = []

    def handle_starttag(self, tag, attrs):
        if tag in SKIP_TAGS:
            self.skip_depth += 1
            return
        if self.skip_depth:
            return
        if tag in BLOCK_TAGS or tag in HEADINGS:
            self._flush()
        attr_id = dict(attrs).get("id") or ""
        if self.split == "apple-ids" and APPLE_ID.match(attr_id):
            self.blocks.append((attr_id, ""))
        if tag in HEADINGS:
            self.heading = tag
            self.heading_text = []

    def handle_endtag(self, tag):
        if tag in SKIP_TAGS:
            self.skip_depth = max(0, self.skip_depth - 1)
            return
        if self.skip_depth:
            return
        if tag in HEADINGS and self.heading == tag:
            text = re.sub(r"\s+", " ", "".join(self.heading_text)).strip()
            self.heading = None
            if text:
                key = text if self.split == "headings" else None
                self.blocks.append((key, f"{'#' * int(tag[1])} {text}"))
            return
        if tag in BLOCK_TAGS:
            self._flush()

    def handle_data(self, data):
        if self.skip_depth:
            return
        if self.heading:
            self.heading_text.append(data)
        else:
            self.buf.append(data)


def fetch(url: str) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept-Language": "en"})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode(resp.headers.get_content_charset() or "utf-8", errors="replace")


def html_sections(raw: str, split: str) -> tuple[str, dict[str, str]]:
    """Return the page as text plus its sections keyed by guideline id or heading."""
    parser = _TextParser(split)
    parser.feed(raw)
    parser._flush()
    blocks = parser.blocks
    # The article starts at the first h1 and ends at the help-centre chrome after it
    start = next((i for i, (_, t) in enumerate(blocks) if t.startswith("# ")), 0)
    blocks = blocks[start:]
    end = next(
        (i for i, (_, t) in enumerate(blocks) if any(t.lstrip("# ").startswith(m) for m in END_MARKERS)), len(blocks)
    )
    blocks = blocks[:end]

    sections: dict[str, list[str]] = {}
    current = "(intro)"
    lines: list[str] = []
    for key, text in blocks:
        if key is not None:
            current = key
            sections.setdefault(current, [])
        if text:
            sections.setdefault(current, []).append(text)
            lines.append(text)
    return "\n\n".join(lines), {k: "\n".join(v) for k, v in sections.items() if v}


def rss_sections(raw: str) -> tuple[str, dict[str, str]]:
    """Recent news items about review, privacy or SDK rules, newest first."""
    root = ET.fromstring(raw)
    cutoff = dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=NEWS_WINDOW_DAYS)
    sections: dict[str, str] = {}
    lines = []
    for item in root.iter("item"):
        title = (item.findtext("title") or "").strip()
        link = (item.findtext("link") or "").strip()
        when = item.findtext("pubDate")
        published = email.utils.parsedate_to_datetime(when) if when else None
        if published and published < cutoff:
            continue
        body = re.sub(r"<[^>]+>", " ", html.unescape(item.findtext("description") or ""))
        body = re.sub(r"\s+", " ", body).strip()
        if not NEWS_TOPICS.search(title + " " + body[:400]):
            continue
        date = published.date().isoformat() if published else "?"
        sections[f"{date} {title}"] = f"{link}\n{body}"
        lines.append(f"## {date} {title}\n{link}\n\n{body}")
    return "\n\n".join(lines), sections


def digest(text: str) -> str:
    # Long numbers are per-request tokens in Google's page chrome, not content
    text = re.sub(r"\b\d{12,}\b", "", text)
    return hashlib.sha256(re.sub(r"\s+", " ", text).strip().encode()).hexdigest()[:16]


def extract_facts(texts: dict[str, str]) -> dict:
    facts: dict = {}
    sdk = texts.get("play-target-sdk", "")
    m = re.search(r"New apps and app updates must target Android [\d.]+ \(API level (\d+)\)", sdk)
    if m:
        facts["play_target_sdk_new"] = int(m.group(1))
        start = re.search(r"Starting ([A-Z][a-z]+ \d{1,2},? \d{4})[^.]{0,40}New apps and app updates must target", sdk)
        if start:
            facts["play_target_sdk_new_from"] = start.group(1)
    m = re.search(r"Existing apps must target Android [\d.]+ \(API level (\d+)\)", sdk)
    if m:
        facts["play_target_sdk_existing"] = int(m.group(1))

    deadlines = texts.get("play-policy-deadlines", "")
    today = dt.date.today().isoformat()
    upcoming = []
    for m in re.finditer(r"(\d{4}-\d{2}-\d{2}) (.{20,400}?)(?= \d{4}-\d{2}-\d{2} |$)", deadlines.replace("\n", " ")):
        if m.group(1) >= today:
            upcoming.append({"deadline": m.group(1), "change": re.sub(r"\s+(Announced)?\s*$", "", m.group(2)).strip()})
    if upcoming:
        facts["play_upcoming_deadlines"] = upcoming

    guidelines = texts.get("apple-review-guidelines", "")
    m = re.search(r"Last Updated: ([A-Z][a-z]+ \d{1,2}, \d{4})", guidelines)
    if m:
        facts["apple_guidelines_last_updated"] = m.group(1)
    return facts


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", required=True, type=Path, help="directory for the page texts and report.json")
    ap.add_argument("--update-baseline", action="store_true", help="record the live sections as the new baseline")
    args = ap.parse_args()

    sources = json.loads(SOURCES.read_text())["sources"]
    baseline = json.loads(BASELINE.read_text()) if BASELINE.exists() else {"checked": None, "sections": {}}
    args.out.mkdir(parents=True, exist_ok=True)

    report: dict = {
        "fetched": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "baseline_checked": baseline.get("checked"),
        "sources": [],
    }
    texts: dict[str, str] = {}
    new_baseline: dict[str, dict[str, str]] = {}
    for src in sources:
        entry = {"id": src["id"], "store": src["store"], "title": src["title"], "url": src["url"]}
        try:
            raw = fetch(src["url"])
            text, sections = rss_sections(raw) if src["split"] == "rss" else html_sections(raw, src["split"])
        except Exception as exc:  # a page that fails is reported, never silently skipped
            entry["status"] = f"FAILED: {exc}"
            report["sources"].append(entry)
            continue
        if not sections:
            entry["status"] = "FAILED: no content extracted (page layout changed?)"
            report["sources"].append(entry)
            continue
        texts[src["id"]] = text
        path = args.out / f"{src['id']}.md"
        path.write_text(f"# {src['title']}\n\nSource: {src['url']}\n\n{text}\n")
        entry["status"] = "ok"
        entry["text_file"] = str(path)
        entry["references"] = src.get("references", [])

        hashes = {k: digest(v) for k, v in sections.items()}
        new_baseline[src["id"]] = hashes
        old = baseline["sections"].get(src["id"])
        if src["split"] == "rss":
            entry["items"] = list(sections)  # news is always listed, never diffed
        elif old is None:
            entry["changes"] = "no baseline yet"
        else:
            entry["changed"] = [k for k in hashes if k in old and old[k] != hashes[k]]
            entry["added"] = [k for k in hashes if k not in old]
            entry["removed"] = [k for k in old if k not in hashes]
        report["sources"].append(entry)

    report["facts"] = extract_facts(texts)
    (args.out / "report.json").write_text(json.dumps(report, indent=2))

    if args.update_baseline:
        failed = [s["id"] for s in report["sources"] if s["status"] != "ok"]
        if failed:
            print(f"Not updating the baseline: {', '.join(failed)} failed to fetch", file=sys.stderr)
            return 1
        BASELINE.write_text(
            json.dumps({"checked": dt.date.today().isoformat(), "sections": new_baseline}, indent=1, sort_keys=True)
            + "\n"
        )

    print_summary(report)
    return 0 if all(s["status"] == "ok" for s in report["sources"]) else 2


def print_summary(report: dict) -> None:
    print(f"Official sources fetched {report['fetched']} (references last checked {report['baseline_checked']})")
    for s in report["sources"]:
        line = f"- [{s['store']}] {s['title']}: {s['status']}"
        if s.get("changes"):
            line += f", {s['changes']}"
        for key in ("changed", "added", "removed"):
            if s.get(key):
                shown = ", ".join(s[key][:12]) + (f" and {len(s[key]) - 12} more" if len(s[key]) > 12 else "")
                line += f"\n    {key}: {shown}"
        if s.get("items"):
            line += "\n    " + "\n    ".join(s["items"][:10])
        print(line)
    if report["facts"]:
        print("Facts:")
        print(json.dumps(report["facts"], indent=2))


if __name__ == "__main__":
    sys.exit(main())
