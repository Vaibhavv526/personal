---
name: crawl-render-audit
description: Audits a URL for technical crawlability, robots.txt disallows, JSON-LD/schema.org entity markup, and JavaScript rendering gaps where core facts exist only in the post-JS DOM. Triggers when given a URL to audit crawlability, structured data, SSR vs CSR, or when invoked by audit-orchestrator.
license: MIT
allowed-tools:
  - http-fetch
  - browser-render
---

# Crawl Render Audit

Sub-skill of brand-ai-readiness-audit. Read-only and recommend-only. Return a **raw list of findings** to `audit-orchestrator`. Do not emit the final marketplace JSON report. Do not modify the site.

## Goal

Determine whether crawlers and AI agents can (1) be allowed to fetch the URL, (2) read entity/product facts from raw HTML, and (3) see the same core facts without executing JavaScript.

## Inputs

- `target_url` from the orchestrator (or the user).
- Derive `origin` (`scheme://host`) and `robots_url` = `{origin}/robots.txt`.

## Procedure

Execute these steps in order. Use HTTP GET. Record status codes. Do not POST, authenticate, or bypass blocks.

> **Fact-gathering for steps 1–3 is deterministic.** Run the scripts listed
> under each step and use their JSON output as the primary evidence source.
> Full severity-mapping tables are in [`references/severity-rules.md`](references/severity-rules.md).

### 1. Check `robots.txt` for disallows

**Run:** `python scripts/robots_check.py {target_url}`

Returns `fetch.status`, `fetch.error`, `content_type`, `looks_like_valid_robots_txt`, `sitewide_disallow`, `sitemaps[]`,
`parsed.raw_line_count`, and `evaluation` (per tracked agent: `result`, `matched_rule`).

Key severity rules (see reference for full table):
- `looks_like_valid_robots_txt == false` (despite `fetch.status == 200`) → `high` · `robots.txt returns non-robots.txt content (catch-all routing)` (evidence citing `content_type` and short excerpt confirming HTML)
- `fetch.status == 404` → `medium` · `robots.txt missing`
- `fetch.ok == false` (5xx/timeout) → `high` · `robots.txt unreachable`
- `sitewide_disallow == true` → `critical` · `Sitewide robots disallow`
- Any tracked AI agent `result == "disallow"` → `critical` · `Target URL disallowed in robots.txt`
- `sitemaps[]` empty → `medium` · `No Sitemap directive in robots.txt`

Do not flag `Crawl-delay`, `/llms.txt`, `/api/`, or app-internal `Disallow` entries unless they cover the target path.

### 2. Inspect raw HTML for JSON-LD / schema.org

**Run:** `python scripts/jsonld_check.py {target_url}`

Returns `fetch.*`, `jsonld_parse_errors[]`, `nodes[]` (with `types`, `missing_required_fields`, `missing_recommended_fields`, `name`, `url`, `id`), `entity_types_found[]`, `h1`, `name_h1_mismatch`, `conflicting_names[]`, `conflicting_ids[]`.

Key severity rules (required/recommended fields per type in reference):
- `fetch.status != 200` → `critical` (4xx/5xx) or `high` (3xx loop)
- Any `jsonld_parse_errors[]` → `high` · `Malformed JSON-LD`
- Homepage without entity type → `critical` · `No entity schema.org markup in raw HTML`
- Product URL without `Product`/`Offer` → `high` · `Product page missing Product JSON-LD`
- `name_h1_mismatch != null` → `high` · `Identity mismatch between JSON-LD and visible branding` (only flags actual contradictions; marketing value propositions in H1 with established brand in title/domain/nav are not defects)
- Missing required `url` field on any node → `medium`
- Org-type node missing `logo` or `sameAs` → `medium`
- Dead `sameAs` URL (spot-check ≤3) → `medium` per URL
- `conflicting_names` or `conflicting_ids` non-empty → `high`

### 3. Compare static HTML to rendered DOM

Core facts: brand name, company purpose, product/service name, address, price/CTA, contact.

**Run:** `python scripts/render_diff.py {target_url}`

Returns `playwright_available`, `static_facts`, `rendered_facts`, `diff[]`
(per field: `field`, `static_value`, `rendered_value`, `gap_type`).

**If `playwright_available == false`:** inspect raw HTML for `__NEXT_DATA__`,
`window.__NUXT__`, empty `#root`/`#app` with no SSR text.

Key severity rules (full table in reference):
- `h1` · `missing_in_static` → `critical` · `Core brand identity only present after JavaScript`
- `meta_description` · `missing_in_static` → `high` · `Value proposition missing from static HTML`
- `jsonld_block_count` · `missing_in_static` → `high` · `JSON-LD injected only by JavaScript`
- `h1` · `mismatch` → `high` · `H1 differs between static HTML and rendered DOM` (only flags when rendered heading has no equivalent in raw HTML; responsive duplicate markup matching rendered H1 is not a gap)
- All entries `match` → no finding
- SPA with static JSON-LD + H1 mismatch → `medium`

### Additional crawl signals (only if observed)

- `noindex` in `X-Robots-Tag` or `<meta name="robots">` on a discoverable page → `critical`
- Canonical pointing at different host or homepage for a distinct entity/product → `high`
- Soft 404 (200 with "not found" in H1) → `high`

### 4. Proactive opportunities (even when checks pass)

After all defect checks are complete, evaluate whether any high-leverage, non-obvious improvement exists even though nothing is strictly broken. Only emit an opportunity finding if there is concrete evidence on the page supporting it.

Examples (not exhaustive):

- **Organization schema present but no `sameAs` links**: `jsonld_check.py` found an Organization node that passed all required-field checks, yet `missing_recommended_fields` includes `sameAs`. Even though this is not a defect (the schema exists), adding `sameAs` to Wikipedia, LinkedIn, and official profiles materially improves AI entity disambiguation.
- **`sameAs` present but points only to social profiles, no Wikidata/Wikipedia link**: entity reconciliation is incomplete.
- **JSON-LD passes validation but lacks `logo`**: AI systems and rich-result renderers use `logo`; its absence is a missed opportunity even when other fields are correct.
- **robots.txt allows all bots and has a sitemap, but the sitemap lists only the homepage**: the site may have indexable product or service pages that are harder to discover.

For each opportunity found, emit a finding with:

```json
{
  "source_skill": "crawl-render-audit",
  "type": "opportunity",
  "title": "Organization schema present but no sameAs links",
  "severity": "medium",
  "evidence": "jsonld_check.py found Organization node with name='Acme Corp'; missing_recommended_fields includes sameAs. No sameAs array in any JSON-LD block.",
  "suggested_action": {
    "summary": "Add sameAs links to Wikipedia, Wikidata, LinkedIn, and official directory profiles in the Organization JSON-LD block.",
    "priority": "medium"
  }
}
```

Do not emit an opportunity if you have already emitted a `"defect"` finding covering the same property.

## Output to the orchestrator

Return **only** a JSON array (no marketplace wrapper, no markdown). Each element:

```json
{
  "source_skill": "crawl-render-audit",
  "type": "defect",
  "title": "Target URL disallowed in robots.txt",
  "severity": "critical",
  "evidence": "User-agent: * Disallow: / for https://example.com/robots.txt; target path / is covered.",
  "suggested_action": {
    "summary": "Allow crawl of public marketing URLs in robots.txt while keeping private app paths disallowed.",
    "priority": "high"
  }
}
```

`type` defaults to `"defect"` if omitted. Empty array if no issues. Do not assign `id`. Do not implement the suggested action.
