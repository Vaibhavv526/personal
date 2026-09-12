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
    """Extract all <script type="application/ld+json"> text blocks, headings, title, and brand signals."""

    def __init__(self) -> None:
        super().__init__()
        self._in_jsonld = False
        self._current: list[str] = []
        self.blocks: list[str] = []
        self.h1_elements: list[str] = []
        self._current_h1: list[str] = []
        self._in_h1 = False
        self.title: str = ""
        self._in_title = False
        self.brand_signals: list[str] = []
        self._in_header_or_nav = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_dict = {k.lower(): (v or "") for k, v in attrs}
        if tag in ("header", "nav"):
            self._in_header_or_nav += 1

        if tag == "script" and attr_dict.get("type", "").lower() == "application/ld+json":
            self._in_jsonld = True
            self._current = []
        elif tag == "h1":
            self._in_h1 = True
            self._current_h1 = []
        elif tag == "title":
            self._in_title = True
        elif tag == "meta":
            prop = attr_dict.get("property", "").lower()
            name = attr_dict.get("name", "").lower()
            if prop in ("og:site_name", "og:title") or name in ("application-name", "publisher"):
                content = attr_dict.get("content", "").strip()
                if content:
                    self.brand_signals.append(content)
        elif tag in ("img", "svg", "a"):
            alt = attr_dict.get("alt", "").strip()
            aria = attr_dict.get("aria-label", "").strip()
            cls = attr_dict.get("class", "").lower()
            rel = attr_dict.get("rel", "").lower()
            if "logo" in cls or "brand" in cls or rel == "home" or self._in_header_or_nav > 0:
                if alt and len(alt) < 60:
                    self.brand_signals.append(alt)
                if aria and len(aria) < 60:
                    self.brand_signals.append(aria)

    def handle_endtag(self, tag: str) -> None:
        if tag in ("header", "nav") and self._in_header_or_nav > 0:
            self._in_header_or_nav -= 1

        if tag == "script" and self._in_jsonld:
            self.blocks.append("".join(self._current))
            self._in_jsonld = False
            self._current = []
        elif tag == "h1":
            self._in_h1 = False
            text = " ".join(self._current_h1).strip()
            if text:
                self.h1_elements.append(text)
            self._current_h1 = []
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_jsonld:
            self._current.append(data)
        elif self._in_h1:
            self._current_h1.append(data.strip())
        elif self._in_title:
            self.title += data.strip()
        elif self._in_header_or_nav > 0:
            text = data.strip()
            if text and len(text) < 40:
                self.brand_signals.append(text)


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


def clean_brand_name(name: str) -> str:
    """Normalize brand name by removing common legal entity suffixes and punctuation."""
    cleaned = re.sub(
        r"\b(llc|inc|incorporated|ltd|limited|corp|corporation|co|company|gmbh|pty|sarl|sa|bv|holdings|group)\b\.?",
        "",
        name,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"[^\w\s]", " ", cleaned)
    return re.sub(r"\s+", " ", cleaned).strip().lower()


def check_identity_coherence(
    node_name: str | None,
    h1s: list[str],
    title: str | None,
    target_url: str,
    brand_signals: list[str] | None = None,
    all_entity_names: list[str] | None = None,
) -> dict[str, Any] | None:
    """
    Check if the JSON-LD entity name is consistent with the page's visible identity.

    A brand's homepage H1 may legitimately be a value proposition, category statement,
    product positioning statement, or marketing headline. An identity mismatch is only
    reported when there is actual evidence that the page's identity is ambiguous or conflicting.
    """
    if not node_name:
        return None

    norm_org = clean_brand_name(node_name)
    if not norm_org:
        norm_org = node_name.strip().lower()

    # Extract domain name core
    parsed = urllib.parse.urlparse(target_url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    domain_core = host.split(".")[0] if "." in host else host

    title_str = (title or "").lower()
    h1_combined = " ".join(h1s).lower() if h1s else ""
    signals = [s.lower() for s in (brand_signals or [])]
    other_names = [clean_brand_name(n) for n in (all_entity_names or []) if n]

    # 1. Direct match or containment in H1
    if norm_org in h1_combined or any(norm_org in h.lower() for h in h1s):
        return None

    # 2. Brand identity established elsewhere (Title, Domain, Nav/Logo, other Schema)
    brand_in_title = norm_org in title_str or (domain_core and domain_core in norm_org and domain_core in title_str)
    brand_in_domain = norm_org in domain_core or domain_core in norm_org
    brand_in_signals = any(norm_org in s or s in norm_org for s in signals if len(s) >= 3)
    brand_in_other_nodes = any(norm_org == on for on in other_names if on != norm_org)

    if brand_in_title or brand_in_domain or brand_in_signals or brand_in_other_nodes:
        # Brand identity is clearly established on the page.
        # An H1 acting as a value proposition or tagline is NOT a defect.
        return None

    # 3. Only escalate when there is an actual identity conflict or ambiguity
    return {
        "jsonld_name": node_name,
        "h1_text": " ".join(h1s).strip(),
        "title": title,
        "domain": host,
        "mismatch": True,
        "conflict_type": "contradictory_identity",
        "reason": f"JSON-LD Organization name '{node_name}' is not reflected in page title, domain, or primary heading",
    }


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
        "h1_elements": [],
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

    unique_h1s = list(dict.fromkeys(parser.h1_elements))
    output["h1"] = " ".join(unique_h1s).strip() or None
    output["h1_elements"] = parser.h1_elements
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

    # Identity coherence check for first entity node with a name
    for v in validated:
        if v.get("name") and v["is_entity_type"] and output["h1"]:
            mismatch = check_identity_coherence(
                v["name"],
                parser.h1_elements,
                output["title"],
                target_url,
                parser.brand_signals,
                names,
            )
            if mismatch:
                output["name_h1_mismatch"] = mismatch
            break  # only check the first entity

    print(json.dumps(output, indent=2))


if __name__ == "__main__":
    main()
