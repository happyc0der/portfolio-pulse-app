# Portfolio Pulse: Devpost write-up

As submitted to Deal Flow, NYC's VC hackathon at Betaworks, on October 24, 2026.

## Inspiration

A fund's portfolio is a long list. Plug and Play's "Our Startups" page flags 1,508 companies as portfolio; everywhere.vc lists 265. Those companies are in the news every week: rounds, new executives, layoffs, acquisitions, lawsuits. The news is public, but nobody reads all of it, and once a quarter someone rebuilds the story by hand for the LP letter.

Track 3 asked for early warnings from scattered portfolio updates. We wanted the warning, the partner's next move and the LP paragraph in one place, with a source under every sentence, because a partner won't forward a claim they can't check.

## What it does

Pick a fund. Portfolio Pulse loads its companies, pulls the last 90 days of news for each one from akta.pro, and turns every article into a signal using fixed rules on akta's own event tags. akta's headcount trends add leading indicators, which often move before the news:

- **Funding** (equity fund-raising, debt financing, valuation events): severity 2. Suggested move: congratulate; offer intros to later-stage investors.
- **People, negative** (workforce reductions, restructuring, a C-suite departure with negative sentiment): severity 3. Suggested move: check-in call with the founder this week.
- **People, positive** (strategic hiring, board changes, a C-suite appointment): severity 1. Suggested move: congratulate the new leader.
- **Product** (launches, partnerships, geographic expansion, milestones, awards): severity 1. Suggested move: amplify it; offer customer intros.
- **Corporate** (M&A, divestitures, IPOs, SPACs, secondaries, take-privates): severity 3. Suggested move: exit tracking; prepare the LP disclosure.
- **Risk** (litigation, antitrust, data privacy, outages, breaches, reputational damage, financial distress): severity 3. Suggested move: call the founder; prepare an LP note.
- **Leading indicator** (akta headcount: down 5% or more, or up 20% or more in 6 months): severity 3 for a drop of 10% or more in 6 months, 2 for a smaller drop, 1 for growth. Suggested move: for a drop, check in with the founder; for growth, ask which roles and offer candidate intros.

Triage keeps the list short enough to act on:

- **A news story reaches severity 3 only if its headline names the company.** A story that only mentions the company is severity 1: "Mentions the company in passing; no action needed". That was 84 of the 358 signals across our four funds at 2:51 PM ET.
- **One story, one signal.** Repeat reports of the same story within 7 days are merged, and the signal says so ("+1 more report of this story").
- **Stock-market robo-posts are filtered out.** They aren't portfolio events.
- **The move follows the sentiment.** Bad news is never "Congratulate" or "Amplify it": a Funding, Product or positive People story with negative sentiment becomes Risk.
- **Exits are tracked, not alarmed on.** akta's company data counts only when akta's match has the company's website. Exits akta misses are corrected with a named source (The Browser Company: Atlassian; ZestyAI: Aon; Hugging Face: the Nvidia deal). Exited companies are marked "Exited · public" or "Exited · acquired", stay out of "Needs your attention", and have their own "Exits" filter.

The model never decides a category or a severity, and the rule table is one click away in the app ("How signals work").

Then:

- **Needs your attention.** The top of each fund page lists severity-3 signals from the last 30 days at companies that haven't exited, each with its suggested move. When nothing qualifies it says so: Betaworks' list was empty at 2:51 PM ET.
- **Pulse.** Each company gets a score: the sum of its signals' severities, weighted by recency with a 90-day half-life. The fund page sorts companies by pulse, so the top of the page is where to look first. A fund-wide feed lists every signal, newest first.
- **Draft action.** Click a signal to see the summary, the suggested move and the source. "Partner note" drafts three bullets: what happened, why it matters for our position, what to ask the founder. "Email to founder" drafts a short note with one concrete offer. Claude Opus 5.5 writes it through Nicrron, from numbered sources only. Every factual sentence cites one as [n]; click it and the article opens.
- **LP update.** "Generate LP update" writes the quarter's update for the whole fund: Portfolio highlights and Companies to watch, every sentence cited, with a numbered source list. Copy it, or download it as .md or .docx.
- **A validator, not a promise.** Before anything reaches the screen, the backend checks every sentence: it drops facts with no citation and any citation to a source number the model wasn't given, and keeps questions and offers to the founder. PRISM by Block Convey traces every draft and LP update with an index of the numbered sources the model was given, so each citation can be checked against them.
- **Agents that hand off work.** When a partner asks for a draft, a signal-watcher bot hands the event to a drafting bot as a task in Roundtable. The drafter claims it, saves the cited draft as a versioned file in the shared workspace and closes the task.
- **Nothing sends itself.** Every output is a draft for a person to read, edit and send.

It runs today on four funds. Three are real public portfolios, taken from each fund's own portfolio page: Everywhere Ventures (40 companies), Plug and Play (37) and Betaworks (37). Those are the companies we loaded today, not each fund's full portfolio. The fourth, Hack VC (28), was added at a judge's request and assembled by akta.pro from the funding rounds that list Hack VC (222 companies; the top 25 shown, plus its 3 most recent investments).

**Add any fund, live.** On the home page, "+ Add a fund" opens a search box. akta.pro company search runs as you type and tolerates typos and short forms: "sequia" finds Sequoia Capital, "a16z" finds Andreessen Horowitz, "union sq" finds Union Square Ventures. Investment firms are listed first, with an Investor chip. Pick one, and akta.pro finds the companies whose funding rounds list that investor; the app pulls 90 days of news for each and builds the fund page. Funds added this way are labelled "Added live" on the home page. We checked it on the live app with Greycroft: 25 companies (485 on record), news in about 45 seconds; the home page listed it on 8 of 8 reads, its fund page loaded 8 of 8 times, and its draft and LP update worked. At 2:51 PM ET Greycroft showed 90 signals, 5 items in "Needs your attention" and five exits marked automatically.

## How we built it

- **Before build day** (allowed pre-work): problem research, the spec and the build prompts. A Next.js starter was also created on Friday; we didn't use it.
- **This morning, before 10:30:** the three portfolio lists, copied from each fund's public page with every website checked live, and two small curl scripts to test the akta API.
- **From 10:30, the app**, built in **Ninoo Builder** from seven prompts: a React + TypeScript front end and a Python FastAPI backend.
- **akta.pro by Wokelo AI is the whole data layer.** The backend calls `/news/` with `primary_company` (only articles mainly about that company), a 90-day `start_date` and `group_articles`, and reads each article's event tags (`tags[]`), sentiment, publisher, URL and AI summary. `/company/search/` flags companies akta can't resolve, and `/company/headcount-trends/` feeds the leading indicators. A 204 means no news, shown honestly as a quiet company. The API key stays on the backend.
- **Add a fund, also akta.pro.** Company search runs on every keystroke (free, 250 ms debounce). When a firm is picked, List Generation filtered on funding rounds that list that investor returns its companies in about 3 seconds for about 6.5 credits. The backend then pulls 90 days of news four companies at a time, so each request stays inside the host's 30-second limit.
- **Signal engine:** plain Python. It maps akta's tag codes to a category, severity and suggested move, takes the article's primary tag, and computes pulse. It also runs the triage above: the headline check before severity 3, the 7-day merge of repeat reports, the stock-market filter, moves that follow sentiment, the website match for akta company data, and headcount thresholds. No model involved.
- **Nicrron (NicrronNinoo)** is the model gateway: OpenAI-compatible, model `anthropic/claude-opus-5-5`, called only from the backend.
- **Citation validator:** sources are numbered [1], [2], ... before the model sees them. The backend splits the reply into sentences (without breaking on "Oct." or "Inc."), keeps questions and offers, and drops any sentence that states a fact without a citation or cites a source number that isn't in the list.
- **PRISM by Block Convey:** every draft and LP update is one trace: an agent step (the request in, the final draft out); an `akta_sources` step that indexes every numbered source with its title in under 1,900 characters, plus detail steps; and the Nicrron model call with tokens and cost. The model's request itself opens with the same source index. PRISM's free automatic review scores every trace. It reads only the start of the request, so before the index it flagged valid citations as invented; with the index, the same draft (BIT, a Hack VC company) went from 35, flagged for having "only sources [1] and [2]", to 72, with a genuine question about whether two sources support two claims. We claim no pass rate (see Challenges).
- **Roundtable:** for each draft or LP update, the signal-watcher bot saves the event (or the update) to the shared workspace and assigns a task to the drafting bot, which claims it, saves the result as a versioned file and closes the task. Both bots run inside our backend on demand, each with its own Roundtable identity.
- **Several servers, one shared folder.** The published backend runs as several server instances with separate disks. Funds added live and every generated draft and LP update are saved to the team's Roundtable folder, so every instance serves them. A broad live check on random items passed: LP updates for all four funds generated in 16 to 22 seconds, and 8 random drafts across all funds took 10 to 13 seconds each, each with its Roundtable task done.

## Challenges we ran into

- **Noise a VC would stop trusting.** Four QA agents tested the live app as users and as a skeptical VC. They found stories that only mentioned a company rated severity 3, one story counted several times, stock-market robo-posts, "Congratulate" on bad news, and exits akta had missed. Each finding became a fixed rule (the triage list above).
- **Our citation check cut good sentences.** It split sentences at "Oct." and "Inc." and dropped questions to the founder, which carry no citation. It now splits correctly, keeps questions and offers, and still drops uncited facts and invented source numbers.
- **A fund that came and went.** A fund we added live answered on some requests and was "not found" on others: the published backend runs as several instances, each with its own disk. We moved added funds, drafts and LP updates into Roundtable files that every instance reads.
- **PRISM's judges see less than the model does.** Our first citation-rule run failed 39 of 40 drafts because of how we traced: the judge saw only source [1], so it marked correct citations as invalid. The automatic review reads only the start of the request, so it flagged valid citations too, until the request opened with a source index. A custom citation-check evaluator reading `{context}` scored 5 traces and all 5 failed: 3 because its judge saw only sources [1] to [6] of 17 (fixed), and 2 after that fix because it checks support against short source summaries (about 2,000 characters visible, though PRISM's docs say 6,000). So it can't yet tell v1 drafts (no validator) from v2. None of these runs is evidence about draft quality.
- **Our Roundtable tasks never closed until 1:40 PM.** Two of our calls sent arguments Roundtable rejects (`get_task` takes only a task id; `update_task` wants progress as text), so every task stayed open and each draft waited 25 seconds for a status that never came. Roundtable's dashboard flagged our signal-watcher bot by name, its agent log showed the failing call, and `GET /api/tools` gave the exact schemas, so the fix took minutes. We closed the six stuck tasks the same way.
- **Empty responses that looked like success.** akta paths need a trailing slash (`/news/?...`). Without it the API answers 307 with an empty body, and curl saved empty files and exited 0.
- **Public portfolio pages are messy.** everywhere.vc lists names and descriptions but no websites, and akta resolves companies by website, so we matched each one by hand. We dropped dead, parked and acquired-and-redirected domains.
- **Old news looks new.** Aggregators re-date and re-cover old events (a June round re-dated, an April launch re-covered), so we pick demo events only from what akta returns, not from web search.
- **A 30-second request limit.** The host cuts off any request after 30 seconds, and a new fund's news takes longer than that, so the backend pulls it four companies at a time.
- **A green check isn't a working app.** After we swapped in real data, the builder reported that the typecheck passed while every fund page rendered blank (companies with no events yet). We now open the routes ourselves after every change.

## Accomplishments that we're proud of

- It runs end to end on real, public data. At 2:51 PM ET on Oct 24 the live app had 142 companies across four funds, 86 of them with news, 358 signals from the last 90 days, 11 at severity 3 at companies that haven't exited, and 7 items in "Needs your attention". The three judging funds alone: 114 companies, 246 signals, 4 items needing attention.
- Any fund can be added live by name. Greycroft went from a search box to a fund page with news in about 45 seconds (25 companies of 485 on record), and was served on 8 of 8 reads across our server instances.
- The model writes; it never decides. Severity comes from a rule table anyone can read, and the triage rules came from four QA agents testing the live app as users and as a skeptical VC.
- Every factual sentence carries a source, enforced in code, and every draft and LP update is one PRISM trace that indexes the sources the model was given.
- A broad live check on random items passed: LP updates for all four funds in 16 to 22 seconds, and 8 random drafts in 10 to 13 seconds each, each with its Roundtable task done.
- All four sponsor tools carry real weight: Ninoo built it, Nicrron runs the model, akta is the data and finds the portfolio, PRISM traces and reviews every draft with its sources, Roundtable moves the work between agents and holds the shared state.

## What we learned

- VCs trust a rule they can read more than a score they can't, so the model stays out of decisions.
- The citation rule is the product. A draft is only forwardable if every sentence can be checked.
- For public portfolio data, the website is the join key, and it is often wrong or missing.
- A story that mentions a company isn't news about the company.
- `[ONE LINE FROM THE LUNCH INTERVIEWS, or delete this bullet]`

## What's next for Portfolio Pulse

- Design partners: the three funds in this demo first. We'll draft their Q4 2026 LP update free.
- Load an added fund's full portfolio, not only the first 25 companies akta returns (Greycroft has 485 on record), and accept a pasted list for funds whose rounds akta doesn't record.
- akta's job-post data next to the headcount trends already live, for pre-seed companies that never make the press.
- Merge re-covered stories across more than 7 days, by the date an event was first seen.
- A company profile panel loaded on demand: akta's firmographics, funding history and team trend for one
  company. We spent today's akta budget on monitoring news for every company; a full profile costs about
  13.5 credits per company, so it loads only when a partner asks.
- One shared credit ledger. The hosted app runs as several server copies, and our 500-credit akta cap
  is counted per copy today; a single ledger makes the cap exact and shows the true spend.
- A weekly digest to the partner. Still drafts; nothing goes to founders or LPs on its own.

## Where each required sponsor tool is used

- **NicrronNinoo:** Ninoo Builder built and hosts the app (React + FastAPI), which is listed on the Ninoo Marketplace; Nicrron serves Claude Opus 5.5 for every draft and LP update. In the demo: Draft action and Generate LP update.
- **PRISM by Block Convey:** one trace per draft and LP update: an agent step, an `akta_sources` step indexing every numbered source, and the Nicrron model call; PRISM's automatic review scores every trace. In the demo: a draft's trace, with the request and draft, the source index, tokens and cost.
- **akta.pro by Wokelo AI:** all company news, event tags, sentiment and headcount trends; the tags drive the signal engine; every citation is an akta article; company search and List Generation turn a fund's name into its portfolio. In the demo: the fund feed, "How signals work", any [n] link, "+ Add a fund".
- **Roundtable:** on each draft or LP update, the signal-watcher bot assigns the work to the drafting bot as a task; the drafter saves a versioned file and closes the task. The same folder holds added funds, drafts and LP updates for every server instance. In the demo: the closed task and the file versions in the workspace.
