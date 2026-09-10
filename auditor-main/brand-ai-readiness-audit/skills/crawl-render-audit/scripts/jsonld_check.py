#!/usr/bin/env python3
"""
jsonld_check.py — Fetch raw HTML and extract/validate every JSON-LD block.

Usage:
    python jsonld_check.py <target_url>

Output: JSON to stdout. Exit 0 always (errors captured in output).

Validates against the entity @type list defined in crawl-render-audit/SKILL.md:
    Organization, LocalBusiness, Corporation, Brand, Person,
    Product, Offer, WebSite, WebPage, FAQPage, Article, BreadcrumbList
"""

import sys
import json
import re
import urllib.request
import urllib.error
import urllib.parse
from html.parser import HTMLParser
from typing import Any

ENTITY_TYPES_OF_INTEREST = {
    "Organization",
    "LocalBusiness",
    "Corporation",
    "Brand",
    "Person",
    "Product",
    "Offer",
    "WebSite",
    "WebPage",
    "FAQPage",
    "Article",
    "BreadcrumbList",
}

REQUIRED_FIELDS_BY_TYPE: dict[str, list[str]] = {
    "Organization": ["name", "url"],
    "LocalBusiness": ["name", "url", "address"],
    "Corporation": ["name", "url"],
    "Brand": ["name"],
    "Person": ["name"],
    "Product": ["name", "description"],
    "Offer": ["price", "priceCurrency"],
    "WebSite": ["name", "url"],
    "WebPage": ["name"],
    "FAQPage": ["mainEntity"],
    "Article": ["headline", "author"],
    "BreadcrumbList": ["itemListElement"],
}

RECOMMENDED_FIELDS_BY_TYPE: dict[str, list[str]] = {
    "Organization": ["logo", "sameAs", "contactPoint"],
    "LocalBusiness": ["telephone", "openingHours", "geo"],
    "Product": ["image", "sku", "offers"],
    "Person": ["sameAs", "jobTitle"],
}


class ScriptTagExtractor(HTMLParser):
    """Extract all <script type="application/ld+json"> text blocks."""

    def __init__(self) -> None:
        super().__init__()
        self._in_jsonld = False
        self._current: list[str] = []
        self.blocks: list[str] = []
        self.h1s: list[str] = []
        self.title: str = ""
        self._in_h1 = False
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = dict(attrs)
        if tag == "script" and attr_dict.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._current = []
        elif tag == "h1":
            self._in_h1 = True
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._in_jsonld:
            self.blocks.append("".join(self._current))
            self._in_jsonld = False
            self._current = []
        elif tag == "h1":
            self._in_h1 = False
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._current.append(data)
        elif self._in_h1:
            self.h1s.append(data.strip())
        elif self._in_title:
            self.title += data.strip()


def fetch_html(url: str, timeout: int = 15) -> dict[str, Any]:
    """Fetch raw HTML without JavaScript execution."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": "BrandAIReadinessAudit/1.0 (+https://github.com/brand-ai-readiness-audit)",
                "Accept": "text/html,application/xhtml+xml",
                "Accept-Language": "en-US,en;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            final_url = resp.url
            status = resp.status
            content_type = resp.headers.get("Content-Type", "")
            body = resp.read().decode("utf-8", errors="replace")
            return {
                "ok": True,
                "status": status,
                "final_url": final_url,
                "content_type": content_type,
                "body": body,
                "error": None,
            }
    except urllib.error.HTTPError as exc:
        return {"ok": False, "status": exc.code, "final_url": url, "content_type": None, "body": None, "error": str(exc)}
    except urllib.error.URLError as exc:
        return {"ok": False, "status": None, "final_url": url, "content_type": None, "body": None, "error": str(exc.reason)}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "status": None, "final_url": url, "content_type": None, "body": None, "error": str(exc)}


def expand_graph(obj: Any) -> list[dict[str, Any]]:
    """
    Expand a single parsed JSON-LD value into a flat list of typed nodes.
    Handles: plain object, @graph arrays, top-level arrays.
    """
    nodes: list[dict[str, Any]] = []
    if isinstance(obj, list):
        for item in obj:
            nodes.extend(expand_graph(item))
    elif isinstance(obj, dict):
        if "@graph" in obj:
            for item in obj["@graph"]:
                nodes.extend(expand_graph(item))
        elif "@type" in obj:
            nodes.append(obj)
    return nodes


def validate_node(node: dict[str, Any]) -> dict[str, Any]:
    """Validate a single typed JSON-LD node against known requirements."""
    raw_type = node.get("@type", "")
    types = raw_type if isinstance(raw_type, list) else [raw_type]
    # Normalize to short name (strip schema.org prefix)
    types = [t.replace("https://schema.org/", "").replace("http://schema.org/", "") for t in types]

    missing_required: list[str] = []
    missing_recommended: list[str] = []

    for t in types:
        for field in REQUIRED_FIELDS_BY_TYPE.get(t, []):
            if field not in node:
                missing_required.append(f"{t}.{field}")
        for field in RECOMMENDED_FIELDS_BY_TYPE.get(t, []):
            if field not in node:
                missing_recommended.append(f"{t}.{field}")

    is_entity = bool(set(types) & ENTITY_TYPES_OF_INTEREST)

    return {
        "types": types,
        "is_entity_type": is_entity,
        "id": node.get("@id"),
        "name": node.get("name"),
        "url": node.get("url"),
        "missing_required_fields": missing_required,
        "missing_recommended_fields": missing_recommended,
    }


def check_name_vs_h1(node_name: str | None, h1s: list[str]) -> dict[str, Any] | None:
    """Check if JSON-LD name field matches the page H1."""
    if not node_name or not h1s:
        return None
    h1_combined = " ".join(h1s).strip()
    # Normalize: lowercase, collapse whitespace
    def norm(s: str) -> str:
        return re.sub(r"\s+", " ", s.lower().strip())
    if norm(node_name) != norm(h1_combined):
        return {"jsonld_name": node_name, "h1_text": h1_combined, "mismatch": True}
    return None


def main() -> None:
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: jsonld_check.py <target_url>"}))
        sys.exit(1)

    target_url = sys.argv[1].strip()
    fetch_result = fetch_html(target_url)

    output: dict[str, Any] = {
        "target_url": target_url,
        "fetch": {
            "ok": fetch_result["ok"],
            "status": fetch_result["status"],
            "final_url": fetch_result["final_url"],
            "content_type": fetch_result["content_type"],
            "error": fetch_result["error"],
        },
        "jsonld_blocks_found": 0,
        "jsonld_parse_errors": [],
        "nodes": [],
        "entity_types_found": [],
        "h1": None,
        "title": None,
        "name_h1_mismatch": None,
        "conflicting_names": [],
        "conflicting_ids": [],
    }

    if not fetch_result["ok"] or not fetch_result["body"]:
        print(json.dumps(output, indent=2))
        return

    body = fetch_result["body"]
    parser = ScriptTagExtractor()
    parser.feed(body)

    output["h1"] = " ".join(parser.h1s).strip() or None
    output["title"] = parser.title or None

    all_nodes: list[dict[str, Any]] = []
    parse_errors: list[dict[str, Any]] = []

    for i, block in enumerate(parser.blocks):
        try:
            parsed_json = json.loads(block)
            nodes = expand_graph(parsed_json)
            all_nodes.extend(nodes)
        except json.JSONDecodeError as exc:
            excerpt = block.strip()[:120]
            parse_errors.append({
                "block_index": i,
                "error": str(exc),
                "excerpt": excerpt,
            })

    output["jsonld_blocks_found"] = len(parser.blocks)
    output["jsonld_parse_errors"] = parse_errors

    validated = [validate_node(n) for n in all_nodes]
    output["nodes"] = validated

    # Collect all entity types
    entity_types: list[str] = []
    for v in validated:
        for t in v["types"]:
            if t in ENTITY_TYPES_OF_INTEREST:
                entity_types.append(t)
    output["entity_types_found"] = list(dict.fromkeys(entity_types))  # deduplicated, order preserved

    # Name / ID conflict detection
    names: list[str] = [v["name"] for v in validated if v.get("name") and v["is_entity_type"]]
    ids: list[str] = [v["id"] for v in validated if v.get("id") and v["is_entity_type"]]

    unique_names = list(dict.fromkeys(n.strip().lower() for n in names))
    if len(unique_names) > 1:
        output["conflicting_names"] = names

    unique_ids = list(dict.fromkeys(ids))
    if len(unique_ids) > 1:
        output["conflicting_ids"] = ids

    # Name vs H1 check for first entity node with a name
    for v in validated:
        if v.get("name") and v["is_entity_type"] and output["h1"]:
            mismatch = check_name_vs_h1(v["name"], parser.h1s)
            if mismatch:
                output["name_h1_mismatch"] = mismatch
            break  # only check the first entity

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
