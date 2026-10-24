# scripts/roundtable-setup.py: run on your own machine (not in Ninoo): python3 scripts/roundtable-setup.py Creates two Roundtable bots and saves their keys.
import getpass, json, os, urllib.request, uuid

BASE = "https://roundtable.bot/api/tools/"
team_key = getpass.getpass("Roundtable team key (hidden): ").strip()

def call(tool, **args):
    req = urllib.request.Request(
        BASE + tool, data=json.dumps(args).encode(), method="POST",
        headers={"Authorization": f"Bearer {team_key}", "Content-Type": "application/json",
                 "User-Agent": "portfolio-pulse-setup/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

banks = call("list_banks")
banks = banks if isinstance(banks, list) else banks.get("banks", [])
team = [b["bank"] for b in banks
        if b.get("access") == "write" and b["bank"] != "shared-notes"
        and not (b["bank"].startswith("agent-") and len(b["bank"]) == 38)]
if len(team) != 1:
    raise SystemExit(f"Expected one writable team folder, found: {team}. Set project by hand.")
project = team[0]

lines = [f"ROUNDTABLE_PROJECT={project}"]
for name in ("signal-watcher", "drafter"):
    res = call("create_subagent", request_id=str(uuid.uuid4()), name=name,
               client="custom-agent", access={project: "write"})
    prefix = name.upper().replace("-", "_")
    lines.append(f"{prefix}_KEY={res['token']}")
    if name == "drafter":
        lines.append(f"DRAFTER_ID={res['assistant']['id']}")

fd = os.open(".env.roundtable", os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
with os.fdopen(fd, "w") as f:
    f.write("\n".join(lines) + "\n")
print("Wrote .env.roundtable (4 lines, git-ignored). Paste each value into Ninoo Secrets, then delete the file.")
