---
name: freshness-corroboration
description: Audits a URL for fact staleness, third-party corroboration of brand claims, and entity-name ambiguity. Triggers when given a URL to verify brand facts against Wikipedia, news, and directories, check name collisions, or when invoked by audit-orchestrator.
license: MIT
allowed-tools:
  - http-fetch
  - web-search
---

# Freshness Corroboration

Sub-skill of brand-ai-readiness-audit. Read-only and recommend-only. Return a **raw list of findings** to `audit-orchestrator`. Do not emit the final marketplace JSON report. Do not modify the site.

## Goal

Identify the brand/entity the page represents, test whether independent sources corroborate its claims, detect other entities that share the name, and flag stale on-site dates.

## Inputs

- `target_url` and `site` (registrable domain) from the orchestrator.

## Procedure

### 1. Identify the core entity/brand

1. Fetch the page (static HTML; rendered text if already available from crawl-render-audit—do not contradict that snapshot).
2. Extract a working identity:
   - JSON-LD `Organization`/`Brand`/`LocalBusiness`/`Person` `name`
   - else `<h1>`
   - else `<title>` (strip “| Home”, site chrome)
   - else nav logo `alt`
3. Record `entity_name`, `entity_type` (company, product, person, place, unknown), and 3–8 **on-site claims** to test: founding year, HQ city, leadership names, product category, tagline, “#1 / largest / official”, award names, store count, “established” dates.
4. If identity cannot be determined (generic title “Home”, no H1, stock template): severity `critical`, title `Core entity cannot be identified from the page`, evidence quoted title/H1/JSON-LD absence. Suggested action: put the legal or brand name in H1, title, and Organization JSON-LD. Skip web corroboration of a name you invented.
5. Prefer the legal/brand name over a campaign slogan as `entity_name`.

### 2. Search the web for third-party corroboration

> **Search-tool failure rule (§2).** Before running any queries, verify the web-search tool is functional by issuing a single test query. If the search tool errors, times out, or returns zero usable results after **one retry**, do **not** proceed to classify any claim as uncorroborated, contradicted, lacking a footprint, or otherwise suspicious. Instead, emit exactly **one** finding for the entire corroboration step:
>
> ```json
> {
>   "title": "Corroboration check incomplete — search tool unavailable",
>   "severity": "medium",
>   "evidence": "<state the exact tool error message or empty-result condition observed on this run>",
>   "suggested_action": {
>     "summary": "Re-run corroboration checks once search tooling is available; no site change is implied by this finding.",
>     "priority": "low"
>   }
> }
> ```
>
> **Do not fill this gap using general or prior knowledge about the brand.** A corroboration claim (uncorroborated, contradicted, no footprint) must be backed by an actual search result retrieved during this run. Skip the remainder of §2 and proceed to §3.

Search the open web for `entity_name` plus the domain and distinctive claims (e.g. `"Acme Robotics"`, `Acme Robotics {city}`, site name). Use Wikipedia/Wikidata, major news, company directories (LinkedIn company, Crunchbase, official registries, Google Knowledge-style panels if visible), and the brand’s official profiles.

For each high-importance claim (legal name, what they do, location, leadership if stated as fact):

1. **Corroborated**: at least one independent, reputable source agrees. Do not create a finding.
2. **Uncorroborated**: on-site claim with **no** independent mention after reasonable search (2–5 queries). Severity `high` if the claim is identity-defining (what the company is, HQ, “official X”); `medium` if secondary (award, statistic). Title `On-site claim not corroborated by third parties`. Evidence: the claim quote, queries used, and that Wikipedia/news/directories did not confirm it. Suggested action: cite sources on-page or weaken unsourced superlatives; keep facts consistent with public records.
3. **Contradicted**: a reputable source disagrees (different HQ, acquired/defunct, different CEO, product discontinued). Severity `critical` if the contradiction is about existence, legal name, or “we are still operating”; else `high`. Title `On-site claim contradicted by third-party source`. Evidence: on-site quote + source title, URL, and conflicting fact. Suggested action: update the page to match current public facts or explain the discrepancy.
4. **No third-party footprint**: entity_name + domain yield only the site itself, mirrors, and spam. Severity `high`, title `Brand has little independent web corroboration`. Evidence: search returned only first-party or low-quality clones. Suggested action: earn directory listings, news, or Wikipedia/Wikidata if notable; publish consistent NAP and sameAs.

Do not treat the company’s own blog, press room, or paid landing pages as independent corroboration. Wikipedia, regulators, established news, and major directories count. Social profiles count as weak corroboration (`medium` only if they conflict or are missing when the page claims “follow us” identities that 404—spot-check).

### 3. Entity ambiguity (shared names)

> **Search-tool failure rule (§3).** §3 depends on the same web-search tool as §2. If the tool was already found unavailable in §2 (the `Corroboration check incomplete` finding was emitted), skip §3 entirely — do not emit an additional finding for it. If §2 succeeded but the search tool fails during §3 queries specifically, apply the same rule: if the tool errors, times out, or returns zero usable results after **one retry**, emit exactly **one** finding:
>
> ```json
> {
>   "title": "Corroboration check incomplete — search tool unavailable",
>   "severity": "medium",
>   "evidence": "<state the exact tool error message or empty-result condition observed on this run>",
>   "suggested_action": {
>     "summary": "Re-run corroboration checks once search tooling is available; no site change is implied by this finding.",
>     "priority": "low"
>   }
> }
> ```
>
> **Do not fill this gap using general or prior knowledge about the brand.** A claim about entity collision or name ambiguity must be backed by an actual search result from this run. Skip the remainder of §3 and proceed to §4.

1. Search `entity_name` without the domain. List other notable organizations, products, or people with the same or confusingly similar name.
2. If another well-known entity shares the name in the same industry or the same country: severity `high`, title `Entity name is ambiguous`, evidence the other entity and a source URL. Suggested action: use a disambiguating legal name, product qualifier, geo, and strong schema.org `name` + `alternateName` + `sameAs` to the official profiles.
3. If the name is generic (`Delta`, `Pioneer`, `United`) and the page never pairs it with a distinctive category or geo in title/H1: severity `high`, title `Generic brand name without disambiguation in title/H1`. Evidence: title/H1 text and a colliding entity.
4. If no meaningful collisions (unique coined name, or collisions are clearly unrelated and the page disambiguates): no finding.
5. Domain vs brand mismatch (page brand is “Foo”, domain is unrelated dictionary word used by others): severity `medium`, title `Brand name and domain are weakly aligned`, evidence both strings.

### 4. Stale data (copyright years, outdated posts)

**Run staleness_check.py with both static and rendered inputs when available.**

If `crawl-render-audit` has already run and `audit-orchestrator` has passed its rendered snapshot forward, invoke the script with the rendered visible text:

```
python scripts/staleness_check.py {target_url} {audit_date_iso} --rendered-text {path_to_rendered_text_file}
```

If no rendered snapshot is available (Playwright was unavailable or the orchestrator did not pass one forward), invoke without the rendered-text argument:

```
python scripts/staleness_check.py {target_url} {audit_date_iso}
```

The script fetches the page, extracts visible text from static HTML, and — when `--rendered-text` is provided — also runs the same regex checks against the rendered visible text. It returns `findings[]`. Each finding has `check` (`copyright_year` | `dated_content` | `blog_freshness`), `severity`, `title`, `evidence`, `found_in` (`"static"` | `"rendered"`), and `suggested_action`. Thresholds are the ones defined here — the script implements them deterministically:

- Copyright year 1 year behind → severity `medium` (`copyright_year` check)
- Copyright year 2+ years behind → severity `high`
- Dated content framed as current and older than 18 months → severity `high` (`dated_content` check)
- Most recent blog/news post older than 18 months → severity `medium` (`blog_freshness` check)
- Event / pricing / "coming soon" with a past date → severity `high`

When static HTML yields no copyright/dated-content matches but rendered text does, the script runs the same checks against the rendered text and tags results with `"found_in": "rendered"`. This prevents SPA sites from silently returning an empty findings list.

Use the script's `findings[]` directly as this sub-skill's stale-data findings. Promote them to the output array verbatim (add `source_skill` field; do not re-derive severity). **When citing a staleness finding in the evidence string, include the `found_in` value** — e.g. `"Copyright year 2022 found in rendered DOM (SPA site; static HTML contained no copyright text)."` or `"Copyright year 2022 found in static HTML."`

**Do not flag evergreen articles merely because they are old if they are not framed as current news.** If the script flags a date that is clearly in an evergreen article, discard that finding using agent judgment.

Sitemap or listing dates vs on-page dates: if an on-page date suggests active status but a third-party source says the business closed — handle under contradiction in step 2, not here.


## 5. Proactive opportunities (even when checks pass)

After completing steps 1–4, evaluate whether any non-obvious, high-leverage improvement exists even though no defect was found. Only emit an opportunity if concrete on-page or search evidence supports it.

Examples (not exhaustive):

- **Brand corroborated but no Wikipedia page and no Wikidata entry**: the brand exists and its facts check out, but there is no structured knowledge-graph record. AI systems prefer entities with Wikidata Q-numbers for disambiguation.
- **All claims corroborated but `sameAs` not present in the page's JSON-LD**: third-party sources exist (LinkedIn, Crunchbase, Wikipedia), but the site never links to them in structured data. Adding `sameAs` closes the knowledge-graph loop.
- **Name is unambiguous and entity is clearly identified, but no `alternateName`**: if the entity uses an acronym or common short form, adding `alternateName` in schema improves recall in AI-generated summaries.
- **Dates all current but the brand's founding year or "established" date is nowhere on the page or in schema**: notable provenance signals that corroborate longevity are missing from any structured source.

For each opportunity found, emit:

```json
{
  "source_skill": "freshness-corroboration",
  "type": "opportunity",
  "title": "Brand has no Wikidata entity record",
  "severity": "medium",
  "evidence": "Web search found corroborating news and LinkedIn profile for 'Acme Corp', but no Wikipedia article or Wikidata Q-number. AI systems use Wikidata for entity reconciliation.",
  "suggested_action": {
    "summary": "Create a Wikidata entry and, if notable, a Wikipedia article for the brand. Add sameAs links in Organization JSON-LD pointing to these records.",
    "priority": "medium"
  }
}
```

Do not emit an opportunity for the same underlying property if you have already emitted a `"defect"` finding about it.

## Output to the orchestrator

Return **only** a JSON array. Each element:

```json
{
  "source_skill": "freshness-corroboration",
  "type": "defect",
  "title": "On-site claim contradicted by third-party source",
  "severity": "high",
  "evidence": "Site H1 claims HQ in Austin; Companies House / news article at {url} lists registered office in London (2024).",
  "suggested_action": {
    "summary": "Align the public HQ statement with the current registered office or explain regional offices in schema and copy.",
    "priority": "high"
  }
}
```

`type` defaults to `"defect"` if omitted. Empty array if identity is clear, claims match independent sources, the name is unambiguous, and dates are current. Do not assign `id`. Do not implement the suggested action.

