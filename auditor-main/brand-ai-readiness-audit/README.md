# Brand AI-Readiness Audit Marketplace

The **Brand AI-Readiness Audit Marketplace** is a read-only, recommend-only Agent Skill Marketplace built to audit how effectively public websites can be discovered, crawled, understood, corroborated, and trusted by modern AI systems (such as SearchGPT, Perplexity, Gemini, Claude, and ChatGPT), as well as how smoothly visitors referred by AI answers can orient and engage on-site. The marketplace executes deterministic technical checks alongside structured reasoning to generate an evidence-based, fully validated JSON audit report.

---

## 2. What Problem Does It Solve?

Modern AI search engines and answer engines do not browse the web like human users, nor do they index content like legacy keyword crawlers. Websites face two distinct failure modes in the AI era:

### A. Off-Site AI Discoverability
An AI engine may fail to cite, summarize, or recommend a brand because:
- **Crawl Blocks & AI Disallows**: `robots.txt` directives explicitly block key AI crawlers (`GPTBot`, `OAI-SearchBot`, `Google-Extended`, `anthropic-ai`, `PerplexityBot`, `CCBot`, `Applebot-Extended`) or catch-all routing serves an HTML page in place of a valid `robots.txt`.
- **Missing or JS-Gated Core Content**: Single Page Applications (SPAs) serve an empty `<div id="root"></div>` shell to crawlers without executing JavaScript, leaving core brand identity, headings, and value propositions invisible to non-rendering crawlers.
- **Structured Data Absence or Malformation**: Absence of schema.org markup (`Organization`, `SoftwareApplication`, `Product`, `LocalBusiness`), unparseable JSON-LD, or conflicting `@id` and `name` attributes prevent machines from building an unambiguous knowledge-graph entity.
- **Brand Identity & Entity Ambiguity**: Shared or generic brand names collide with unrelated entities across the web without disambiguating qualifiers (`alternateName`, distinct category signifiers, official `sameAs` links).
- **Weak Third-Party Corroboration**: Key on-site claims (founding date, awards, leadership, market position) lack independent verification in public directories, news, or authoritative databases.
- **Stale Temporal Signals**: Outdated copyright years, legacy blog dates, or expired events undermine AI confidence in fact recency.

### B. On-Site AI-Referral Engagement
When an AI engine references a site and sends a human visitor via a citation link, the user arrives with specific context and high expectations. Visitors bounce if:
- **Hero Orientation Failure**: The initial viewport fails to communicate what the entity is, what product or service is offered, or what job it does.
- **Information Architecture Gaps**: Answers to fundamental questions (About, Pricing, Contact, Documentation, Legal Ownership) are gated behind chat widgets, hidden behind multi-tier menus, or absent.
- **Weak Trust & Legitimacy Signals**: Lack of verifiable creator/organization identity, missing contact paths, or unanchored marketing claims create friction and bounce risk.

---

## 3. Key Features

- **Robots.txt & Sitemap Evaluation**: Validates HTTP status, confirms plain-text MIME validity (preventing SPA catch-all false-positives), and evaluates explicit `Allow`/`Disallow` rules for general bots and AI agents (`*`, `GPTBot`, `OAI-SearchBot`, `Google-Extended`, `anthropic-ai`, `CCBot`, `PerplexityBot`, `Applebot-Extended`, `Googlebot`, `Bingbot`) using standard longest-match semantics.
- **Dual-Layer DOM & Render Inspection**: Inspects both raw static HTML and browser-rendered DOM via headless Playwright to uncover Client-Side Rendering (CSR) gaps.
- **Headless Browser Rendering**: Evaluates actual rendered content, heading elements, and body copy using modern browser automation.
- **Static vs. Rendered DOM Diffing**: Directly compares headings (`H1`), meta descriptions, and structured data blocks between raw static responses and rendered state.
- **Schema.org & JSON-LD Validation**: Extracts and parses all embedded JSON-LD blocks, validates required and recommended entity properties, flags malformed syntax, and detects conflicting entity IDs.
- **Entity Identity Coherence**: Evaluates alignment across schema markup, title tags, domains, and visible headings—avoiding false-positive flags on legitimate marketing slogans.
- **Entity Ambiguity & Name Collision Detection**: Identifies competing brands or namesake entities in similar market categories.
- **Third-Party Web Corroboration**: Evaluates independent web footprint and verifies high-stakes on-site claims.
- **Temporal Staleness Detection**: Detects outdated copyright dates, stale news updates, and unanchored past events.
- **Human-Centric AI-Referral UX Review**: Assesses hero orientation, first-click information architecture, and trust signals.
- **Evidence-Based Findings**: Every finding is backed by concrete proof—quoted text, HTTP status codes, missing fields, or selector values.
- **Strict Severity Classification**: Standardized severity levels (`critical`, `high`, `medium`) for defects and a dedicated `medium` tier for proactive opportunities.
- **Actionable Remediation**: Every issue includes a concrete `suggested_action` with prioritized recommendations (`high`, `medium`, `low`).
- **Deterministic Aggregation & Sequential IDs**: Deduplicates genuine overlaps without merging distinct issues, sorts defects by severity, and numbers findings cleanly (`F-001`, `F-002`, ...).
- **Report Integrity Validation**: Programmatically guarantees `summary.total_findings == len(findings)`, severity counts match exactly, and fields remain isolated without contamination.
- **Read-Only & Recommend-Only**: Strictly non-destructive. Never writes to target sites, bypasses logins, or submits forms.

---

## 4. Architecture

The marketplace adheres to the **Agentskills.io** specification. The entrypoint skill `audit-orchestrator` coordinates the specialist sub-skills, collects their findings, passes them through the programmatic aggregator, and outputs the final report.

```text
User / Agent Harness
        ↓
[audit-orchestrator] (Single Entrypoint)
        │
        ├─► 1. crawl-render-audit
        │       ├── robots_check.py   (robots.txt, sitemaps, AI crawlers)
        │       ├── jsonld_check.py   (Schema.org, JSON-LD, entity coherence)
        │       └── render_diff.py    (Playwright static vs. rendered DOM)
        │
        ├─► 2. freshness-corroboration
        │       └── staleness_check.py (Copyright years, dated content, recency)
        │
        ├─► 3. engagement-audit
        │       └── On-site orientation, IA navigation, trust signals
        │
        ▼
[aggregate_report.py] (Deterministic Normalization & Integrity Validation)
        │   - Exact deduplication
        │   - Severity sorting (critical -> high -> medium -> opportunities)
        │   - Sequential ID assignment (F-001, F-002, ...)
        │   - Summary recalculation from final findings array
        │   - Schema & field boundary verification
        ▼
Validated JSON Report (stdout)
```

### Skills Breakdown

1. **`audit-orchestrator`** (`skills/audit-orchestrator/`):
   The primary entrypoint. Coordinates the sequential pipeline, manages intermediate state (e.g. passing rendered text snapshots), executes aggregation and validation, and emits the final JSON report.
2. **`crawl-render-audit`** (`skills/crawl-render-audit/`):
   Technical foundation audit covering crawl access, AI bot policies, schema markup, and JavaScript rendering disparities.
3. **`freshness-corroboration`** (`skills/freshness-corroboration/`):
   Entity corroboration and trust audit assessing whether independent sources corroborate claims, detecting name collisions, and finding stale dates.
4. **`engagement-audit`** (`skills/engagement-audit/`):
   Human-factor audit assessing first-viewport hero clarity, one-click accessibility of key information, and organizational legitimacy.

---

## 5. Repository Structure

```text
brand-ai-readiness-audit/
├── marketplace.json                        # Agentskills.io marketplace manifest
├── README.md                               # Project documentation & operational manual
└── skills/
    ├── audit-orchestrator/
    │   ├── SKILL.md                        # Entrypoint skill instructions & constraints
    │   └── scripts/
    │       ├── aggregate_report.py         # Programmatic findings aggregator & validator
    │       └── run_audit.py                # End-to-end automated audit runner
    ├── crawl-render-audit/
    │   ├── SKILL.md                        # Technical crawl & render audit instructions
    │   ├── references/
    │   │   └── severity-rules.md           # Defect mapping rules & severity definitions
    │   └── scripts/
    │       ├── jsonld_check.py             # Schema.org JSON-LD validator & identity check
    │       ├── render_diff.py              # Playwright DOM vs. static HTML comparison
    │       └── robots_check.py             # robots.txt parser & AI crawler evaluator
    ├── freshness-corroboration/
    │   ├── SKILL.md                        # Brand corroboration & freshness instructions
    │   └── scripts/
    │       └── staleness_check.py          # Temporal staleness & copyright date checker
    └── engagement-audit/
        ├── SKILL.md                        # On-site orientation & UX review instructions
        └── references/
            └── severity-rules.md           # Engagement & bounce risk severity rules
```

---

## 6. Prerequisites & Installation

### System Requirements
- **Python**: 3.10 or higher
- **Node.js**: (Optional, only if using external Playwright drivers)
- **Linux, macOS, or Windows (WSL recommended)**

### 1. Clone the Repository
```bash
git clone https://github.com/your-org/brand-ai-readiness-audit.git
cd brand-ai-readiness-audit
```

### 2. Create and Activate Virtual Environment
```bash
python3 -m venv venv
source venv/bin/activate
```

### 3. Install Dependencies
All audit scripts are built with zero heavy external frameworks, using Python's standard library for HTTP parsing, regex, and HTML processing. The only external package is **Playwright** for headless browser DOM rendering.

```bash
pip install playwright
playwright install chromium
```

---

## 7. How to Run Audits

### Option A: End-to-End Audit Runner (Command Line)

> **Note:** This runner script is a local development and testing convenience, not the primary or required way to run the marketplace. The marketplace itself is designed to run via Agent Skill execution (Option B), per the agentskills.io marketplace format. Additionally, `run_audit.py`'s corroboration checks use a basic standalone web-search implementation and may report "corroboration check incomplete" more often than Option B, which uses the host agent's own search tooling.

Run a complete, automated audit on any public website:

```bash
python3 skills/audit-orchestrator/scripts/run_audit.py https://example.com/
```

This command will:
1. Execute all specialist scripts sequentially against `https://example.com/`.
2. Render the page using headless Chromium.
3. Log execution and specialist breakdown to `stderr`.
4. Output the final, validated JSON report to `stdout`.

To redirect the JSON report to a file while viewing debug progress in the terminal:
```bash
python3 skills/audit-orchestrator/scripts/run_audit.py https://example.com/ > audit_report.json
```

### Option B: Agent Skill Execution
If you are using an Agent runner (e.g. Antigravity IDE, Claude Desktop, or an agent harness conforming to the `agentskills.io` standard):
1. Mount or point your agent to `brand-ai-readiness-audit/`.
2. Provide the prompt:
   ```text
   Run the brand AI-readiness audit on https://example.com/ using audit-orchestrator as the entrypoint.
   ```
3. The orchestrator will read `skills/audit-orchestrator/SKILL.md`, execute sub-skills in sequence, aggregate findings, and return the report.

### Option C: Running Specialist Scripts Individually

Each specialist script can be executed standalone for testing or targeted analysis:

#### 1. Robots.txt & AI Crawler Analysis
```bash
python3 skills/crawl-render-audit/scripts/robots_check.py https://example.com/
```
*Outputs JSON with MIME validation, sitemaps, and allow/disallow evaluation across all tracked AI bots (`GPTBot`, `OAI-SearchBot`, `PerplexityBot`, etc.).*

#### 2. JSON-LD & Structured Data Inspection
```bash
python3 skills/crawl-render-audit/scripts/jsonld_check.py https://example.com/
```
*Outputs JSON with extracted nodes, Schema.org validation errors, entity types, and heading coherence.*

#### 3. Static HTML vs. Rendered DOM Comparison
```bash
python3 skills/crawl-render-audit/scripts/render_diff.py https://example.com/
```
*Launches Chromium, captures rendered text and elements, and outputs a diff against raw static HTML.*

#### 4. Staleness & Freshness Verification
```bash
# Save rendered text first if auditing an SPA
python3 skills/freshness-corroboration/scripts/staleness_check.py https://example.com/ 2026-09-11 --rendered-text rendered_text.tmp
```
*Outputs JSON with detected copyright years, blog publish dates, and staleness evaluations relative to the audit date.*

#### 5. Report Aggregator & Validator
```bash
python3 skills/audit-orchestrator/scripts/aggregate_report.py raw_findings.json "example.com" "2026-09-11T12:00:00Z"
```
*Reads raw specialist findings, deduplicates, sorts, numbers IDs (`F-001`...), validates schema integrity, and prints the report.*

---

## 8. Output Schema & Example Report

The orchestrator produces a single JSON object with the following schema:

```json
{
  "site": "typequest-pro.vercel.app",
  "audited_at": "2026-09-11T14:43:49Z",
  "summary": {
    "total_findings": 8,
    "critical": 1,
    "high": 4,
    "medium": 2,
    "opportunities": 1
  },
  "findings": [
    {
      "id": "F-001",
      "type": "defect",
      "title": "No entity schema.org markup in raw HTML or rendered DOM",
      "severity": "critical",
      "evidence": "jsonld_check.py: jsonld_blocks_found=0, entity_types_found=[], nodes=[]. render_diff.py: rendered jsonld_block_count=0. No Organization, SoftwareApplication, or any schema.org type present anywhere. Static HTML is an SPA shell (<div id='root'></div>). The app has no structured entity identity at all.",
      "suggested_action": {
        "summary": "Add a SoftwareApplication JSON-LD block (name: TypeQuest, applicationCategory: EducationalApplication, operatingSystem: Web) and an Organization block. Inject via <script type='application/ld+json'> in the <head>.",
        "priority": "high"
      }
    },
    {
      "id": "F-002",
      "type": "defect",
      "title": "Core brand identity (H1) only present after JavaScript",
      "severity": "high",
      "evidence": "render_diff.py: static h1=None, rendered h1='typequest'. Static HTML body is empty (<div id='root'></div>). The brand name is injected only by the React bundle. Crawlers without JS execution see no H1 and no body text.",
      "suggested_action": {
        "summary": "Add server-side rendering (Next.js or Vite SSR) or pre-render the landing page so the H1 'TypeQuest' and app description are present in the raw HTML response without JavaScript execution.",
        "priority": "high"
      }
    },
    {
      "id": "F-006",
      "type": "defect",
      "title": "No Sitemap directive in robots.txt",
      "severity": "medium",
      "evidence": "robots_check.py: robots.txt returned HTTP 200, sitemaps=[], sitemap_count=0. The file has 14 lines covering 5 agent groups, but no Sitemap: directive. Without a sitemap, crawlers must rely solely on link discovery.",
      "suggested_action": {
        "summary": "Create a sitemap.xml covering all public pages and add 'Sitemap: https://typequest-pro.vercel.app/sitemap.xml' to robots.txt.",
        "priority": "medium"
      }
    },
    {
      "id": "F-008",
      "type": "opportunity",
      "title": "meta_description is present in static HTML but not surfaced in structured data",
      "severity": "medium",
      "evidence": "Static HTML contains a well-written <meta name='description'> ('A premium typing practice app that helps you learn and revise topics while improving your typing speed. Powered by local AI.') and og:description. However, there is no SoftwareApplication or WebApplication JSON-LD that mirrors this description as schema.org 'description'. The meta description is a strong asset being under-utilized for AI structured comprehension.",
      "suggested_action": {
        "summary": "Add a SoftwareApplication JSON-LD block that mirrors the existing meta description and og:title, and includes applicationCategory, url, and featureList (e.g., AI-powered, educational topics, typing speed modes).",
        "priority": "medium"
      }
    }
  ]
}
```

### Schema Constraints
- **`site`**: Registrable domain without protocol or path (e.g., `"example.com"`).
- **`audited_at`**: UTC ISO-8601 timestamp with `Z`.
- **`summary.total_findings`**: Must strictly equal `len(findings)`.
- **`findings[].id`**: Strictly sequential format matching `^F-[0-9]{3}$`.
- **`findings[].type`**: `"defect"` (broken/missing capability) or `"opportunity"` (passing check with high-leverage improvement).
- **`findings[].severity`**: `"critical"`, `"high"`, or `"medium"`. Opportunity findings are restricted to `"medium"`.
- **`findings[].evidence`**: Concrete observations, status codes, selectors, or quoted text.
- **`suggested_action.summary`**: Actionable remediation starting with an imperative verb (`Add`, `Configure`, `Update`, etc.).
- **`suggested_action.priority`**: `"high"`, `"medium"`, or `"low"`.

---

## 9. Severity Rules & Evaluation Matrix

| Severity | Defect Criteria | Opportunity Criteria |
| :--- | :--- | :--- |
| **`critical`** | Complete block of AI systems or search crawlers; sitewide disallow; absent/invalid core entity schema on commercial homepage; static HTML completely empty for core facts. | *N/A (Opportunities cannot be critical)* |
| **`high`** | Major AI crawler specifically blocked; CSR gap where core identity or meta tags require JS; severe entity ambiguity; uncorroborated defining claims; hero fails to explain what the brand does. | *N/A (Opportunities cannot be high)* |
| **`medium`** | Secondary gaps; missing robots.txt sitemap directive; missing recommended schema fields (`sameAs`, `logo`); stale copyright year; buried contact/about links. | Passing checks where high-leverage enhancements exist (e.g., mirroring meta description into JSON-LD, enriching `sameAs` links). |

---

## 10. Operational Guardrails

- **Non-Destructive**: Read-only inspections only. No test form submissions, cart checkouts, or mutating requests.
- **Ethical Crawling**: Honors robots.txt crawl delays and limits fetch timeouts to prevent denial-of-service or origin strain.
- **Privacy & Authentication**: Never attempts to bypass basic authentication, paywalls, or private portals.
- **Recommendation Only**: Generates prescriptive remediation advice in `suggested_action` without applying direct codebase patches.

---

## 11. Known Limitations

- **Dual-Critical Tie-Breaking in Compilation**: The orchestrator's compile step does not yet have a fully deterministic tie-breaking rule for two simultaneous "critical" findings from different sub-skills when evidentiary richness differs between runs (e.g., search-tool availability). Both findings should remain independently critical; in rare cases one may be reported as "high" instead. This does not affect finding accuracy or evidence, only severity-label placement in ambiguous dual-critical cases.
- **Reasoning-Driven Engagement Checks**: `engagement-audit`'s checks are currently reasoning-driven rather than script-backed. Determinism has been validated empirically across repeated test runs on multiple sites, but is not structurally guaranteed the way the scripted checks in `crawl-render-audit` and `freshness-corroboration` are.
