> The plan written before the event, for a Next.js build. The shipped app is the Ninoo Builder
> build in this repository (React + FastAPI); see the README for what it does today.

# SPEC: Portfolio Pulse

## Users
Associates and platform teams at VC funds. Emerging managers with no ops staff.

## Data model
- Fund { slug, name, sourceUrl, companies: Company[] }
- Company { name, website, aktaId?, profile?: { firmographic, strategicSignal, management,
  financialEstimate }, events: Event[], pulse: number }
- Event { id, companyId, date, title, summary, url, publisher, sentiment, newsScore,
  tags: { code, name, isPrimary }[], category, severity: 1 | 2 | 3, suggestedAction, source: "akta" }
- Draft { eventId, kind: "founder_email" | "partner_note", text, citations: { n, url }[] }
- LPUpdate { fundSlug, quarter, highlights, watchlist, citations: { n, url }[] }

## akta.pro calls (src/lib/akta.ts)
REST base https://api.akta.pro/api/v1, header `x-api-key`. Confirm response field names against the
saved responses in fixtures/akta/ before writing zod schemas.

| Call | Purpose | Credits | Cache |
| --- | --- | --- | --- |
| GET /company/search/?query=<website or name> | Resolve a company to its akta UUID | 0 | forever |
| GET /company/enrichment/?company=<website or uuid>&sections=firmographic,strategic_signal,management_profile,financial_estimate | Profile for the card and the LP update | 5 (2 + 1.5 + 1 + 0.5) | forever |
| GET /news/?primary_company=<website or uuid>&start_date=<today minus 90 days>&limit=20&group_articles=true | Events. `primary_company` keeps only articles mainly about the company (cannot be combined with `company`) | 0.1 + 0.01 per article | 24 hours |
| https://playground.akta.pro/news-tags.csv | The tag list the signal engine maps | 0 | saved to data/news-tags.csv |

Response shapes, from docs/akta-openapi.json and docs.akta.pro/company-data-dictionary.md (confirm
against the fixtures before writing zod schemas; make unknown fields optional):
- search 200: `{ data: [{ uuid, name, website, product_category, company_status }], credits_consumed }`.
  `company_status` is public, private, acquired, delisted or unknown. 204 means no match.
- enrichment 200: `{ status, data, count, credits_consumed }`. `data` is untyped in the spec; expect one
  key per requested section:
  - firmographic: name, legal_name, website, company_type, founded_year, company_description,
    company_description_short, operating_status {code, label}, ownership_category {code, label},
    headcount_range, logo_url.
  - strategic_signal: scale_indicator[], partnership[], recent_move[] {type, description, date, source},
    leadership_change[] {title, description, type, source}, expansion_highlight[].
  - management_profile: number_of_profiles, profiles[] {name, designation, designation_category,
    overview, start_date, source}.
  - financial_estimate: revenue_estimate {code, label}, valuation_estimate {code, label}.
  403 means a section the key does not unlock.
- news 200: `{ status, total, count, limit, offset, credits_consumed, data: NewsArticle[] }`. NewsArticle:
  title, url, publisher, published_date (YYYY-MM-DD), sentiment (positive, negative or neutral),
  news_score (0 to 1), ai_summary, full_text, author, countries[], industries[] {name, code, is_primary},
  **types[] {name, code, is_primary}** (the event tags), company_mentions[] {company_id, name, website,
  is_primary}. 204 means no news.

Only if the sponsor key unlocks them (otherwise they return 403; show nothing, never crash):
GET /company/headcount-trends (2.5), GET /company/website-traffic (1.5), GET /company/jobs,
enrichment sections funding_detail (3) and mna_and_investment (5).
Plan B only: POST /list/generate/companies/ with { query } or { filters }, plus POST /list/filter-builder/.

Notes: news lookback is capped at 6 months on non-enterprise plans. /news returns 204 when there is no
match; treat that as "quiet 90 days", not an error. Budget: at most 6 credits per company and 40
companies per fund on demo day (about $12 per fund at $0.05 per credit).

## Signal engine (src/lib/signals.ts, deterministic)
Tag families to category, severity and suggested action:
- funding (equity fund-raising, debt, grant): severity 2, "congratulate; offer intro to later-stage investors".
- people, negative (executive departure, layoffs): severity 3, "check-in call this week".
  people, positive (executive appointment, hiring): severity 1, "congratulate".
- product (launch, partnership, customer win): severity 1, "amplify; offer customer intros".
- corporate (M&A, acquisition, IPO): severity 3, "exit tracking; LP disclosure".
- risk (lawsuit, regulatory, breach, or negative sentiment on any tag): severity 3,
  "risk flag; call founder; prepare LP note".
Pulse per company = sum of severity weighted by recency with a 90-day half-life.
The fund view sorts companies by pulse. Exact tag names come from data/news-tags.csv.

The same families as akta tag codes (data/news-tags.csv; an article's `types[].code`). Classify each
article by its primary type, falling back to the first type; when two rules match, the higher severity wins.

| Category | Codes | Severity | Notes |
| --- | --- | --- | --- |
| funding | CM01 Equity Fund-Raising, CM02 Debt Financing, CM09 Valuation Events | 2 | |
| people (negative) | WT02 Workforce Reductions, LG04 Organisational Restructuring; LG01 C-Suite Appointments & Departures with negative sentiment | 3 | "check-in call this week" |
| people (positive) | WT01 Strategic Hiring, LG02 Board Composition & Changes; LG01 with positive or neutral sentiment | 1 | "congratulate" |
| product | SD01 Product Launches, SD02 Partnerships, SD03 Geographic Expansion, SD04 Operational Milestones, SD11 Awards | 1 | |
| corporate | CM03 M&A, CM04 Divestitures, CM05 IPOs, CM06 SPACs, CM07 Secondary Transactions, CM11 Take-Private | 3 | |
| risk | RC03 Litigation, RC06 Antitrust, RC07 Data Privacy Regulation, RK04 Operational Disruptions, RK05 Cybersecurity Incidents, RK06 Reputational Damage, RK07 Financial Distress | 3 | also any other mapped tag with negative sentiment |
| (dropped) | MD*, MM*, FR07, CM08, CM10, CM12, OT01 and anything unmapped | none | market noise, not a portfolio event; never shown as a signal |

## LLM prompts (src/lib/llm.ts)
System: "You are a VC platform associate. Plain, specific sentences. Cite only the provided sources as
[n]. Never invent facts. If the sources do not support a claim, leave it out."
- Founder email: at most 90 words, warm, one concrete offer (an intro, a customer, a candidate).
- Partner note: three bullets: what happened, why it matters for our position, what to ask.
- LP update: "Portfolio highlights" (5 to 8 bullets across the fund, newest first) and "Companies to
  watch" (2 to 3, each with the concern and our action). Every bullet ends in [n].
Validation: collect every [n]; drop sentences whose n is not in the source list.

## Pages and routes
- / : fund picker, three preloaded funds plus paste-a-list.
- /fund/[slug] : card grid, event feed sidebar, Generate LP update button.
- /fund/[slug]/update : the generated update with .md and .docx export.
- POST /api/fund/[slug]/refresh : pull or refresh akta data for the fund.
- POST /api/draft and POST /api/lp-update : streaming routes.

## Definition of done (3:30)
Three funds render offline from fixtures. One fund refreshes live. Draft action streams with
citations. LP update exports .md and .docx. The Vercel URL is live. `npm run build` and `npm test`
are green. NOTES.md is honest.
