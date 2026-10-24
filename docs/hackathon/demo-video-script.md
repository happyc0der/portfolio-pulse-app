# Demo video script: 2:51

For the Devpost video (3:00 limit; 2:51 leaves margin). Screen recording with voiceover. About 400
words of voiceover, a calm pace with room for the screen to move.

## Before you record (15 minutes)

- **Pick the fund.** Open on **Plug and Play**: at 2:51 PM ET its "Needs your
  attention" had three items, two of them news (Eliyan, ApplyBoard). Everywhere Ventures had one, a headcount drop at Particle Health, and no severe news in the last 30
  days. Betaworks had none: its list says "No severity 3 signals from the last 30 days", and Hugging
  Face and The Browser Company show "Exited · acquired".
- **The severity-3 event:** **Eliyan**, "AI chiplet startup Eliyan draws takeover interest months
  after $1 billion valuation" (Crypto Briefing, Oct 9), Corporate, severity 3, shown with "+1 more
  report of this story". Backup: **ApplyBoard**, "ApplyBoard was the worst-performing Canadian startup
  in Fidelity's portfolio in 2026" (The Logic, Oct 6), Risk, severity 3. URLs and checks are in "Real
  events" below. If Eliyan's partner note was already generated today, it is cached and appears at
  once instead of streaming. To show the streaming, record shot 4 on the backup (check it has not
  been drafted yet), or on any event you have not drafted.
- **Don't refresh the funds before recording** unless the data is missing: the events and counts
  below were read at 2:51 PM ET and again at 2:58, after the 2:55 republish. If you do refresh,
  re-check the event and the numbers before recording.
- **Warm everything else:** open PRISM on the trace of a fresh Eliyan draft and click its
  `akta_sources` step so the source index is on screen; open the Roundtable workspace on the drafts
  folder.
- **Pick the fund to add in shot 10:** one that is not on the home page yet (a fund already there
  opens straight away, so there is nothing to show; Greycroft and Lerer Hippeau are already there).
  Record it in one take: each add costs about 6.5 akta credits for the portfolio plus news per
  company. Greycroft's news took about 45 seconds; cut the wait in editing.
- **Hide secrets.** Close Ninoo's Secrets panel, PRISM's API keys page and Roundtable's keys page.
  Nothing with a key goes on camera. Close unrelated tabs, turn on Do Not Disturb, hide bookmarks.
- **Screen:** 1920×1080, browser zoom 110 to 125% so text reads on a laptop. Record shot by shot and
  cut them together; record the voiceover separately if the room is loud.
- **Record** with **Cmd+Shift+5** or QuickTime Player (File, New Screen Recording), capturing the
  browser window with the microphone on under Options. A paid Loom plan also works if you download
  the MP4; a free Loom can't be downloaded, and Devpost refuses Loom links.
- **Upload** the file to YouTube as **Unlisted**, with embedding allowed (on by default), titled
  "Portfolio Pulse: Deal Flow 2026 demo (Track 3)". Paste the YouTube link into Devpost's video field
  (YouTube, Vimeo or Youku only) and into social-posts.md.

## Shot list

| # | Time | On screen | Voiceover | Caption |
| --- | --- | --- | --- | --- |
| 1 | 0:00–0:12 | Plug and Play fund page, already loaded: the KPI tiles, "Needs your attention" (Eliyan, ApplyBoard, BigID's headcount drop), then 37 company cards sorted by pulse (Veho, BigID and Reco on top at 2:51 PM ET), feed on the right. Slow scroll down the cards. | "This is part of Plug and Play's portfolio: 37 companies from their public startups page, sorted by what changed. Portfolio Pulse reads their news through akta.pro, so the partners don't have to." | Plug and Play · 37 companies · akta.pro news |
| 2 | 0:12–0:28 | Hover one card: favicon, pulse score, category badges, severity dot. Scroll the signal feed. Point at a "Leading indicator" badge, an "Exited · public" card (Dropbox or PayPal), then a "Quiet 90 days" card (Rappi or Visby Medical at 2:51 PM ET). | "Every article becomes a signal: Funding, People, Product, Corporate or Risk, with a severity from one to three. akta's headcount trends add leading indicators. Pulse adds them up, weighted toward the last few days. Exits are marked, and companies with no news say so." | Five signals + leading indicators · severity 1 to 3 · pulse = severity × recency |
| 3 | 0:28–0:42 | Click the Eliyan item in "Needs your attention" ("AI chiplet startup Eliyan draws takeover interest months after $1 billion valuation"). The side panel opens: headline, summary, suggested move, source link, "+1 more report of this story". | "Here's a severity three: Eliyan. Crypto Briefing reports a takeover bid, two months after it raised at a one-billion-dollar valuation; repeat reports of the same story are merged into this one. The suggested move is exit tracking and an LP disclosure. That comes from akta's event tag and a fixed rule, not from the model." | Severity from rules, not the model |
| 4 | 0:42–1:02 | Click **Partner note**. Sentences stream in, each ending in a small [n]. Let it finish. | "Draft action. Claude Opus 5.5, through Nicrron, writes the partner note: what happened, why it matters for our position, what to ask. It only sees numbered sources, and every fact has to cite one. A validator drops any sentence with an uncited fact or a source it wasn't given." | Claude Opus 5.5 via Nicrron · every fact cited |
| 5 | 1:02–1:12 | Click [1]. The akta article opens in a new tab. Pause one second, switch back. | "Click a citation and you're on the article. Nothing here sends itself. The partner copies what they want." | Click any [n] to check it |
| 6 | 1:12–1:38 | Back to the fund page. Click **Generate LP update** (or **Regenerate**). Highlights and Companies to watch stream in. Scroll to the numbered Sources. Click **Download .docx**; open the file in Word for two seconds. | "Once a quarter, the same sources write the LP update: portfolio highlights and companies to watch, every sentence cited, with the source list at the end. Download it as Word and edit it like any other draft." | LP update · cited · .docx |
| 7 | 1:38–1:48 | Click **How signals work**. The rule table opens. Hover the Risk and People rows. | "Anyone can check the logic. This is the whole rule table. Stories that only mention a company stay low, and stock-market posts are dropped. The model never decides severity." | The rules are on screen |
| 8 | 1:48–2:10 | Switch to PRISM. Open the trace of a fresh Eliyan draft and click through it: the agent step (request in, draft out), the `akta_sources` step with its index of every numbered source, and the Nicrron model call with tokens and cost. | "Every draft and LP update is one trace in PRISM by Block Convey: the request and the final draft, an index of every akta source the model was given, and the Nicrron call with its tokens and cost. PRISM reviews every trace automatically, and each citation can be checked against exactly what the model saw." | PRISM: request, sources and model call in one trace |
| 9 | 2:10–2:26 | Switch to Roundtable. Show the signal-watcher bot's task handed to the drafting bot, then the draft file with its author and version, then the LP update file's version history. | "Our agents hand work to each other in Roundtable. When you ask for a draft, a signal-watcher bot hands it to a drafting bot as a task, and the drafter closes it. Drafts and LP updates land in the shared workspace as versioned files." | Roundtable: watcher → drafter · versioned files |
| 10 | 2:26–2:36 | Back to the app home. Click **+ Add a fund**, type the fund's name (or a short form), pick the firm with the **Investor** chip. Cut the wait; land on the new fund page with "Needs your attention" at the top. | "Your fund isn't here? Type its name; typos and short forms work. akta.pro finds every company whose funding rounds list that investor, and the app pulls their news." | + Add a fund · any fund, from akta.pro |
| 11 | 2:36–2:51 | End card: Portfolio Pulse, price, https://portfolio-pulse-portfolio-mo-193e.ninoo.app, team names. | "Portfolio Pulse runs today on Everywhere Ventures, Plug and Play, Betaworks and any fund you add. Four hundred ninety-nine dollars a month for an emerging manager, every seat included. We want three design partners. We'll draft your Q4 LP update." | $499/month per emerging manager · every seat · portfolio-pulse-portfolio-mo-193e.ninoo.app |

## Fill before recording

- Shot 3 is filled (Eliyan). Before recording, confirm the Eliyan item is still in "Needs your
  attention" and the panel's repeat-report line matches the voiceover ("+1 more report" at 2:58 PM
  ET; the voiceover says "repeat reports", so it holds for any count).
- Shot 8 states no PRISM score or pass rate. The automatic review scored one draft 35 before the
  source index and 72 after; the custom citation evaluator failed 5 of 5 traces for reasons in our
  tracing and its judge's window, so it can't yet tell v1 from v2 (devpost-submission.md,
  Challenges). Don't put any of these numbers on screen as a quality claim, and don't mention the
  earlier citation-rule run (39 of 40 failed).
- The Roundtable screens (shot 9): which page shows the handoff best. If the task itself has no page
  in the dashboard, show the drafting bot's recent activity (files it read and wrote) and the draft
  file's author and version.
- Team names for the end card (shot 11). The live URL is filled in.

## Real events (from the live API)

Read at 2:51 PM ET on Oct 24 and unchanged at 2:58 PM ET, after the 2:55 republish.

- **Shots 1 to 5, Plug and Play, Eliyan.** "AI chiplet startup Eliyan draws takeover interest months
  after $1 billion valuation", Crypto Briefing, 2026-10-09, Corporate, severity 3, suggested move
  "Exit tracking; prepare the LP disclosure", one repeat report merged into it ("+1 more report of
  this story").
  https://cryptobriefing.com/eliyan-ai-chiplet-takeover-interest/
  akta's summary: Eliyan has received at least one takeover bid, with options that could value it at
  $3 billion, two months after it raised $145 million at a $1 billion valuation. SDxCentral's Oct 15
  story ("Cisco-backed chiplet interconnect upstart in line for acquisition: report") doesn't name
  Eliyan in its headline, so it is now severity 1, "Mentions the company in passing; no action
  needed". Don't use it for shot 3.
- **Backup, Plug and Play, ApplyBoard.** "ApplyBoard was the worst-performing Canadian startup in
  Fidelity's portfolio in 2026", The Logic, 2026-10-06, Risk, severity 3. Paywalled.
  https://thelogic.co/news/applyboard-valuation-fidelity/
- **If you open on Everywhere.** "Needs your attention" holds one item: Particle
  Health, "Headcount down 29% in 6 months" (Leading indicator, severity 3, suggested move "check in
  with the founder"). There is no severe news from the last 30 days, so change shot 3's voiceover to
  the headcount drop if you use it.
- **If you open on Betaworks.** "Needs your attention" is empty (nothing severe in the last 30 days).
  Hugging Face and The Browser Company show "Exited · acquired" (Nvidia deal; Atlassian). The old
  Arc shutdown event is no longer severity 3. Show Betaworks only for the exits and the empty list.
- **Example of the Eliyan output** (generated earlier today; a new draft will differ): "Reported
  options could value Eliyan at $3 billion, two months after it raised $145 million at a $1 billion
  valuation [n]." Check which article each [n] opens before shot 5.
- **Counts for any voiceover (2:51 PM ET).** Plug and Play: 37 companies, 33 with signals, 163
  signals, 4 at severity 3 (not exited), 3 needing attention. Everywhere: 40, 13, 41, 2, 1.
  Betaworks: 37, 14, 42, 1, 0. Hack VC: 28, 26, 112, 4, 3. The three judging funds: 114 companies,
  60 with signals, 246 signals, 7 at severity 3, 4 needing attention. All four: 142, 86, 358, 11, 7.

## If a shot fails while recording

- **Draft or LP update errors:** re-record that shot with Regenerate. Don't splice in a draft from
  another event.
- **The stream is slow:** cut the wait in editing, but keep the first and last sentence on screen so
  the streaming is visible.
- **Add a fund stalls:** reload the page and open the fund from the home page (its news is saved
  batch by batch), then re-record shot 10 on that fund page.
- **Over 2:51:** trim shots 2 and 7 first. Never cut shots 4, 8 or 9: they show the citation rule,
  PRISM and Roundtable, which the judges are scoring.
