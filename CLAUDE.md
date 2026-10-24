# Portfolio Pulse: notes for working on this repo

What it is, how it works and what's next: README.md. The roadmap is GitHub issue #1.

## Layout
- `src/`: React 19 + Vite + TypeScript + Tailwind v4. `src/App.tsx` holds most of the UI.
- `api/`: FastAPI backend. `main.py` (data, signal rules, drafts, LP updates, the shared stores),
  `citations.py` (citation check), `tracing.py` (PRISM), `roundtable.py` (Roundtable client).
- `api/data/funds.json`: the built-in funds. `api/data/snapshot/`: committed cache served right after
  a publish. Runtime caches go to `api/cache/` (git-ignored).

## Check every change
- `.venv/bin/python -m pytest -q api` and `npx tsc --noEmit -p .` and `npx vite build`.
- The signal rules are deterministic; the model never decides severity. Keep `api/test_signals.py`
  in step with any rule change.

## Deploy
The app is hosted by Ninoo Builder (ninoo.app). Two remotes:
- `origin` is Ninoo Git. Push to `main`; Ninoo adds a "Merged ... (pushed to main)" commit, so
  `git fetch origin && git rebase origin/main` before pushing. Then press Publish in the Ninoo
  project (Publish -> "Publish latest changes"). Secrets live in Ninoo Secrets, never in the repo.
- `github` is this public repo. Its history is separate: mirror the tree with
  `git commit-tree "$(git rev-parse HEAD^{tree})" -p github/main -m "..."` and push that commit to
  `refs/heads/main` (in zsh write `"${C}:refs/heads/main"`).

## Hosting constraints that shaped the code
- Requests stop at 30 s, so news refresh runs in batches of 4 companies with a time budget.
- The backend runs as several instances with separate disks: funds added live and generated drafts
  and LP updates are stored in the team's Roundtable folder (`funds/`, `cache/`). Check a file exists
  before reading it; Roundtable counts a missing-file read as a failed request.
- Roundtable files hold at most 200,000 characters.

## Secrets
Never print or commit keys. Local values go in `.env` (backend) or `.env.local` (scripts), both
git-ignored. Variable names are listed in the README.
