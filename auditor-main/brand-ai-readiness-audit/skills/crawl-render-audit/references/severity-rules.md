# Crawl Render Audit — Severity Rules Reference

This file contains the complete severity-mapping tables and rule lists for
`crawl-render-audit/SKILL.md`. The SKILL.md procedure references this file
for the detailed rules; do not change severity values here without updating
the SKILL.md summary as well.

---

## Step 1 — robots.txt severity rules

Script output fields: `fetch.ok`, `fetch.status`, `fetch.error`,
`sitewide_disallow`, `sitemaps[]`, `parsed.raw_line_count`, `evaluation`
(per-agent: `result`, `matched_rule`, `resolved_from_group`).

Tracked agents: `*`, `GPTBot`, `Google-Extended`, `anthropic-ai`, `CCBot`,
`PerplexityBot`, `Applebot-Extended`, `Googlebot`, `Bingbot`.

| Condition | Severity | Title |
|---|---|---|
| `fetch.status == 404` | `medium` | `robots.txt missing` |
| `fetch.ok == false` (5xx / timeout / connection error) | `high` | `robots.txt unreachable` |
| `sitewide_disallow == true` (`Disallow: /` for `*`) | `critical` | `Sitewide robots disallow` |
| Any tracked agent: `result == "disallow"` for target path | `critical` | `Target URL disallowed in robots.txt` |
| `sitemaps[]` is empty | `medium` | `No Sitemap directive in robots.txt` |

**Non-findings:** `Crawl-delay`; `Disallow` of `/llms.txt`, `/api/`, or app-internal paths (unless those paths are the target URL).

---

## Step 2 — JSON-LD / schema.org severity rules

Script output fields: `fetch.*`, `jsonld_parse_errors[]`, `nodes[]`
(per-node: `types[]`, `missing_required_fields[]`, `missing_recommended_fields[]`, `name`, `url`, `id`),
`entity_types_found[]`, `h1`, `title`, `name_h1_mismatch`, `conflicting_names[]`, `conflicting_ids[]`.

Entity types of interest: `Organization`, `LocalBusiness`, `Corporation`, `Brand`, `Person`,
`Product`, `Offer`, `WebSite`, `WebPage`, `FAQPage`, `Article`, `BreadcrumbList`.

### Required fields per type (script validates these)

| Type | Required fields |
|---|---|
| `Organization` | `name`, `url` |
| `LocalBusiness` | `name`, `url`, `address` |
| `Corporation` | `name`, `url` |
| `Brand` | `name` |
| `Person` | `name` |
| `Product` | `name`, `description` |
| `Offer` | `price`, `priceCurrency` |
| `WebSite` | `name`, `url` |
| `WebPage` | `name` |
| `FAQPage` | `mainEntity` |
| `Article` | `headline`, `author` |
| `BreadcrumbList` | `itemListElement` |

### Recommended fields per type (script flags these as missing_recommended)

| Type | Recommended fields |
|---|---|
| `Organization` | `logo`, `sameAs`, `contactPoint` |
| `LocalBusiness` | `telephone`, `openingHours`, `geo` |
| `Product` | `image`, `sku`, `offers` |
| `Person` | `sameAs`, `jobTitle` |

### Severity table

| Condition | Severity | Title |
|---|---|---|
| `fetch.status != 200` (4xx/5xx) | `critical` | _(describe the HTTP error)_ |
| `fetch.status != 200` (3xx loop) | `high` | _(describe the redirect loop)_ |
| `fetch.content_type` not `html` | `high` | _(describe MIME type)_ |
| Any `jsonld_parse_errors[]` entry | `high` | `Malformed JSON-LD` |
| Homepage/brand landing: no entity type found | `critical` | `No entity schema.org markup in raw HTML` |
| Product-like URL: no `Product` or `Offer` | `high` | `Product page missing Product JSON-LD` |
| `name_h1_mismatch != null` | `high` | `Identity mismatch between JSON-LD and visible branding` |
| Node `missing_required_fields` contains `url` | `medium` | _(describe node type + missing field)_ |
| Org-type node `missing_recommended_fields` has `logo` or `sameAs` | `medium` | _(describe missing properties)_ |
| `sameAs` URL returns 404 (spot-check ≤3) | `medium` (per URL) | _(describe dead profile)_ |
| `conflicting_names` non-empty | `high` | `Conflicting entity JSON-LD` |
| `conflicting_ids` non-empty | `high` | `Conflicting entity JSON-LD @id` |

**Non-findings for Step 2:** H1 serving as a marketing value proposition, tagline, or category statement when the brand identity is clearly corroborated in document title, domain, logo, or navigation.

---

## Step 3 — Render diff severity rules

Script output fields: `playwright_available`, `static_facts` (h1, meta_description,
jsonld_block_count, jsonld_names), `rendered_facts` (same shape), `diff[]`
(per-field: `field`, `static_value`, `rendered_value`, `gap_type`), `error`.

`gap_type` values: `"missing_in_static"` | `"mismatch"` | `"match"`.

### Severity table

| `diff[]` field | `gap_type` | Severity | Title |
|---|---|---|---|
| `h1` | `missing_in_static` | `critical` | `Core brand identity only present after JavaScript` |
| `meta_description` | `missing_in_static` | `high` | `Value proposition missing from static HTML` |
| `jsonld_block_count` | `missing_in_static` | `high` | `JSON-LD injected only by JavaScript` |
| `h1` | `mismatch` | `high` | `H1 differs between static HTML and rendered DOM` |
| Any field | `match` | — | No finding |
| SPA: `jsonld_block_count > 0` static + h1 `mismatch` | — | `medium` | `Main content client-rendered but JSON-LD present in raw HTML` |

**Non-findings for Step 3:** Responsive duplicate H1 markup in static HTML that contains or matches the rendered visible H1 is not a render gap. Only flag `mismatch` when the rendered heading has no equivalent representation in the raw HTML.

**Fallback (Playwright unavailable):** inspect raw HTML for `__NEXT_DATA__`,
`window.__NUXT__`, empty `#root`/`#app` with no SSR text.

---

## Additional crawl signals (only if observed)

| Signal | Severity |
|---|---|
| `noindex` in `X-Robots-Tag` or `<meta name="robots">` on a discoverable page | `critical` |
| Canonical pointing at a different host or to homepage for a distinct entity/product URL | `high` |
| Soft 404 (200 with "not found" in H1) | `high` |
