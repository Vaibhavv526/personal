#!/usr/bin/env python3
"""
render_diff.py — Compare raw HTML vs rendered DOM for core brand facts.

Uses Playwright (headless Chromium) to render the page. If Playwright is
not available at runtime, fails gracefully and returns
{"playwright_available": false} so the skill's fallback procedure applies.

Usage:
    python render_diff.py <target_url>

Output: JSON to stdout. Exit 0 always (errors captured in output).

Core facts compared:
    - H1 (brand/entity name, page title)
    - <meta name="description"> content
    - JSON-LD blocks (presence and content)

Additional output fields (for snapshot hand-off to freshness-corroboration):
    - static_text: visible text extracted from raw HTML (no JS)
    - rendered_text: full visible body text from the rendered DOM
      (None when Playwright is unavailable or render fails)
"""

import sys
import json
import re
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser
from typing import Any


# ── HTML extraction helpers (stdlib only, no Playwright dependency) ─────────

class CoreFactExtractor(HTMLParser):
    """Extract H1, meta description, and JSON-LD blocks from raw HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.h1_elements: list[str] = []
        self._current_h1: list[str] = []
        self._in_h1 = False
        self.meta_description: str | None = None
        self.jsonld_blocks: list[str] = []
        self._in_jsonld = False
        self._jsonld_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "h1":
            self._in_h1 = True
            self._current_h1 = []
        elif tag == "meta":
            name = (attr_dict.get("name") or "").lower()
            if name == "description" and attr_dict.get("content"):
                self.meta_description = attr_dict["content"]
        elif tag == "script" and (attr_dict.get("type") or "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._jsonld_buf = []

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._in_h1 = False
            text = " ".join(self._current_h1).strip()
            if text:
                self.h1_elements.append(text)
            self._current_h1 = []
        elif tag == "script" and self._in_jsonld:
            self.jsonld_blocks.append("".join(self._jsonld_buf))
            self._in_jsonld = False
            self._jsonld_buf = []

    def handle_data(self, data: str) -> None:
        if self._in_h1:
            self._current_h1.append(data.strip())
        elif self._in_jsonld:
            self._jsonld_buf.append(data)


class VisibleTextExtractor(HTMLParser):
    """Extract all visible text (excluding script/style/noscript/head) from HTML.

    Mirrors freshness-corroboration/scripts/staleness_check.py's FullTextExtractor
    so that the same regex patterns apply to both static_text and rendered_text.
    """

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


def extract_facts_from_html(html: str) -> dict[str, Any]:
    """Return core facts dict from raw HTML string."""
    parser = CoreFactExtractor()
    parser.feed(html)
    unique_h1s: list[str] = []
    for h in parser.h1_elements:
        norm_h = _norm(h)
        if not any(_norm(u) == norm_h for u in unique_h1s):
            unique_h1s.append(h)

    primary_h1 = unique_h1s[0] if unique_h1s else None
    jsonld_names = _extract_jsonld_names(parser.jsonld_blocks)
    return {
        "h1": primary_h1,
        "h1_elements": parser.h1_elements,
        "meta_description": parser.meta_description,
        "jsonld_block_count": len(parser.jsonld_blocks),
        "jsonld_names": jsonld_names,
    }


def extract_visible_text_from_html(html: str) -> str:
    """Return all visible text from raw HTML, stripped of scripts/styles."""
    parser = VisibleTextExtractor()
    parser.feed(html)
    return parser.full_text()


def _extract_jsonld_names(blocks: list[str]) -> list[str]:
    """Best-effort extraction of 'name' values from JSON-LD blocks."""
    names: list[str] = []
    for block in blocks:
        try:
            data = json.loads(block)
            nodes = data if isinstance(data, list) else [data]
            for node in nodes:
                if isinstance(node, dict):
                    if "name" in node:
                        names.append(str(node["name"]))
                    if "@graph" in node:
                        for sub in node["@graph"]:
                            if isinstance(sub, dict) and "name" in sub:
                                names.append(str(sub["name"]))
        except (json.JSONDecodeError, TypeError):
            pass
    return names


def fetch_raw_html(url: str, timeout: int = 15) -> dict[str, Any]:
    """Fetch page HTML without JS execution."""
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


# ── Playwright helpers ───────────────────────────────────────────────────────

def _playwright_available() -> bool:
    try:
        import importlib
        importlib.import_module("playwright.sync_api")
        return True
    except ImportError:
        return False


def render_with_playwright(url: str, timeout_ms: int = 10000) -> dict[str, Any]:
    """
    Launch headless Chromium via Playwright and extract core facts from the
    rendered DOM. Returns structured result or error information.

    In addition to H1, meta description, and JSON-LD facts, this function also
    captures the full visible body text of the rendered page (rendered_text).
    That field is used by freshness-corroboration/staleness_check.py to run
    copyright-year and dated-content checks on SPA sites where static HTML
    contains no visible text.
    """
    try:
        from playwright.sync_api import sync_playwright, Error as PWError  # type: ignore[import]

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            try:
                page.goto(url, wait_until="networkidle", timeout=timeout_ms)
            except PWError:
                # If networkidle times out (e.g. background polling/streaming on an SPA),
                # the page is usually already loaded; ensure DOM is ready and proceed.
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=5000)
                except Exception:
                    pass

            h1 = page.evaluate("""() => {
                const el = document.querySelector('h1');
                return el ? el.innerText.trim() : null;
            }""")

            rendered_h1s = page.evaluate("""() => {
                return Array.from(document.querySelectorAll('h1'))
                    .map(el => el.innerText.trim())
                    .filter(Boolean);
            }""")

            meta_desc = page.evaluate("""() => {
                const el = document.querySelector('meta[name="description"]');
                return el ? el.getAttribute('content') : null;
            }""")

            jsonld_names = page.evaluate("""() => {
                const scripts = document.querySelectorAll('script[type="application/ld+json"]');
                const names = [];
                scripts.forEach(s => {
                    try {
                        const data = JSON.parse(s.textContent);
                        const nodes = Array.isArray(data) ? data : [data];
                        nodes.forEach(n => {
                            if (n && n.name) names.push(n.name);
                            if (n && n['@graph']) {
                                n['@graph'].forEach(sub => {
                                    if (sub && sub.name) names.push(sub.name);
                                });
                            }
                        });
                    } catch(e) {}
                });
                return names;
            }""")

            jsonld_block_count = page.evaluate("""() =>
                document.querySelectorAll('script[type="application/ld+json"]').length
            """)

            # Capture full visible body text for staleness_check.py hand-off.
            # Excludes script/style content; mirrors what VisibleTextExtractor does
            # on static HTML so the same regex patterns apply to both.
            rendered_text = page.evaluate("""() => {
                const skipTags = new Set(['SCRIPT', 'STYLE', 'NOSCRIPT', 'HEAD']);
                function walk(node, parts) {
                    if (node.nodeType === Node.TEXT_NODE) {
                        const t = node.textContent.trim();
                        if (t) parts.push(t);
                    } else if (node.nodeType === Node.ELEMENT_NODE) {
                        if (!skipTags.has(node.tagName)) {
                            node.childNodes.forEach(c => walk(c, parts));
                        }
                    }
                }
                const parts = [];
                walk(document.body, parts);
                return parts.join(' ');
            }""")

            browser.close()

            return {
                "ok": True,
                "h1": h1,
                "rendered_h1s": rendered_h1s,
                "meta_description": meta_desc,
                "jsonld_block_count": jsonld_block_count,
                "jsonld_names": jsonld_names,
                "rendered_text": rendered_text,
                "error": None,
            }
    except Exception as exc:  # noqa: BLE001
        return {
            "ok": False,
            "h1": None,
            "rendered_h1s": [],
            "meta_description": None,
            "jsonld_block_count": 0,
            "jsonld_names": [],
            "rendered_text": None,
            "error": str(exc),
        }


# ── Diff logic ───────────────────────────────────────────────────────────────

def _norm(s: str | None) -> str:
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.lower().strip())


def diff_facts(static: dict[str, Any], rendered: dict[str, Any]) -> list[dict[str, Any]]:
    """
    Return a list of diff entries describing discrepancies between
    static HTML facts and rendered DOM facts.
    Each entry: {"field", "static_value", "rendered_value", "gap_type"}
    gap_type: "missing_in_static" | "mismatch" | "match"
    """
    diffs = []

    # H1 comparison (semantic and responsive-duplicate aware)
    static_h1s = static.get("h1_elements") or ([static["h1"]] if static.get("h1") else [])
    rendered_h1 = rendered.get("h1")
    rendered_h1s = rendered.get("rendered_h1s") or ([rendered_h1] if rendered_h1 else [])

    norm_static_h1s = [_norm(h) for h in static_h1s if h]
    norm_rendered_h1 = _norm(rendered_h1) if rendered_h1 else ""
    norm_rendered_h1s = [_norm(h) for h in rendered_h1s if h]

    h1_gap = "match"
    matched_static_h1 = static.get("h1")

    if not norm_static_h1s and (norm_rendered_h1 or norm_rendered_h1s):
        h1_gap = "missing_in_static"
    elif norm_static_h1s and not norm_rendered_h1 and not norm_rendered_h1s:
        h1_gap = "mismatch"
    elif norm_static_h1s and norm_rendered_h1:
        exact_match = any(s == norm_rendered_h1 for s in norm_static_h1s)
        contained_match = any((s in norm_rendered_h1 or norm_rendered_h1 in s) for s in norm_static_h1s)

        if exact_match or contained_match:
            h1_gap = "match"
            for h in static_h1s:
                nh = _norm(h)
                if nh == norm_rendered_h1 or nh in norm_rendered_h1 or norm_rendered_h1 in nh:
                    matched_static_h1 = h
                    break
        else:
            h1_gap = "mismatch"

    diffs.append({
        "field": "h1",
        "static_value": matched_static_h1,
        "rendered_value": rendered_h1,
        "gap_type": h1_gap,
    })

    # Meta description
    desc_gap = None
    if not static.get("meta_description") and rendered.get("meta_description"):
        desc_gap = "missing_in_static"
    elif _norm(static.get("meta_description")) != _norm(rendered.get("meta_description")):
        desc_gap = "mismatch"
    else:
        desc_gap = "match"
    diffs.append({
        "field": "meta_description",
        "static_value": static.get("meta_description"),
        "rendered_value": rendered.get("meta_description"),
        "gap_type": desc_gap,
    })

    # JSON-LD presence
    static_count = static.get("jsonld_block_count", 0)
    rendered_count = rendered.get("jsonld_block_count", 0)
    jsonld_gap = "match"
    if static_count == 0 and rendered_count > 0:
        jsonld_gap = "missing_in_static"
    elif static_count != rendered_count:
        jsonld_gap = "mismatch"
    diffs.append({
        "field": "jsonld_block_count",
        "static_value": static_count,
        "rendered_value": rendered_count,
        "gap_type": jsonld_gap,
    })

    return diffs


# ── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: render_diff.py <target_url>"}))
        sys.exit(1)

    target_url = sys.argv[1].strip()

    pw_available = _playwright_available()

    output: dict[str, Any] = {
        "target_url": target_url,
        "playwright_available": pw_available,
        "static_facts": {},
        "static_text": "",        # visible text from raw HTML; for staleness_check.py hand-off
        "rendered_facts": {},
        "rendered_text": "",      # visible body text from rendered DOM; for staleness_check.py hand-off
        "diff": [],
        "error": None,
        "http_status": None,
    }

    # Always fetch static HTML
    raw_result = fetch_raw_html(target_url)
    output["http_status"] = raw_result.get("status")
    if not raw_result["ok"] or not raw_result["body"]:
        output["error"] = f"HTTP fetch failed: status={raw_result['status']} error={raw_result['error']}"
        print(json.dumps(output, indent=2))
        return

    static_facts = extract_facts_from_html(raw_result["body"])
    output["static_facts"] = static_facts
    output["static_text"] = extract_visible_text_from_html(raw_result["body"])

    if not pw_available:
        # Graceful fallback — skill has a fallback path for this
        output["error"] = (
            "Playwright not available at runtime. "
            "Static-only extraction complete. "
            "Use the fallback procedure in SKILL.md §3 to inspect "
            "__NEXT_DATA__, #root, #app, and inline JSON payloads manually."
        )
        print(json.dumps(output, indent=2))
        return

    # Render with Playwright
    rendered_result = render_with_playwright(target_url)
    if not rendered_result["ok"]:
        output["error"] = f"Playwright render failed: {rendered_result['error']}"
        output["rendered_facts"] = {}
        # Still emit static facts so partial result is useful
        print(json.dumps(output, indent=2))
        return

    rendered_facts: dict[str, Any] = {
        "h1": rendered_result["h1"],
        "rendered_h1s": rendered_result.get("rendered_h1s", []),
        "meta_description": rendered_result["meta_description"],
        "jsonld_block_count": rendered_result["jsonld_block_count"],
        "jsonld_names": rendered_result["jsonld_names"],
    }
    output["rendered_facts"] = rendered_facts
    output["rendered_text"] = rendered_result["rendered_text"]
    output["diff"] = diff_facts(static_facts, rendered_facts)

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
