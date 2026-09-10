# Brand AI Readiness Audit

Agentskills.io-compliant skill marketplace for auditing a website’s **AI-readiness**: whether machines can crawl, render, corroborate, and cite the brand—and whether a human visitor can orient, trust, and stay.

Skills are **read-only and recommend-only**. They inspect public pages, robots rules, markup, third-party sources, and on-page UX. They never modify the target site, inject scripts, submit forms, bypass access controls, or implement fixes.

## Marketplace

| Field | Value |
| --- | --- |
| Name | `brand-ai-readiness-audit` |
| Version | `1.0.0` |
| Manifest | `marketplace.json` |
| Entrypoint | `audit-orchestrator` |

Load this folder as a skill pack. When a user supplies a URL (or asks to audit AI discoverability, GEO/AEO, crawlability, or on-site engagement), run **audit-orchestrator**. The orchestrator sequentially runs the three sub-audits and emits a single JSON report.

## Skills

### `audit-orchestrator` (entrypoint)

Accepts a target URL, runs the three sub-skills in order, merges their findings, assigns stable IDs (`F-001`, `F-002`, …), rolls up severity counts, and outputs **only** the final JSON report (no markdown outside that JSON block).

### `crawl-render-audit`

Technical crawlability and machine readability:

1. `robots.txt` allow/disallow (and sitemap pointers).
2. Raw HTML for JSON-LD / schema.org, especially Product, Organization, LocalBusiness, Person, and other entity types.
3. Static HTML vs rendered DOM: core facts that exist only after JavaScript execution.

### `freshness-corroboration`

Trust and recency of brand facts:

1. Identify the core entity/brand.
2. Corroborate on-site claims against Wikipedia, news, and directories.
3. Detect entity ambiguity (other brands sharing the name).
4. Flag stale signals (copyright years, outdated posts, dead dates).

### `engagement-audit`

Human landing experience that also affects bounce and context retention:

1. Immediate orientation in the hero (what the entity is).
2. Information architecture for common AI-style questions (what, where, who, how to buy/contact).
3. Trust signals (legitimacy, identity, proof).

## How the orchestrator composes them

```
URL
 └─► crawl-render-audit        → findings[]
 └─► freshness-corroboration   → findings[]
 └─► engagement-audit          → findings[]
      └─► audit-orchestrator   → one JSON report
```

1. Normalize the URL (scheme, host, trailing slash). Set `site` to the registrable host (e.g. `example.com`).
2. Run **crawl-render-audit** on that URL. Collect raw findings.
3. Run **freshness-corroboration** on the same URL (and home/about if needed for entity identity). Collect raw findings.
4. Run **engagement-audit** as a first-visit human on the same URL. Collect raw findings.
5. Deduplicate overlapping issues, keep the strongest severity, merge evidence.
6. Emit the report schema defined in `skills/audit-orchestrator/SKILL.md`.

No sub-skill writes the final report. Only the orchestrator does.

## Constraints

- Do not change the audited site or its CMS.
- Do not store credentials, scrape behind logins, or ignore `robots.txt` crawl delays in a way that hammers origin.
- Suggested actions are recommendations (`suggested_action`), not applied patches.
- If a check cannot be completed (timeout, block, missing robots), record a finding with evidence of the failure—do not invent markup or third-party citations.

## Running an audit

Provide a public URL, for example:

```text
Audit https://www.example.com for AI readiness
```

The agent loads this marketplace, starts at `audit-orchestrator`, and returns the JSON report.

