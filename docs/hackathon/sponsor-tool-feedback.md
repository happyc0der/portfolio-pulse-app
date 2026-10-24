# Feedback for the sponsor tools

What we ran into while building Portfolio Pulse at Deal Flow (Oct 24, 2026), written for each
product's founders. Each item: what happened, why it cost us time, and a suggested fix. Times are ET.

## akta.pro (Wokelo AI)

- **Paths without a trailing slash return 307 with an empty body.** `GET /api/v1/news?...` redirects
  to `/api/v1/news/?...`. curl without `-L` saves an empty file and exits 0, so a fixture script looks
  like it worked. The OpenAPI spec lists the paths without the slash (`/v1/news`,
  `/v1/company/search`), so code generated from the spec hits the redirect on every call. We found it
  only by testing with a fake key (10:00). *Suggest:* serve both forms, or match the spec to the
  server, and put a one-line note in the quickstart.
- **The enrichment response is untyped in the spec.** `GET /v1/company/enrichment` declares
  `data: { type: object }`. Field names live only in the 10,700-line data dictionary page, so typed
  clients and validators (zod, pydantic) can't be generated. *Suggest:* a schema per section in
  openapi.json.
- **`news-tags.csv` is tab-separated with no header row** (and no trailing newline), despite the
  `.csv` name. A CSV parser reads each line as one column. *Suggest:* real CSV with a `code,name`
  header, or rename it to `.tsv`.
- **The live `/news/` response doesn't match the OpenAPI spec** (checked at 10:57 against 12 real
  companies, 214 articles):
  - Event tags arrive as `tags[]`, while the spec says `types[]`. Code written from the spec finds no tags.
  - Sentiment is `Positive`/`Negative`/`Neutral`; the spec says lowercase.
  - `published_date` is a timestamp, `2026-10-15T07:30:00`; the spec says `YYYY-MM-DD`.
  - The score is `newsworthiness_score`; the spec says `news_score`.
  - `company_mentions[]` carry `uuid`; the spec says `company_id`.
  - The envelope has no `status`.
  - Undocumented but useful: `is_press_release`, `is_breaking`, `article_type`, `entities`,
    `group_id`, `sentiment_score`, and `akta_rank` on search results.
  We nearly shipped a signal engine that classified every article as "unknown". *Suggest:* generate
  the spec from the server, or add a contract test.
- **`group_articles=true` doesn't merge translations.** N26's new-CFO story came back five times,
  in Thai, Japanese, Portuguese, Italian and German, each with its own `group_id`. *Suggest:* group
  across languages, or add a `language=en` filter.
- **`original_language` is sometimes wrong.** Spanish, German and Portuguese headlines arrive
  labelled `EN`, so a language filter on that field lets them through. We added a stopword check
  on the title.
- **`is_press_release` is true on 271 of 302 articles** across our three portfolios, so it can't
  separate press releases from reporting.
- **`company_status` misses acquisitions.** Giphy (Shutterstock), Tumblr (Automattic) and The Browser
  Company (Atlassian) come back as `private`, and one seed-stage startup comes back as `delisted`. For a
  VC, exits matter. We use the `public` status to mark exits, which caught BitGo, Dropbox, Einride,
  PayPal, SoundHound and Wealthfront.
- **`group_id` doesn't group repeat reports either.** Eliyan's takeover interest came back as three
  articles in six days, Granola's lawsuit as five, Particle Health's FTC story as three, each with its
  own `group_id`. We merge them ourselves (same company and category within 7 days). *Suggest:* one
  story id across publishers and languages.
- **Company search's first result can be a different company.** For "Eliyan" the first hit was "Eliya
  Chocolates Inc."; we had taken the first result and showed a chocolate maker's data in a chip
  startup's draft. Matching on the website domain fixed it. *Suggest:* rank an exact domain match
  first, or accept a domain filter.
- **Strong data once parsed:** tags were present on every article and accurate (CM01 for Reco's
  $55M raise, LG01 for N26's CFO, CM03 for Eliyan's takeover talks, RC03 for AI-notetaker
  litigation). Headcount trends and `funding_detail` worked on our key (Reco: 213 employees, +27%
  over 6 months; Series B, $140M total).
- **Company search is forgiving, which made "add any fund" possible.** It handles typos ("sequia" finds
  Sequoia Capital), short forms ("a16z" finds Andreessen Horowitz) and prefixes ("union sq" finds
  Union Square Ventures), and it costs no credits, so we run it on every keystroke (250 ms debounce).
  *Suggest:* an `is_investor` or entity-type field. We guess investors from the category text.
- **List Generation turns an investor into a portfolio in about 3 seconds.** Filtering on
  `funding_detail.funding_rounds.investors.uuid` returned Lerer Hippeau's portfolio (353 companies on
  record, 25 per call) for about 6.5 credits. This is the feature our live demo is built on. *Suggest:*
  document this filter path with an example; we found it in the data dictionary, not the List
  Generation page. Results come back with well-known companies first (Scopely, Oscar Health, Venmo
  for Lerer Hippeau), but the sort order isn't documented. A `sort` by last funding date would help a
  VC see the current portfolio rather than its most famous names.
- **What worked well:** `llms.txt` and the `.md` version of every docs page made the API quick to
  learn with a coding agent. `primary_company` (only articles mainly about the company) and
  `group_articles` are exactly what portfolio monitoring needs. A bad key returns a clear
  `{"detail":"Invalid API key"}`.

## Nicrron

- **The quickstart doesn't name the auth header** (it only shows the key passed to the OpenAI SDK)
  and has no curl example. We assumed `Authorization: Bearer`, which a test confirmed: a bad key
  returns `{"error":{"message":"Invalid API key","code":401}}`. *Suggest:* a curl example on the
  quickstart.
- **Streaming isn't documented** on the quickstart or the models page, and neither says whether
  `GET /v1/models` exists. Both matter for any app that streams drafts. *Suggest:* one line each.
- **What worked well:** the models page lists exact slugs (`anthropic/claude-opus-5-5`,
  `anthropic/claude-haiku-5-5`), so there was no guessing.

## Ninoo Builder

- **A working app shows "Something broke in your app. WebSocket closed without opened."** The
  preview rendered correctly after the first prompt, but the red banner stayed up. The console shows
  the cause: Vite's dev-server live-reload socket (`wss://<id>.preview.ninoo.app/`, from
  `/@vite/client`) fails to connect on the preview domain. So the app is fine, but at a demo the
  banner reads as a crash. *Suggest:* proxy the HMR websocket on preview domains, or tell
  live-reload errors apart from app errors and don't offer "Fix it" for the former.
- **"Typecheck passes" shipped a runtime crash.** After prompt 2 (swap mock data for real data),
  Ninoo reported "Typecheck passes", but every fund page rendered blank: `TypeError: Cannot read
  properties of undefined (reading 'date')` in `App.tsx`, because real companies had no events yet.
  We only caught it by opening `/fund/betaworks` ourselves. *Suggest:* after each turn, load the app's
  routes in a headless browser and treat uncaught errors as a failed turn, not just `tsc`.
- **Deep links weren't checked either.** The same crash hit both direct loads and in-app navigation.
  A route smoke test would catch both.
- **Docs gaps that changed our design:** whether streaming responses work on published apps; how
  backend code reads Secrets at runtime (the docs say values go to the backend, not how to read them);
  and whether backend files and SQLite persist after publishing (the docs say SQLite "can reset").
  We had to plan fallbacks for all three. *Suggest:* a "Backend runtime" page covering env vars,
  persistence and streaming.
- **Secrets don't reach the preview.** We saved `AKTA_API_KEY` under Integrations → Secrets (it
  showed as saved, no longer "missing"), but the preview backend kept returning "AKTA_API_KEY is
  not configured" on two refreshes. The small print says Secrets are "added when you publish", while
  the card header says keys "go straight to where your app reads them". Nicrron AI's key *does* go to
  the preview's `.env`, so the two behave differently. We lost about 10 minutes and had to hand-edit
  `.env`. *Suggest:* push Secrets to the preview too (or say clearly on the card that they don't),
  and show a "preview has no value for X" warning.
- **A turn can end with a known failing test.** The drafts prompt ended with "This is not finished
  or verified: the email greeting/sign-off citation-check test is still failing". We appreciated
  the honesty, and it's far better than a silent "Typecheck passes". But the next queued prompt
  started right after, on top of the failing state. *Suggest:* when a turn ends unverified, pause
  the queue and ask, or let the user mark a queued item "only if the last turn passed".
- **Queued messages live only in the browser tab.** We had four prompts queued; closing that tab
  silently dropped the last three (a test fix, an env fix and a theme fix). Nothing warned us, and the
  project page later showed an empty queue. *Suggest:* keep the queue on the server, or warn on tab
  close ("3 queued messages will be lost").
- **The published backend only gets `api/`, but Ninoo's own code read `src/funds.json`.** The preview
  worked, but after publishing, every data route returned a bare `Internal Server Error` while
  `/api/health` was fine. Ninoo had written that cross-folder read itself, earlier in the session.
  *Suggest:* a publish-time check that flags backend code reading paths outside `api/`, and JSON
  error bodies or a visible log for the published backend.
- **Nicrron AI silently stops reaching the preview.** Integrations later said "AI is on for the
  published app. Open the workspace and turn it on again to reach the preview too", after the
  workspace had paused. Our preview's `/api/health` reported `NICRRON_API_KEY` missing until then.
  *Suggest:* re-inject the key when the workspace resumes.
- **The Builder's model isn't documented.** Pricing says Builder uses "the nicrron/builder model, a
  low-cost model with fallbacks", but `nicrron/builder` isn't in the public model catalog, and there's
  no model choice. Knowing the model would help users size prompts. We switched to short prompts with
  explicit acceptance checks after seeing it miss unstated requirements (light-mode theming).
- **The project chat hits a hard context limit with no way out.** About 20 turns in, every
  prompt failed: "Provider openai rejected the request: Input tokens exceed the configured limit
  of 272000 tokens. Your messages resulted in 451543 tokens." `/compact` didn't help, and there's no
  "new chat" for an existing project. A turn that crashes this way also leaves half-applied edits:
  ours left a TypeScript error (`payload` used outside its block) that broke the refresh flow at
  runtime. *Suggest:* compact automatically, or start a fresh thread with a repo summary; never
  leave a crashed turn's edits unflagged.
- **Ninoo writes one giant backend file.** `api/main.py` reached 72 KB (about 18k tokens), and each
  turn re-read it several times, which is what blew the context. *Suggest:* split modules once a file
  passes a size, and read by symbol rather than whole files.
- **The context-limit problem was fixed during the event.** At about 1:15 PM the Ninoo team fixed
  chat compaction, so long projects can continue in the Builder chat again. Thank you for the quick
  turnaround on event day.
- **One unexplained 404 right after a publish.** About two minutes after "Publish latest changes",
  our backend created a fund and served it to seven requests in a row, then answered the eighth with
  our own "Fund not found"; every retry after that returned 200. We couldn't tell whether an older
  instance was still serving. We made the client confirm before opening the page. *Suggest:*
  document whether publishes roll over instances and whether more than one instance can serve
  requests, since that decides whether local-disk state is safe at all.
- **The 30-second request limit shapes the design.** Our news refresh plus a headcount pass took
  about 63 seconds in one request locally, so we split it into batches of 4 companies with a time
  budget. *Suggest:* put the limit on the publish panel, and return a clear 504 body when it's hit.
- **The published backend runs as several instances with separate disks, and nothing says so.** A
  fund our app added live (written to its local disk) answered on some requests and was "not found"
  on others, then vanished. Back-to-back reads of our own credit counter alternated between two
  values, and one response was a 429 `ReservedFunctionConcurrentInvocationLimitExceeded`. Every
  cache we wrote at runtime (drafts, LP updates, the credit ledger and its cap) was per instance.
  We moved shared state to Roundtable files and baked demo outputs into committed data. *Suggest:*
  document the runtime model (instances, disk lifetime, concurrency limit) on the backends page and
  offer a small shared key-value store; "Use SQLite" can't work across instances.
- **Ninoo Git saved the day.** Cloning the project, fixing it locally with tests, and pushing to
  `main` merged straight into the app, with the same Secrets and URL. This deserves a prominent place
  in the docs as the escape hatch for large projects.
- **Queued messages are a great feature:** "type to queue" let us line up the next prompt while a
  long turn ran, which kept the build moving.
- **Session is per browser profile.** Signing in once in Edge did not carry to a second browser
  (expected), but the team lost a few minutes. *Suggest:* "Open in another browser" via a magic link.
- **What worked well:** a first build from a 2,400-character prompt in about a minute, with a clear
  summary of what changed. The documented 20,000-character message limit let us plan prompt sizes
  ahead. The prompting guide ("one or two changes per message") was accurate.

## Devpost page (organizers)

- **The deadline disagrees with itself.** The overview says submissions close at 4:00 PM ET; the
  rules page says 4:30 PM ET. We are planning for 4:00.

## PRISM by Block Convey

- **`{input}` is only the user's last message, so most of our sources never reached the judge.** Our
  prompt carried the numbered sources inside one long JSON message. PRISM's judge reads `{input}` as
  the user's last message only, and `{context}` as what the trace's retrieval and tool steps
  returned (about 6,000 characters). Our first citation-rule run failed 39 of 40 drafts, but the
  judge had seen only source [1], so it marked correct citations as invalid. That run told us
  nothing about draft quality, it cost evaluator credits (1 per trace scored), and we found the cause
  only by reading the traces. The Evaluators Hub paragraph in the docs explains `{context}`, but
  nothing in the quickstart or the `trace_llm` docstring says sources must arrive as a retrieval
  step. We now send each draft as one trace with three steps: the agent run, an `akta_sources`
  retrieval step with the numbered sources, and the Nicrron LLM call (checked in PRISM at 1:20 PM).
  *Suggest:* a `trace_llm` parameter for retrieved context, or a note in the quickstart.
- **Sending both `POST /api/traces` and `POST /api/spans/ingest` for the same `trace_id` races.**
  Whichever request arrives first wins. One of our traces lost its spans; another took the retrieval
  step's text as its output and counted tokens twice. We found both only by reading the spans with
  `prism_get_trace`, and until then the judge would have scored the wrong output. The SDK's own
  handlers send spans only, but the docs don't say so. *Suggest:* document that the SDK sends spans
  only and that the two endpoints shouldn't be mixed for one trace, or merge the two requests into
  one trace whichever arrives first.
- **The judge read about 2,000 characters of `{context}`, not the documented 6,000.** Our first
  three traces scored with a `{context}` rubric all failed for the same reason: the judge said "only
  [1] through [6] are available", while the trace's sources step listed 17 sources in 5,522
  characters, and [7] starts at character 2,159. So valid citations to [8], [10] and [14] were marked
  invalid. We now open the sources with an index step under 1,900 characters that names the full
  range. *Suggest:* state the real limit (per step or in total), and mark truncation in the judge's
  input ("…context truncated at N characters") so a rubric can't mistake missing text for absent sources.
- **The automatic review reads only the start of the last user message, too.** With our sources
  inside one JSON request, the free per-trace review said "only sources [1] and [2] are provided" and
  flagged valid citations as invented (BIT draft: quality 35, flagged). Opening the real request with
  a compact source index fixed it: the same draft scored 72, and the remaining flag is a genuine
  question about whether two sources support two claims. *Suggest:* tell integrators which part of
  a trace each judge reads, and how much of it.
- **What worked well:** the MCP server let us add and run evaluators and read traces from our coding
  agent, with a preview and a confirm code before any credit was spent. `prism_get_trace` shows a
  trace's spans, which is how we found both problems above.

## Roundtable

- **The handoff works end to end, after a fix at 1:40 PM.** Our Signal Watcher bot writes the event
  file and creates the task; the Drafter bot claims it, writes the cited draft and closes the task. Bot
  creation with `create_subagent` worked on the first try. Until 1:40, though, no task ever closed (next
  item).
- **"Invalid arguments" doesn't say which argument.** `get_task` accepts only `task_id`, while the other
  task tools take `project` and `expected_version`, so every one of our `get_task` calls was rejected.
  `update_task` wants `progress` as text and we sent the number 100, so no task ever closed: six sat in
  `active` until their leases expired, and each draft waited 25 seconds for a status that never came.
  The dashboard banner "signal-watcher needs attention: 5 unresolved request failures: Invalid
  arguments" is what told us. `get_agent_log` showed which call failed, and `GET /api/tools` returned
  every tool's JSON schema, which is how we fixed it in minutes. *Suggest:* name the field and the
  reason in validation errors ("get_task: unexpected field 'project'"), and link the schema list from
  the docs.
- **An expired lease returns a bare 409.** Closing a task whose lease had run out returned `409
  Conflict` with no hint. Claiming it again with its current version, then closing it, worked.
  *Suggest:* say "lease expired; claim again" in the 409 body.
- **Files are capped at 200,000 characters, but `write_file`'s schema doesn't say so.** The error is
  clear ("File exceeds 200,000 characters"), which is good; a `maxLength` in the tool schema would
  let clients check before sending. We now use Roundtable files as the shared memory for live-added
  funds across our server instances, which worked well once trimmed under the cap.
- **What worked well:** the dashboard named the failing agent, and the agent log plus the tool schemas
  made the cause obvious. That is good observability for an agent workspace.
- **`get_folder_history` rejects every argument shape we tried.** `{bank, path:"drafts/"}`
  returns "Use a relative POSIX path…"; `{bank, path:"drafts"}`, `{bank}` and
  `{bank, path:"drafts/40910269.md"}` return "Folder not found", although `list_files` shows
  `drafts/40910269.md`. `{folder}` returns "Invalid arguments at " (with an empty location). We fell
  back to `list_files`. *Suggest:* document each tool's parameters and give the field name in
  validation errors.
- **"Waiting for first check-in…" never clears for bots made through the API.** Our bots did real
  work in the folder, but the Connect dialog kept waiting, which looks like a failure to a new user.
- More detail is in pitch/roundtable.md, section 9.
