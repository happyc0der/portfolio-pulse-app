# Portfolio Pulse

Early warnings for VC portfolios, from outside data, with every claim cited.

**Live demo:** https://portfolio-pulse-portfolio-mo-193e.ninoo.app
Built on Oct 24, 2026 at Deal Flow, NYC's first VC hackathon (Track 3: Portfolio).

## What it does
- Watches every company in a fund's portfolio through akta.pro news and company data. It runs on
  three real public portfolios: Everywhere Ventures, Plug and Play Ventures and Betaworks.
- Turns each article into a signal with **deterministic rules** (akta tag code → category, severity
  1 to 3 and a suggested action) and ranks companies by a recency-weighted pulse.
- Puts severity 3 events from the last 30 days at the top ("Needs your attention").
- Drafts the partner's next move (a partner note or founder email) and the fund's LP update. Every
  sentence cites a numbered source, and sentences the sources don't support are removed.
- Nothing sends itself: every draft is for a human to copy, edit and send.

## How it works
```
akta.pro news + headcount ──► relevance + language filters ──► signal rules (tag code → severity)
        │                                                        │
        ▼                                                        ▼
  provenance on every number                       Signal Watcher bot (Roundtable)
                                                                 │ hands the event over as a task
                                                                 ▼
  numbered sources ──► Nicrron (Claude Opus 5.5) ──► citation check ──► Drafter bot saves the
                                     │                                   draft as a versioned file
                                     ▼
                         PRISM trace for every LLM call (v1 vs v2)
```

## Sponsor tools
| Tool | Where |
| --- | --- |
| **Ninoo Builder** | The whole app was built in Ninoo Builder from our prompts and is published on ninoo.app. |
| **Nicrron** | Every AI call goes through `https://api.nicrron.ai/v1` (`anthropic/claude-opus-5-5`). |
| **akta.pro** | News (`/news/` with `primary_company`, event tags, sentiment), headcount trends, website traffic, open roles, company profiles and comparable companies (List Generation). |
| **PRISM by Block Convey** | `api/tracing.py` traces every draft and LP update as one trace with three steps: the run (request in, draft out), an `akta_sources` step listing the numbered sources the model was given (what PRISM evaluators read as `{context}`), and the Nicrron call with tokens and cost. Run names `draft-v1` / `draft-v2` compare output without and with the citation check on the same inputs, and `/eval` replays 20 events. |
| **Roundtable** | `api/roundtable.py`: a Signal Watcher bot writes each event to the shared folder and hands it to a Drafter bot as a task. The Drafter claims the task, saves the cited draft as a versioned file, closes the task and reports the files it used; the Signal Watcher reads the status back. Both bots run inside the backend on demand, each with its own Roundtable identity. |

## Signal rules (`api/main.py`)
| Category | akta tag codes | Severity |
| --- | --- | --- |
| Funding | CM01, CM02, CM09 | 2 |
| People (negative) | WT02, LG04, LG01 with negative sentiment | 3 |
| People (positive) | WT01, LG02, LG01 otherwise | 1 |
| Product | SD01–SD05, SD08, SD11, II01, II02 | 1 |
| Corporate | CM03–CM07, CM11 | 3 |
| Risk | RC03, RC06, RC07, RK04–RK07, or negative sentiment on a positive category | 3 |

Market noise (stock moves, macro, commentary) is dropped. Pulse = Σ severity × 0.5^(age in days / 90).
Unit tests: `api/test_signals.py`.

## Data and trust
- Public, licensed data from akta.pro only. No scraping, no founder uploads, no private fund data.
- An article counts for a company only if it names the company and is in English. Everything else is
  counted as "filtered" and shown, so the cleaning is visible.
- Keys stay on the backend (`os.getenv`) and are never sent to the browser.

## Run it
```bash
pnpm install && pnpm dev                       # frontend
uv pip install -r api/requirements.txt
uvicorn api.main:app --reload --port 8000      # backend
pytest api/                                    # tests
```
Environment variables (names only): `AKTA_API_KEY`, `NICRRON_API_KEY`, `PRISMTRACE_API_KEY`,
`PRISMTRACE_PROJECT_ID`, `PRISMTRACE_HOST`, `ROUNDTABLE_PROJECT`, `SIGNAL_WATCHER_KEY`,
`DRAFTER_KEY`, `DRAFTER_ID`. Optional: `AKTA_CREDIT_CAP` (default 150).

## Built today
All code in this repository was generated in Ninoo Builder on Oct 24, 2026 during the event. Before
the event we did the founder work only: customer research, the product spec and the public portfolio
lists.
