---
name: engagement-audit
description: Audits a URL for on-site orientation, bounce-risk, and context retention by evaluating hero clarity, information architecture for common AI-style questions, and trust signals. Triggers when given a URL to review landing UX, bounce risk, or first-visit comprehension, or when invoked by audit-orchestrator.
license: MIT
allowed-tools:
  - http-fetch
  - browser-render
---

# Engagement Audit

Sub-skill of brand-ai-readiness-audit. Read-only and recommend-only. Act as a **human visitor** landing on the page for the first time (no brand prior knowledge except the URL). Return a **raw list of findings** to `audit-orchestrator`. Do not emit the final marketplace JSON report. Do not modify the site. Do not click destructive actions; viewing the page and reading publicly linked About/Contact/FAQ is allowed.

## Goal

Judge whether a first-time visitor (and an AI summarizing the visit) can immediately tell what the entity is, find answers to ordinary questions without hunting, and trust that the site is legitimate.

## Inputs

- `target_url` from the orchestrator.
- Use rendered view if available; otherwise static HTML plus obvious visible copy. Cookie banners that cover the hero count as orientation failure if the value proposition is not readable without dismissing (do not dismiss if that requires agreeing to non-essential tracking; note the overlay as evidence).

## Procedure

Full severity-mapping tables are in [`references/severity-rules.md`](references/severity-rules.md).

### 1. Immediate orientation (hero)

**Does the hero (first viewport: H1, subhead, primary image/video caption, primary CTA label) explain exactly what the entity is?**

Pass requires all three: specific entity name · concrete category or job-to-be-done · language a stranger can paraphrase in one sentence.

Key severity rules:
- No H1 or H1 decorative/empty → `critical` · `Hero does not name the entity`
- Name present but no category/purpose → `high` · `Hero does not explain what the entity is`
- Purpose only below the fold or in carousel slide 2+ → `high` · `Value proposition not in the first viewport`
- Vague CTA with unclear purpose → `medium` · `Primary CTA does not communicate next step`
- Auto-playing video with no text pitch → `high`

If orientation is clear, do not add a hero finding.

### 2. Information architecture (answers vs buried)

Can a visitor (or AI) answer common queries within one click from prominent nav, footer, or in-page sections?

Query types to check: What is this? · Who is it for? · Cost/how to buy? · Contact/location? · Legitimacy/who runs it? · Help/how it works?

Key severity rules:
- Answers only in PDFs, images-of-text, or 4+ nav levels → `high` · `Common questions are buried in the information architecture`
- No About or Contact in header/footer on commercial URL → `high` · `No obvious path to About or Contact`
- Key facts only in chatbot (not in HTML) → `high` · `Primary answers gated behind on-site chat`
- Internal search required for basic identity → `medium`
- Competing nav systems, broken anchors, footer-only links → `medium`

Exception: single-purpose legal/utility pages — judge for their document type.

### 3. Trust signals (legitimacy)

Look for clear legitimacy indicators appropriate to the entity type: legal name matching domain, physical address/service area (if local), non-form-only contact, policy links (if collecting data), third-party proof (press, reviews, certs) — only as present.

Key severity rules:
- `http://` with no HTTPS redirect → `high` · `Page not served on HTTPS`
- Lorem ipsum / default theme credits / "your logo here" → `critical` or `high` · `Template or placeholder content undermines legitimacy`
- Site requests money/accounts/personal data with no legal identity → `critical` · `No verifiable identity before conversion`
- Fake urgency (countdown, "99 viewing now") with no identity → `high`
- Unnamed testimonials with no other trust layer → `medium`

Non-finding: absence of press logos alone. Absence of **any** of: address, about, contact, or legal name is sufficient for a finding.

## Bounce-risk and context retention (derived from 1–3)

- One click leads to a page that never repeats the entity name → `high` · `Entity context is not retained past the landing view`
- Full-screen popup blocking content before orientation → `high` · `Interstitial blocks first-visit orientation`

## 4. Proactive opportunities (even when checks pass)

After completing the orientation, IA, and trust checks above, evaluate whether there is a non-obvious, high-leverage improvement even though the page is not failing any check. Only emit an opportunity if concrete on-page evidence supports it.

Examples (not exhaustive):

- **Hero passes orientation but value proposition is generic**: the page names the entity and category but uses vague benefit language ("Transform your workflow") rather than a memorable, differentiated one-liner a stranger could repeat. Even with a passing score, a sharper value prop improves AI summary quality and first-visit retention.
- **IA check passes but FAQ is fully on-page text yet not marked up as FAQPage JSON-LD**: answers are accessible, but AI systems cannot extract them as structured Q&A pairs for direct answers in AI Overviews or featured snippets.
- **Trust section has a "Press" logo grid but no link to actual articles**: logos add credibility but do not provide AI-citable evidence; linking to the source articles would enable corroboration.
- **Contact method exists but is only a web form with no email or phone visible**: passes the "not chat-only" test, but a direct contact point improves crawlability and trust for AI-generated contact summaries.
- **About page is reachable in one click but duplicates the homepage value prop instead of adding depth**: the IA check passes, but the About page is a missed opportunity to expose founding story, leadership, and mission for AI citation.

For each opportunity found, emit:

```json
{
  "source_skill": "engagement-audit",
  "type": "opportunity",
  "title": "Hero value proposition is generic despite naming the entity",
  "severity": "medium",
  "evidence": "H1 is 'Acme Corp' and subhead is 'Transform your workflow'. Orientation check passes, but no differentiated benefit or audience is stated. A stranger cannot describe Acme's specific niche.",
  "suggested_action": {
    "summary": "Rewrite the subhead to state a specific, differentiated benefit or audience in one sentence, e.g. 'The only contract-intelligence platform built for mid-market procurement teams.'",
    "priority": "medium"
  }
}
```

Do not emit an opportunity for the same underlying property if you have already emitted a `"defect"` finding about it.

## Output to the orchestrator

Return **only** a JSON array. Each element:

```json
{
  "source_skill": "engagement-audit",
  "type": "defect",
  "title": "Hero does not explain what the entity is",
  "severity": "high",
  "evidence": "H1 is 'Welcome back'. Subhead is 'The future is yours'. First viewport has no category, product, or audience.",
  "suggested_action": {
    "summary": "Put the brand name and a one-sentence description of what the organization does in the H1 and subhead of the first viewport.",
    "priority": "high"
  }
}
```

`type` defaults to `"defect"` if omitted. Empty array if orientation, IA, and trust are adequate for a first visit. Do not assign `id`. Do not implement the suggested action. Do not rewrite the page.
