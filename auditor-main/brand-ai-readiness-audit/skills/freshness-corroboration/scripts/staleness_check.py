#!/usr/bin/env python3
"""
staleness_check.py — Parse copyright years and dated-content strings from a
fetched page and evaluate staleness against the thresholds defined in
freshness-corroboration/SKILL.md.

Thresholds (from SKILL.md §4):
  - Copyright year 1 year behind current calendar year  → severity "medium"
  - Copyright year 2+ years behind                      → severity "high"
  - Dated content presented as current, older than 18 months → severity "high"
  - Blog/news most-recent post older than 18 months     → severity "medium"
  - Event / pricing / "coming soon" with a past date    → severity "high"

Third-party corroboration and entity-ambiguity search steps are intentionally
left as agent-driven reasoning in the SKILL.md procedure — those require
judgment, not a script.

Usage:
    python staleness_check.py <target_url> [audit_date_iso] [--rendered-text <file>]

    audit_date_iso defaults to today (UTC).

    --rendered-text <file>
        Path to a UTF-8 text file containing the visible body text extracted
        from the rendered DOM (as produced by crawl-render-audit/render_diff.py's
        `rendered_text` field). When provided, the script runs all regex checks
        against this rendered text whenever the static HTML yields no matches,
        and tags each finding with "found_in": "rendered". Findings from static
        HTML are tagged "found_in": "static". This prevents SPA sites from
        silently returning an empty findings list.

Output: JSON to stdout. Exit 0 always (errors captured in output).
"""

import sys
import json
import re
import urllib.request
import urllib.error
from datetime import date, datetime
from html.parser import HTMLParser
from typing import Any

# ── Thresholds (mirror SKILL.md §4 exactly) ─────────────────────────────────
COPYRIGHT_MEDIUM_THRESHOLD_YEARS = 1   # 1 year behind → medium
COPYRIGHT_HIGH_THRESHOLD_YEARS = 2     # 2+ years behind → high
CONTENT_STALENESS_MONTHS = 18          # 18+ months → high


# ── HTML text extractor ──────────────────────────────────────────────────────

class FullTextExtractor(HTMLParser):
    """Extract visible text (excluding script/style) from HTML."""

    SKIP_TAGS = {"script", "style", "noscript", "head"}

    def __init__(self) -> None:
        super().__init__()
        self._skip_depth = 0
        self._tag_stack: list[str] = []
        self.segments: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self._tag_stack.append(tag)
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if self._tag_stack and self._tag_stack[-1] == tag:
            self._tag_stack.pop()
        if tag in self.SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            stripped = data.strip()
            if stripped:
                self.segments.append(stripped)

    def full_text(self) -> str:
        return " ".join(self.segments)


# ── Fetch ─────────────────────────────────────────────────────────────────────

def fetch_html(url: str, timeout: int = 15) -> dict[str, Any]:
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "BrandAIReadinessAudit/1.0 (+https://github.com/brand-ai-readiness-audit)",
                "Accept": "text/html,application/xhtml+xml",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            return {"ok": True, "status": resp.status, "body": body, "error": None}
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "body": None, "error": str(exc)}
    except urllib.error.URLError as exc:
        return {"ok": False, "status": None, "body": None, "error": str(exc.reason)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "body": None, "error": str(exc)}


# ── Copyright year extraction ─────────────────────────────────────────────────

# Match © / (c) / Copyright followed by an optional range and a 4-digit year
_COPYRIGHT_RE = re.compile(
    r"(?:©|\(c\)|copyright)\s*(?:\d{4}\s*[-–—]\s*)?(\d{4})",
    re.IGNORECASE,
)


def extract_copyright_years(text: str) -> list[int]:
    """Return all copyright years found in text, deduplicated."""
    return list(dict.fromkeys(int(m.group(1)) for m in _COPYRIGHT_RE.finditer(text)))


def evaluate_copyright(years: list[int], audit_year: int, found_in: str) -> list[dict[str, Any]]:
    """
    Apply SKILL.md §4 thresholds to copyright years.
    Returns a list of finding dicts (may be empty).

    found_in: "static" | "rendered" — indicates which content source the
    copyright year was found in.
    """
    if not years:
        return []
    latest = max(years)
    behind = audit_year - latest
    if behind <= 0:
        return []
    severity = "high" if behind >= COPYRIGHT_HIGH_THRESHOLD_YEARS else "medium"
    return [
        {
            "check": "copyright_year",
            "severity": severity,
            "title": "Copyright year is stale",
            "latest_copyright_year": latest,
            "audit_year": audit_year,
            "years_behind": behind,
            "found_in": found_in,
            "evidence": (
                f"Footer copyright year {latest}; audit year {audit_year} "
                f"({behind} year(s) behind). Found in {found_in} content."
            ),
            "suggested_action": {
                "summary": "Update the copyright year in the global footer.",
                "priority": severity,
            },
        }
    ]


# ── Dated-content extraction ──────────────────────────────────────────────────

# Month names and abbreviations
_MONTHS = (
    "january|february|march|april|may|june|july|august|september|october|november|december"
    "|jan|feb|mar|apr|jun|jul|aug|sep|oct|nov|dec"
)

# Pattern: "last updated [Month] YYYY" or "as of [Month] YYYY"
_LAST_UPDATED_RE = re.compile(
    rf"(?:last\s+updated|last\s+modified|as\s+of|updated)\s*[:\-]?\s*"
    rf"(?:({_MONTHS})\s+(\d{{1,2}}),?\s+)?(\d{{4}})",
    re.IGNORECASE,
)

# Pattern: standalone year reference in common staleness phrases
_STAT_YEAR_RE = re.compile(
    r"(?:in|since|during|from|through|as\s+of)\s+(\d{4})\b",
    re.IGNORECASE,
)

# ISO date pattern YYYY-MM-DD
_ISO_DATE_RE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")

# "Month DD, YYYY" or "Month YYYY"
_MONTH_YEAR_RE = re.compile(
    rf"\b({_MONTHS})\s+(?:\d{{1,2}},?\s+)?(\d{{4}})\b",
    re.IGNORECASE,
)

_MONTH_MAP: dict[str, int] = {
    "jan": 1, "january": 1, "feb": 2, "february": 2, "mar": 3, "march": 3,
    "apr": 4, "april": 4, "may": 5, "jun": 6, "june": 6, "jul": 7, "july": 7,
    "aug": 8, "august": 8, "sep": 9, "september": 9, "oct": 10, "october": 10,
    "nov": 11, "november": 11, "dec": 12, "december": 12,
}


def _months_between(d: date, audit_date: date) -> int:
    return (audit_date.year - d.year) * 12 + (audit_date.month - d.month)


def extract_dated_content(text: str, audit_date: date) -> list[dict[str, Any]]:
    """
    Scan visible text for staleness signals (SKILL.md §4.2–4.4).
    Returns raw matches annotated with their staleness in months.
    """
    findings: list[dict[str, Any]] = []

    def _add(pattern_name: str, matched_text: str, d: date, severity: str, note: str) -> None:
        months_old = _months_between(d, audit_date)
        findings.append({
            "pattern": pattern_name,
            "matched_text": matched_text[:200],
            "parsed_date": d.isoformat(),
            "months_old": months_old,
            "severity": severity,
            "note": note,
        })

    # "Last updated" / "as of" patterns
    for m in _LAST_UPDATED_RE.finditer(text):
        year_str = m.group(3)
        month_str = m.group(1)
        try:
            year = int(year_str)
            month = _MONTH_MAP.get((month_str or "").lower(), 1)
            d = date(year, month, 1)
            months_old = _months_between(d, audit_date)
            if months_old >= CONTENT_STALENESS_MONTHS:
                _add("last_updated", m.group(0), d, "high",
                     "Time-sensitive content presented as current (last updated / as of).")
        except (ValueError, TypeError):
            pass

    # ISO dates
    for m in _ISO_DATE_RE.finditer(text):
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d > audit_date:
                continue  # future date, could be event — handle separately
            months_old = _months_between(d, audit_date)
            if months_old >= CONTENT_STALENESS_MONTHS:
                context_start = max(0, m.start() - 60)
                context = text[context_start: m.end() + 60]
                # Only flag if surrounded by framing language (not just a release note date)
                framing = re.search(
                    r"(?:current|now|today|present|latest|ongoing|active|as\s+of|last\s+updated)",
                    context, re.IGNORECASE
                )
                if framing:
                    _add("iso_date_framed_as_current", m.group(0), d, "high",
                         "ISO date found in 'current' framing context.")
        except (ValueError, TypeError):
            pass

    # Past events / pricing / "coming soon" with past dates
    future_markers = re.compile(
        r"\b(?:coming\s+soon|register\s+now|early\s+bird|opens|event\s+date|conference|webinar|deadline)\b",
        re.IGNORECASE,
    )
    for m in _ISO_DATE_RE.finditer(text):
        try:
            d = date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
            if d >= audit_date:
                continue
            context_start = max(0, m.start() - 120)
            context = text[context_start: m.end() + 120]
            if future_markers.search(context):
                _add("past_event_date", m.group(0), d, "high",
                     "Event/deadline date is in the past.")
        except (ValueError, TypeError):
            pass

    return findings


def evaluate_dated_content(raw_matches: list[dict[str, Any]], found_in: str) -> list[dict[str, Any]]:
    """Wrap raw matches into the findings contract, tagging each with found_in."""
    results = []
    seen: set[str] = set()
    for m in raw_matches:
        key = f"{m['pattern']}:{m['parsed_date']}"
        if key in seen:
            continue
        seen.add(key)
        results.append({
            "check": "dated_content",
            "severity": m["severity"],
            "title": "Time-sensitive content presented as current"
            if m["pattern"] != "past_event_date"
            else "Event or deadline date is in the past",
            "matched_text": m["matched_text"],
            "parsed_date": m["parsed_date"],
            "months_old": m["months_old"],
            "found_in": found_in,
            "evidence": (
                f"Matched '{m['matched_text']}' ({m['parsed_date']}); "
                f"{m['months_old']} months before audit date. {m['note']} "
                f"Found in {found_in} content."
            ),
            "suggested_action": {
                "summary": "Refresh or label as historical. Remove or update past event dates.",
                "priority": m["severity"],
            },
        })
    return results


# ── Blog/news recency ─────────────────────────────────────────────────────────

def extract_blog_dates(text: str) -> list[date]:
    """
    Heuristic: find dates adjacent to common blog/news framing words.
    Returns parsed dates, unsorted.
    """
    dates: list[date] = []
    blog_context_re = re.compile(
        r"(?:posted|published|updated|written|by\s+\w+\s+on|date:|news|article)\b.{0,60}"
        r"(\d{4}-\d{2}-\d{2}|\b(?:jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec)[a-z]*"
        r"\s+\d{1,2},?\s+\d{4})",
        re.IGNORECASE,
    )
    for m in blog_context_re.finditer(text):
        raw = m.group(1).strip()
        # try ISO first
        iso = re.match(r"(\d{4})-(\d{2})-(\d{2})", raw)
        if iso:
            try:
                dates.append(date(int(iso.group(1)), int(iso.group(2)), int(iso.group(3))))
                continue
            except ValueError:
                pass
        # try Month DD, YYYY
        wordy = re.match(
            rf"({_MONTHS})\s+(\d{{1,2}}),?\s+(\d{{4}})", raw, re.IGNORECASE
        )
        if wordy:
            try:
                month = _MONTH_MAP.get(wordy.group(1).lower(), 1)
                dates.append(date(int(wordy.group(3)), month, int(wordy.group(2))))
            except ValueError:
                pass
    return dates


def evaluate_blog_freshness(
    blog_dates: list[date], audit_date: date, found_in: str
) -> list[dict[str, Any]]:
    if not blog_dates:
        return []
    most_recent = max(blog_dates)
    months_old = _months_between(most_recent, audit_date)
    if months_old < CONTENT_STALENESS_MONTHS:
        return []
    return [
        {
            "check": "blog_freshness",
            "severity": "medium",
            "title": "Most recent blog/news post is older than 18 months",
            "most_recent_post_date": most_recent.isoformat(),
            "months_old": months_old,
            "found_in": found_in,
            "evidence": (
                f"Most recent blog/news date found: {most_recent.isoformat()} "
                f"({months_old} months before audit date {audit_date.isoformat()}). "
                f"Found in {found_in} content."
            ),
            "suggested_action": {
                "summary": "Publish a current update or remove the 'latest news' framing.",
                "priority": "medium",
            },
        }
    ]


# ── Core check runner ─────────────────────────────────────────────────────────

def run_checks(
    text: str, audit_date: date, audit_year: int, found_in: str
) -> tuple[list[int], list[dict[str, Any]]]:
    """
    Run all staleness checks against a single text corpus and return
    (copyright_years_found, findings_list). found_in is tagged on every finding.
    """
    copyright_years = extract_copyright_years(text)
    copyright_findings = evaluate_copyright(copyright_years, audit_year, found_in)

    raw_dated = extract_dated_content(text, audit_date)
    dated_findings = evaluate_dated_content(raw_dated, found_in)

    blog_dates = extract_blog_dates(text)
    blog_findings = evaluate_blog_freshness(blog_dates, audit_date, found_in)

    return copyright_years, copyright_findings + dated_findings + blog_findings


# ── Argument parsing ──────────────────────────────────────────────────────────

def _parse_args(argv: list[str]) -> tuple[str, str | None, str | None]:
    """
    Returns (target_url, audit_date_str_or_None, rendered_text_path_or_None).
    Accepts:
        staleness_check.py <url> [date] [--rendered-text <path>]
    """
    if len(argv) < 2:
        return ("", None, None)

    target_url = argv[1].strip()
    audit_date_str: str | None = None
    rendered_text_path: str | None = None

    i = 2
    while i < len(argv):
        if argv[i] == "--rendered-text" and i + 1 < len(argv):
            rendered_text_path = argv[i + 1]
            i += 2
        else:
            if audit_date_str is None and not argv[i].startswith("--"):
                audit_date_str = argv[i].strip()
            i += 1

    return target_url, audit_date_str, rendered_text_path


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    target_url, audit_date_str, rendered_text_path = _parse_args(sys.argv)

    if not target_url:
        print(json.dumps({"error": "Usage: staleness_check.py <target_url> [audit_date_iso] [--rendered-text <file>]"}))
        sys.exit(1)

    try:
        audit_date = date.fromisoformat(audit_date_str) if audit_date_str else date.today()
    except ValueError:
        audit_date = date.today()

    output: dict[str, Any] = {
        "target_url": target_url,
        "audit_date": audit_date.isoformat(),
        "rendered_text_used": rendered_text_path is not None,
        "fetch": {"ok": False, "status": None, "error": None},
        "copyright_years_found": [],
        "findings": [],
        "note": (
            "This script covers SKILL.md §4 checks only (copyright years, "
            "dated content, blog freshness, past events). "
            "Third-party corroboration (§2) and entity-ambiguity search (§3) "
            "require agent-driven web-search reasoning and are not automated here."
        ),
    }

    fetch_result = fetch_html(target_url)
    output["fetch"] = {
        "ok": fetch_result["ok"],
        "status": fetch_result["status"],
        "error": fetch_result["error"],
    }

    if not fetch_result["ok"] or not fetch_result["body"]:
        print(json.dumps(output, indent=2))
        return

    body = fetch_result["body"]
    extractor = FullTextExtractor()
    extractor.feed(body)
    static_text = extractor.full_text()

    audit_year = audit_date.year

    # ── Run checks on static HTML first ──────────────────────────────────────
    static_copyright_years, static_findings = run_checks(
        static_text, audit_date, audit_year, found_in="static"
    )
    output["copyright_years_found"] = static_copyright_years

    all_findings = list(static_findings)

    # ── If static yielded no results and rendered text is available, try it ──
    if rendered_text_path is not None:
        try:
            with open(rendered_text_path, encoding="utf-8") as fh:
                rendered_text = fh.read()
        except OSError as exc:
            output["rendered_text_error"] = f"Could not read rendered text file: {exc}"
            rendered_text = None

        if rendered_text:
            rendered_copyright_years, rendered_findings = run_checks(
                rendered_text, audit_date, audit_year, found_in="rendered"
            )

            # Supplement: add rendered findings for any check type that static
            # produced no findings for. This covers SPA sites where static HTML
            # is an empty shell with no visible text.
            static_checks_with_findings = {f["check"] for f in static_findings}
            for finding in rendered_findings:
                if finding["check"] not in static_checks_with_findings:
                    all_findings.append(finding)

            # Extend the copyright years list with any found only in rendered
            extra_years = [y for y in rendered_copyright_years if y not in static_copyright_years]
            if extra_years:
                output["copyright_years_found"] = list(
                    dict.fromkeys(static_copyright_years + extra_years)
                )

    output["findings"] = all_findings

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
