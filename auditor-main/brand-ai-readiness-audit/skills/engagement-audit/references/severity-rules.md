# Engagement Audit — Severity Rules Reference

This file contains the complete severity-mapping tables and rule lists for
`engagement-audit/SKILL.md`. The SKILL.md procedure references this file
for detailed rules; do not change severity values here without updating
the SKILL.md summaries as well.

---

## Step 1 — Immediate orientation (hero) severity rules

**Pass criterion:** specific entity name + concrete category or job-to-be-done + language a stranger can paraphrase — all visible in the first viewport (H1, subhead, primary image caption, primary CTA label).

| Condition | Severity | Title |
|---|---|---|
| No H1, or H1 is decorative/empty | `critical` | `Hero does not name the entity` |
| Name present but no category/purpose | `high` | `Hero does not explain what the entity is` |
| Purpose only below the fold or in carousel slide 2+ | `high` | `Value proposition not in the first viewport` |
| Vague CTA (`Click here`, `Learn more`) **and** purpose unclear | `medium` | `Primary CTA does not communicate next step` |
| Auto-playing video/background with no text pitch equivalent | `high` | _(describe missing text overlay)_ |

If orientation is clear, do not add a hero finding.

---

## Step 2 — Information architecture severity rules

**Check:** can a visitor (or AI) answer each query type within one click from prominent nav, footer, or in-page sections?

| Query type | "Easy" benchmark |
|---|---|
| What is this? | Hero + 1 short about blurb |
| Who is it for? | Audience, industry, or use-case labels |
| What does it cost / how to buy? | Pricing link, product list, or "contact sales" (B2B) |
| How to contact / where are you? | Contact, NAP, or location pages |
| Is it legit / who runs it? | About, team, or company page |
| Help / how it works | FAQ, docs, or how-it-works |

| Condition | Severity | Title |
|---|---|---|
| Answers exist only in PDFs, images-of-text, or 4+ nav levels deep | `high` | `Common questions are buried in the information architecture` |
| No About, Contact, or equivalent in header/footer on commercial/marketing URL | `high` | `No obvious path to About or Contact` |
| Key facts only in chatbot/widget (not in HTML) | `high` | `Primary answers gated behind on-site chat` |
| Internal search required to find basic identity | `medium` | _(describe)_ |
| Multiple competing nav systems, broken anchors, or footer-only essential links | `medium` | _(describe)_ |

Exception: single-purpose legal/utility pages (privacy policy) — judge for their document type.

---

## Step 3 — Trust signals severity rules

| Condition | Severity | Title |
|---|---|---|
| `http://` URL with no HTTPS redirect | `high` | `Page not served on HTTPS` |
| Lorem ipsum, default theme credits, or "your logo here" visible | `critical` or `high` | `Template or placeholder content undermines legitimacy` |
| Site asks for money/accounts/personal data but has no physical/legal identity | `critical` | `No verifiable identity before conversion` |
| Fake-feeling urgency (countdown, "99 viewing now") with no company identity | `high` | _(describe urgency signal)_ |
| Testimonials with no names/orgs and no other trust layer | `medium` | _(describe)_ |

**Non-finding:** absence of press logos on a small site does not alone trigger a finding. Absence of **any** of: address, about, contact, or legal name is sufficient.

---

## Bounce-risk and context retention severity rules

| Condition | Severity | Title |
|---|---|---|
| One click leads to a page that never repeats the entity name | `high` | `Entity context is not retained past the landing view` |
| Full-screen popup blocks content before orientation | `high` | `Interstitial blocks first-visit orientation` |
| Cookie banner covers hero value proposition and cannot be dismissed without tracking consent | `high` | _(note overlay as evidence; do not dismiss)_ |
