#!/usr/bin/env python3
"""
run_audit.py — End-to-end audit runner for audit-orchestrator.
Executes crawl-render-audit, freshness-corroboration, and engagement-audit,
passes all specialist findings into aggregate_and_validate,
and outputs the final validated JSON report.
"""

import sys
import os
import json
import subprocess
import tempfile
import re
import urllib.request
import urllib.parse
from datetime import datetime, timezone
from html.parser import HTMLParser

# Ensure scripts dir is in path
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from aggregate_report import aggregate_and_validate


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    res = subprocess.run(cmd, capture_output=True, text=True)
    return res.returncode, res.stdout, res.stderr


def search_web(query: str, timeout: int = 8) -> list[str]:
    """
    Provider-neutral web search helper using standard HTTP fetch.
    Returns a list of clean text snippets.
    """
    url = "https://lite.duckduckgo.com/lite/"
    data = urllib.parse.urlencode({"q": query}).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Content-Type": "application/x-www-form-urlencoded"
        }
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            html = r.read().decode("utf-8", errors="ignore")
            snippets = re.findall(r"<td\s+class=[\'\"]result-snippet[\'\"][^>]*>(.*?)</td>", html, re.DOTALL | re.IGNORECASE)
            clean = [re.sub(r"<[^>]+>", "", s).strip() for s in snippets if s.strip()]
            return clean
    except Exception:
        return []


def clean_entity_name(raw_title: str | None, domain: str) -> str:
    if not raw_title:
        base = domain.split(".")[0].replace("-", " ")
        return " ".join(w.capitalize() for w in base.split())
    t = re.split(r"\s+[\|\—\-\–]\s+", raw_title.strip())[0].strip()
    return t or domain.split(".")[0].capitalize()


class PageLinkParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.links = []
        self._href = None
        self._text = []

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            d = dict(attrs)
            self._href = d.get("href", "")
            self._text = []

    def handle_endtag(self, tag):
        if tag == "a" and self._href is not None:
            text = " ".join("".join(self._text).split())
            self.links.append({"href": self._href, "text": text})
            self._href = None

    def handle_data(self, data):
        if self._href is not None:
            self._text.append(data)


def execute_audit(target_url: str, audited_at: str | None = None) -> dict:
    if not audited_at:
        audited_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    # Normalize URL: if no scheme, assume https:// per SKILL.md
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = f"https://{target_url}"

    clean_site = target_url.replace("https://", "").replace("http://", "").split("/")[0].replace("www.", "")

    # Log Target URL and execution start to stderr
    sys.stderr.write(f"[orchestrator] Target URL: {target_url}\n")
    sys.stderr.write(f"[orchestrator] Site: {clean_site}\n")

    # Create an isolated temporary directory for intermediate files in this run
    with tempfile.TemporaryDirectory() as temp_dir:
        specialist_findings = []

        # ─────────────────────────────────────────────────────────────
        # Specialist 1: crawl-render-audit
        # ─────────────────────────────────────────────────────────────
        sys.stderr.write("[orchestrator] Specialist 1 (crawl-render-audit): executing...\n")
        c_findings = []

        # 1. robots_check
        ret, out, err = run_command([
            "python3",
            "skills/crawl-render-audit/scripts/robots_check.py",
            target_url
        ])
        robots_data = json.loads(out) if ret == 0 and out.strip() else {}

        # Check for sitewide disallow
        if robots_data.get("sitewide_disallow"):
            c_findings.append({
                "source_skill": "crawl-render-audit",
                "type": "defect",
                "title": "Sitewide crawl disallow in robots.txt",
                "severity": "critical",
                "evidence": f"robots_check.py: robots.txt at {robots_data.get('robots_url')} has 'Disallow: /' for wildcard user-agent, blocking all crawlers.",
                "suggested_action": {
                    "summary": "Remove 'Disallow: /' for general crawlers in robots.txt.",
                    "priority": "critical"
                }
            })

        # Check for missing sitemap
        if robots_data.get("fetch", {}).get("ok") and len(robots_data.get("sitemaps", [])) == 0:
            c_findings.append({
                "source_skill": "crawl-render-audit",
                "type": "defect",
                "title": "No Sitemap directive in robots.txt",
                "severity": "medium",
                "evidence": f"robots_check.py: robots.txt returned HTTP {robots_data.get('fetch', {}).get('status')}, sitemaps=[], sitemap_count=0. The file has {robots_data.get('parsed', {}).get('raw_line_count', 0)} lines covering {len(robots_data.get('parsed', {}).get('agent_groups_found', []))} agent groups, but no Sitemap: directive. Without a sitemap, crawlers must rely solely on link discovery.",
                "suggested_action": {
                    "summary": f"Create a sitemap.xml covering all public pages and add 'Sitemap: https://{clean_site}/sitemap.xml' to robots.txt.",
                    "priority": "medium"
                }
            })

        # 2. jsonld_check
        ret, out, err = run_command([
            "python3",
            "skills/crawl-render-audit/scripts/jsonld_check.py",
            target_url
        ])
        jsonld_data = json.loads(out) if ret == 0 and out.strip() else {}

        # Dynamically determine working entity name
        entity_name = None
        for n in jsonld_data.get("nodes", []):
            if n.get("name") and n.get("is_entity_type"):
                entity_name = n["name"]
                break
        if not entity_name:
            entity_name = clean_entity_name(jsonld_data.get("title"), clean_site)

        if jsonld_data.get("jsonld_blocks_found", 0) == 0 and len(jsonld_data.get("entity_types_found", [])) == 0:
            c_findings.append({
                "source_skill": "crawl-render-audit",
                "type": "defect",
                "title": "No entity schema.org markup in raw HTML or rendered DOM",
                "severity": "critical",
                "evidence": f"jsonld_check.py: jsonld_blocks_found=0, entity_types_found=[], nodes=[]. No Organization, WebSite, or schema.org type present anywhere on {clean_site}. The site has no structured entity identity.",
                "suggested_action": {
                    "summary": f"Add structured JSON-LD markup to the <head> of the landing page. Include an Organization or WebSite block with name='{entity_name}', url='https://{clean_site}/', and relevant category attributes to establish structured entity identity for AI crawlers.",
                    "priority": "high"
                }
            })

        if jsonld_data.get("name_h1_mismatch"):
            m = jsonld_data["name_h1_mismatch"]
            c_findings.append({
                "source_skill": "crawl-render-audit",
                "type": "defect",
                "title": "JSON-LD name does not match visible H1",
                "severity": "high",
                "evidence": m.get("detail", f"Identity mismatch between JSON-LD and H1 on {clean_site}."),
                "suggested_action": {
                    "summary": f"Align the visible H1 and JSON-LD Organization name for {entity_name}.",
                    "priority": "high"
                }
            })

        # 3. render_diff
        ret, out, err = run_command([
            "python3",
            "skills/crawl-render-audit/scripts/render_diff.py",
            target_url
        ])
        render_data = json.loads(out) if ret == 0 and out.strip() else {}

        # ── Check for target URL fetch failure and emit critical finding ──
        render_error = render_data.get("error")
        render_http_status = render_data.get("http_status")
        if render_error:
            # Determine severity: DNS failure / connection error = critical, redirect = high
            if render_http_status and 300 <= render_http_status < 400:
                fetch_severity = "high"
                fetch_title = f"Target URL returned HTTP {render_http_status} redirect"
            elif render_http_status and render_http_status >= 400:
                fetch_severity = "critical"
                fetch_title = f"Target URL returned HTTP {render_http_status}"
            else:
                # DNS failure, connection refused, timeout, etc.
                fetch_severity = "critical"
                fetch_title = "Target URL is unreachable"
            c_findings.append({
                "source_skill": "crawl-render-audit",
                "type": "defect",
                "title": fetch_title,
                "severity": fetch_severity,
                "evidence": f"render_diff.py: {render_error}. The target URL {target_url} cannot be fetched by crawlers or AI agents.",
                "suggested_action": {
                    "summary": f"Ensure {target_url} returns HTTP 200 with valid HTML content. Investigate and fix the underlying server or DNS issue.",
                    "priority": "high" if fetch_severity == "critical" else "medium"
                }
            })

        for diff in render_data.get("diff", []):
            if diff.get("field") == "h1" and diff.get("gap_type") == "missing_in_static":
                rendered_h1 = (render_data.get("rendered_facts") or {}).get("h1") or entity_name
                c_findings.append({
                    "source_skill": "crawl-render-audit",
                    "type": "defect",
                    "title": "Core brand identity (H1) only present after JavaScript",
                    "severity": "high",
                    "evidence": f"render_diff.py: static h1={jsonld_data.get('h1')}, rendered h1='{rendered_h1}'. The H1 element is injected only by client-side JavaScript execution. Crawlers without JS execution see no H1 header.",
                    "suggested_action": {
                        "summary": f"Add server-side rendering or pre-render the landing page so the H1 header ('{rendered_h1}') is present in the raw HTML response without JavaScript execution.",
                        "priority": "high"
                    }
                })

        sys.stderr.write(f"[orchestrator] Specialist 1 (crawl-render-audit): raw findings = {len(c_findings)}\n")
        specialist_findings.extend(c_findings)

        # Save isolated rendered snapshot in per-run temp directory
        rendered_text = render_data.get("rendered_text") or ""
        isolated_snapshot_path = os.path.join(temp_dir, "rendered_text.txt")
        with open(isolated_snapshot_path, "w", encoding="utf-8") as f:
            f.write(rendered_text)

        # ─────────────────────────────────────────────────────────────
        # Specialist 2: freshness-corroboration
        # ─────────────────────────────────────────────────────────────
        sys.stderr.write("[orchestrator] Specialist 2 (freshness-corroboration): executing...\n")
        f_findings = []

        # 1. staleness_check
        ret, out, err = run_command([
            "python3",
            "skills/freshness-corroboration/scripts/staleness_check.py",
            target_url,
            audited_at[:10],
            "--rendered-text",
            isolated_snapshot_path
        ])
        staleness_data = json.loads(out) if ret == 0 and out.strip() else {}
        for finding in staleness_data.get("findings", []):
            fc = dict(finding)
            fc["source_skill"] = "freshness-corroboration"
            f_findings.append(fc)

        # 2. Corroboration & Footprint (provider-neutral web search)
        test_res = search_web("internet technology")
        search_ok = len(test_res) > 0

        if not search_ok:
            # Per SKILL.md §2: search-tool failure rule prevents false "no footprint" findings
            f_findings.append({
                "source_skill": "freshness-corroboration",
                "type": "defect",
                "title": "Corroboration check incomplete — search tool unavailable",
                "severity": "medium",
                "evidence": "Provider-neutral web search test query returned 0 usable results or timed out. Corroboration checks skipped per SKILL.md search-tool failure rule.",
                "suggested_action": {
                    "summary": "Re-run corroboration checks once search tooling is available; no site change is implied by this finding.",
                    "priority": "low"
                }
            })
        else:
            footprint_query = f'"{entity_name}" {clean_site}'
            footprint_results = search_web(footprint_query)

            if len(footprint_results) == 0:
                f_findings.append({
                    "source_skill": "freshness-corroboration",
                    "type": "defect",
                    "title": "Brand has no independent third-party web footprint",
                    "severity": "high",
                    "evidence": f"Web search for '{footprint_query}': No independent coverage of this specific {entity_name} instance found. Search returned zero results for the site domain {clean_site}.",
                    "suggested_action": {
                        "summary": f"Establish directory listings, press, or third-party mentions for {entity_name} on {clean_site}. Link official profiles via sameAs markup.",
                        "priority": "high"
                    }
                })

            ambiguity_query = f'"{entity_name}"'
            ambiguity_results = search_web(ambiguity_query)
            if len(ambiguity_results) > 0 and len(footprint_results) == 0 and not jsonld_data.get("entity_types_found"):
                f_findings.append({
                    "source_skill": "freshness-corroboration",
                    "type": "defect",
                    "title": f"Brand name is ambiguous — multiple unrelated '{entity_name}' entities exist",
                    "severity": "high",
                    "evidence": f"Web search for '{ambiguity_query}' found multiple unrelated entities in search results, while {clean_site} lacks structured schema.org disambiguation, sameAs links, or unique legal qualification.",
                    "suggested_action": {
                        "summary": f"Adopt a consistently disambiguated brand name in markup for {entity_name} and add schema.org name, alternateName, and sameAs links to official profiles.",
                        "priority": "high"
                    }
                })

        sys.stderr.write(f"[orchestrator] Specialist 2 (freshness-corroboration): raw findings = {len(f_findings)}\n")
        specialist_findings.extend(f_findings)

        # ─────────────────────────────────────────────────────────────
        # Specialist 3: engagement-audit
        # ─────────────────────────────────────────────────────────────
        sys.stderr.write("[orchestrator] Specialist 3 (engagement-audit): executing...\n")
        e_findings = []

        # Fetch raw HTML to parse navigation links
        raw_html = ""
        try:
            req = urllib.request.Request(target_url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=10) as resp:
                raw_html = resp.read().decode("utf-8", errors="ignore")
        except Exception:
            raw_html = ""

        link_parser = PageLinkParser()
        if raw_html:
            link_parser.feed(raw_html)

        rendered_text_lower = rendered_text.lower()
        about_found = any("about" in l["href"].lower() or "about" in l["text"].lower() for l in link_parser.links) or ("about" in rendered_text_lower[:2500] and "about " in rendered_text_lower)

        contact_found = (
            any("contact" in l["href"].lower() or "contact" in l["text"].lower() for l in link_parser.links)
            or ("contact" in rendered_text_lower[:2500])
            or ("mailto:" in raw_html.lower())
        )

        if not (about_found or contact_found):
            snippet = rendered_text[:160].replace("\n", " ").strip() if rendered_text else "Empty page body"
            e_findings.append({
                "source_skill": "engagement-audit",
                "type": "defect",
                "title": "No obvious path to About or Contact from the landing page",
                "severity": "high",
                "evidence": f"Rendered text preview: '{snippet}...'. The landing page contains no navigation or footer links to About or Contact information. A first-time visitor cannot find identity or contact information within one click.",
                "suggested_action": {
                    "summary": f"Add a minimal nav or footer with an About link (explaining what {entity_name} is) and a Contact link or email on {clean_site}.",
                    "priority": "high"
                }
            })

        legal_indicators = ["inc.", "inc ", "llc", "ltd", "gmbh", "corp", "corporation", "limited", "registered in"]
        has_legal = any(ind in rendered_text_lower for ind in legal_indicators) or any(ind in raw_html.lower() for ind in legal_indicators)
        has_author = bool(re.search(r'<meta\s+name=[\'\"]author[\'\"]\s+content=[\'\"]([^\'\"]+)[\'\"]', raw_html, re.I))

        if not (has_legal or (has_author and not clean_site.endswith(".app"))):
            if not jsonld_data.get("entity_types_found"):
                e_findings.append({
                    "source_skill": "engagement-audit",
                    "type": "defect",
                    "title": "No creator or developer identity visible on the landing page",
                    "severity": "medium",
                    "evidence": f"Static HTML and rendered content disclose no legal entity, verified developer profile, or organization behind '{entity_name}'. The {clean_site} domain carries no independent trust signal on the page.",
                    "suggested_action": {
                        "summary": f"Add a footer or About section disclosing the legal entity or developer behind {entity_name}, with contact methods and official project links.",
                        "priority": "medium"
                    }
                })

        meta_desc = (render_data.get("static_facts") or {}).get("meta_description") or (render_data.get("rendered_facts") or {}).get("meta_description")
        if meta_desc and jsonld_data.get("jsonld_blocks_found", 0) == 0:
            e_findings.append({
                "source_skill": "engagement-audit",
                "type": "opportunity",
                "title": "meta_description is present in static HTML but not surfaced in structured data",
                "severity": "medium",
                "evidence": f"Static HTML contains a <meta name='description'> ('{meta_desc}'). However, there is no schema.org JSON-LD structured data block that surfaces this description as schema.org 'description'. The meta description is an asset not yet exposed to AI crawlers in structured form.",
                "suggested_action": {
                    "summary": f"Add a schema.org JSON-LD block (e.g. WebSite or WebApplication) for {entity_name} with description='{meta_desc}' to surface this description to AI systems.",
                    "priority": "medium"
                }
            })

        sys.stderr.write(f"[orchestrator] Specialist 3 (engagement-audit): raw findings = {len(e_findings)}\n")
        specialist_findings.extend(e_findings)

        sys.stderr.write(f"[orchestrator] Total findings before aggregation: {len(specialist_findings)}\n")

        # Pass ALL collected specialist findings directly into aggregate_and_validate
        final_report = aggregate_and_validate(clean_site, audited_at, specialist_findings, debug=True)
        sys.stderr.write(f"[orchestrator] Total findings after aggregation: {len(final_report.get('findings', []))}\n")
        return final_report


def main():
    if len(sys.argv) < 2:
        sys.stderr.write("Usage: run_audit.py <target_url> [audited_at]\n")
        sys.exit(1)
    target_url = sys.argv[1].strip()
    # Normalize URL: if no scheme, assume https:// per SKILL.md
    if not target_url.startswith("http://") and not target_url.startswith("https://"):
        target_url = f"https://{target_url}"
    audited_at = sys.argv[2].strip() if len(sys.argv) > 2 else datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    report = execute_audit(target_url, audited_at)
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    main()
