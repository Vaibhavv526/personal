---
name: audit-orchestrator
description: Entrypoint for the brand AI-readiness marketplace. Takes a public URL, sequentially runs crawl-render-audit, freshness-corroboration, and engagement-audit, then compiles a single JSON findings report. Use when the user asks to audit a website for AI discoverability, GEO/AEO, crawl/render gaps, fact freshness, entity corroboration, or on-site engagement, or when they provide a URL to this marketplace.
license: MIT
allowed-tools: http-fetch
---

# Audit Orchestrator

Entrypoint skill. Read-only and recommend-only. Do not edit the target site. Do not implement fixes. Do not print markdown, commentary, or code fences around the final report when this skill is **executed**.

## Inputs

Accept a single target URL from the user (query, pasted link, or “audit this site”).

1. Trim whitespace. If the scheme is missing, assume `https://`.
2. Parse host. Set `site` to the registrable domain without `www.` (e.g. `https://www.example.com/path` → `example.com`). Keep the full canonical URL internally as `target_url`.
3. If the input is not a URL, ask once for a URL. Do not invent a domain.
4. Record `audited_at` as the current UTC time in ISO-8601 with `Z` (`YYYY-MM-DDTHH:MM:SSZ`).

## Execution order (mandatory)

Run the three sub-skills **sequentially** on the same `target_url`. Read and follow each skill’s `SKILL.md` fully before starting that phase.

1. **crawl-render-audit** (`skills/crawl-render-audit/SKILL.md`)  
   Technical crawlability, robots, JSON-LD/schema.org, static vs rendered DOM.  
   After `render_diff.py` completes, **retain its output** for the next phase:
   - `output.static_text` — visible text from the raw static HTML.
   - `output.rendered_text` — full visible body text from the Playwright-rendered DOM (`null` if Playwright was unavailable or the render failed).  
   Write `rendered_text` to a temporary UTF-8 file (e.g. `rendered_text.tmp`) so it can be passed to `staleness_check.py` in step 2. If `rendered_text` is `null`, do not create the file.

2. **freshness-corroboration** (`skills/freshness-corroboration/SKILL.md`)  
   Core entity, third-party corroboration, name collision, stale dates.  
   **Snapshot hand-off**: pass the `rendered_text.tmp` file path (if it exists) to `staleness_check.py` via the `--rendered-text` argument. This lets the staleness script detect copyright years and dated content in JavaScript-rendered pages (SPAs) where the static HTML shell contains no visible text. Do not re-fetch or re-render the page independently.

3. **engagement-audit** (`skills/engagement-audit/SKILL.md`)  
   Hero orientation, IA for AI-style questions, trust signals.

Do not skip a sub-skill because another already found issues. Each skill owns a different evidence class.

If a sub-skill cannot finish a check, keep its partial findings and add an orchestrator finding only when the entire sub-skill failed (no usable evidence). Severity: `high`. Title: `Sub-skill incomplete`. Evidence: which skill and why (HTTP status, robots block, timeout, tool unavailable).

## Finding object from sub-skills

Each sub-skill returns a list of objects with at least:

| Field | Rule |
| --- | --- |
| `type` | `"defect"` (something broken/missing) or `"opportunity"` (passes but high-leverage improvement exists). Defaults to `"defect"` if absent. |
| `title` | Short, specific, no severity word in the title |
| `severity` | Exactly one of `critical`, `high`, `medium` |
| `evidence` | Concrete: quoted text, URL, HTTP status, selector, missing field, search result title |
| `suggested_action.summary` | Actionable recommendation (what a human should change) |
| `suggested_action.priority` | `high`, `medium`, or `low` |
| `source_skill` | `crawl-render-audit`, `freshness-corroboration`, or `engagement-audit` |

Sub-skills must not assign final `id` values. The orchestrator assigns IDs.

### `type` rules

- `"defect"`: The check found a missing or broken signal. All `critical` and `high` findings must be `"defect"`. A `medium` finding may be a defect or an opportunity.
- `"opportunity"`: The check passed cleanly, but there is a non-obvious, high-leverage improvement available. Must be severity `"medium"` only. Must include concrete evidence of what currently exists and what could be improved.

### Severity mapping (if a sub-skill is vague)

- **critical**: AI systems or crawlers are blocked from the page/site, or identity markup is absent/wrong on a commercial entity homepage, or the page is empty/unusable without JS for core facts.
- **high**: Major discoverability, corroboration, or bounce-risk gap with clear evidence.
- **medium**: Partial, inconsistent, or secondary gaps (weak schema, stale footer year, buried FAQ). Also the only severity level for `"opportunity"` findings.

Never use `low` or `info` in the compiled report. Drop purely cosmetic notes, or promote them to `medium` only if they affect AI citation or first-visit understanding.

## Compile the report

1. **Collect complete findings**: Collect every valid finding returned by each specialist sub-skill (`crawl-render-audit`, `freshness-corroboration`, `engagement-audit`). Do not discard findings merely because they have different types or source skills.
2. **Deduplicate strictly overlapping findings only**: Two findings are overlapping only if they represent the exact same issue (identical normalized title and same `type`). Keep the finding with the higher severity (or first if equal). **Never merge fields from different findings** — each finding must remain an independent object. Do not append, splice, or mix evidence or `suggested_action` across findings.
3. **Sort**: defects first (`critical` → `high` → `medium`), then opportunities (`medium` only). Stable sort preserving original discovery order within a tier.
4. **Assign sequential IDs**: Assign `id` as `F-001`, `F-002`, `F-003`, … zero-padded to three digits, in sorted order across both defects and opportunities with no gaps or missing IDs.
5. **Recalculate summary counts directly from the final findings array**: Never preserve an earlier or stale count.
   - `total_findings` = `len(findings)`
   - `critical` / `high` / `medium` = exact counts of those severities among `defects`
   - `opportunities` = count of findings where `type == "opportunity"`
6. **Strict field isolation**: Each emitted finding must be an independent object containing strictly: `id`, `type`, `title`, `severity`, `evidence`, and `suggested_action` (with `summary` and `priority`). No finding may contain another finding's evidence or suggested action.
7. **Automated serialization and validation**: Execute `python3 skills/audit-orchestrator/scripts/aggregate_report.py` to aggregate, sort, number, calculate summary counts, and validate integrity.
8. **Integrity checks before emission**:
   - `summary.total_findings == len(findings)`
   - counts of critical, high, medium defects, and opportunities match summary exactly
   - all IDs are sequential `F-001` through `F-{N:03d}` with no missing IDs
   - every finding object conforms to the schema independently
   - if validation fails, repair internally and re-validate; never emit an invalid report.

If there are zero findings, emit `findings: []` and all summary counts `0`. Do not invent issues to fill the array.

## Output schema (exact)

When this skill is executed, the **entire assistant message** must be a single JSON object matching this schema. No markdown before or after. No prose. No ``` fences.

```json
{
  "site": "example.com",
  "audited_at": "2026-09-20T14:32:00Z",
  "summary": { "total_findings": 0, "critical": 0, "high": 0, "medium": 0, "opportunities": 0 },
  "findings": [
    {
      "id": "F-001",
      "type": "defect",
      "title": "String",
      "severity": "critical | high | medium",
      "evidence": "Concrete evidence found by the sub-skill",
      "suggested_action": { "summary": "Actionable fix", "priority": "high" }
    },
    {
      "id": "F-002",
      "type": "opportunity",
      "title": "String",
      "severity": "medium",
      "evidence": "What currently exists and what could be improved",
      "suggested_action": { "summary": "Improvement recommendation", "priority": "medium" }
    }
  ]
}
```

### Field constraints

- `site`: hostname only, no scheme, no path, no trailing slash.
- `audited_at`: UTC `Z` timestamp of this run, not a placeholder.
- `findings[].id`: `^F-[0-9]{3}$`.
- `findings[].type`: `"defect"` or `"opportunity"`. Required on every emitted finding.
- `findings[].severity`: only `critical`, `high`, or `medium`.
- `findings[].severity` when `type == "opportunity"`: must be `"medium"` only.
- `findings[].evidence`: non-empty string; cite what was observed, not what "might" be true.
- `suggested_action.summary`: recommend-only; start with a verb (Add, Expose, Align, Update, Surface, Consider).
- `suggested_action.priority`: `high`, `medium`, or `low`.
- `summary.opportunities`: count of findings with `type == "opportunity"`.

## Guardrails

- Do not fetch authenticated, paywalled, or clearly private URLs.
- Honor `robots.txt` for crawling additional paths; the homepage URL the user gave may still be fetched for audit.
- Do not run exploits, scanners, or load tests.
- Do not output patches, HTML to paste, or CMS login steps—only `suggested_action.summary` recommendations.
