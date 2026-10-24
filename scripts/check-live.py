#!/usr/bin/env python3
"""Check the deployed Portfolio Pulse end to end.

    python3 scripts/check-live.py [--refresh] [--draft] [--lp] [base-url]

Read-only by default (no credits). --refresh pulls live akta news for all three funds (about 30 to
100 credits); --draft and --lp each make one Nicrron call. Prints key names and statuses, never values.
"""
import json
import re
import sys
import time
import urllib.error
import urllib.request

BASE = "https://portfolio-pulse-portfolio-mo-193e.ninoo.app"
FUNDS = ["everywhere-ventures", "plug-and-play", "betaworks"]
args = sys.argv[1:]
for a in args:
    if a.startswith("http"):
        BASE = a.rstrip("/")
    elif a not in ("--refresh", "--draft", "--lp"):
        sys.exit(f"unknown option {a}")
problems = []


def call(path, body=None, timeout=30):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(BASE + path, data=data, method="POST" if body is not None else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        return e.code, raw
    except Exception as e:  # unreachable, timeout
        return 0, str(e)
    return 200, raw


def as_json(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return None


def slug(name):
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")


print("==", BASE)
print("== 1. Keys the backend can see")
code, raw = call("/api/health")
health = as_json(raw) or {}
if not health:
    problems.append("backend unreachable")
    print("   unreachable:", raw[:200])
for k, v in sorted(health.get("keys", {}).items()):
    print(f"   {k:24} {v}")
print("   prism:", health.get("prism"))
for k in ("AKTA_API_KEY", "NICRRON_API_KEY"):
    if health.get("keys", {}).get(k) != "set":
        problems.append(f"{k} not visible to the backend")

print("== 2. Roundtable")
print("  ", call("/api/roundtable/status")[1][:300])

if "--refresh" in args:
    print("== 3. Live refresh (akta credits)")
    for f in FUNDS:
        start, totals = 0, {"with_news": 0, "quiet": 0, "failed": 0, "credits": 0.0}
        while start is not None:
            code, raw = call(f"/api/funds/{f}/refresh?start={start}&count=6", {}, timeout=60)
            r = as_json(raw)
            if code != 200 or not isinstance(r, dict):
                problems.append(f"{f}: refresh failed at {start} (HTTP {code})")
                break
            for k in totals:
                totals[k] += r.get(k) or 0
            if r.get("credit_cap_reached"):
                problems.append(f"{f}: akta credit cap reached")
                break
            start = r.get("next_start")
        print(f"   {f}: {totals}")

print("== 4. What each fund shows")
first_event = None
for f in FUNDS:
    code, raw = call(f"/api/funds/{f}")
    d = as_json(raw) or {}
    if code != 200 or not d:
        print(f"   {f}: HTTP {code}: {raw[:120]}")
        problems.append(f"{f}: fund endpoint failed (HTTP {code})")
        continue
    cs = d.get("companies", [])
    arts = [(c, a) for c in cs for a in (c.get("articles") or [])]
    sev3 = [(c, a) for c, a in arts if a.get("severity") == 3]
    with_news = sum(1 for c in cs if c.get("articles"))
    print(f"   {f}: {len(cs)} companies, {with_news} with news, {len(arts)} signals, "
          f"{len(sev3)} severity 3, last refreshed {d.get('last_refreshed')}")
    top = sorted(cs, key=lambda c: -(c.get("pulse") or 0))[:3]
    print("      top pulse:", ", ".join(f"{c['name']} {c.get('pulse')}" for c in top))
    for c, a in sev3[:3]:
        print(f"      sev 3: {c['name']}: {(a.get('title') or '')[:80]} [{a.get('category')}]")
    if f == "plug-and-play" and arts:
        c, a = (sev3 or arts)[0]
        first_event = {"fund_slug": f, "company_slug": slug(c["name"]),
                       "event_id": str(a.get("id") or a.get("event_id")), "kind": "partner_note"}
    if not arts:
        problems.append(f"{f}: no signals cached")


def check_text(label, out):
    print("  ", out[:1200].replace("\n", "\n   "))
    n = len(re.findall(r"\[\d+\]", out))
    print(f"   citations found: {n}")
    if n == 0:
        problems.append(f"{label}: no citations in the output")


if "--draft" in args:
    print("== 5. Cited partner note (one Nicrron call)")
    if not first_event:
        problems.append("no cached event to draft from (run with --refresh first)")
        print("   no cached event to draft from")
    else:
        print("   request:", json.dumps(first_event))
        check_text("draft", call("/api/draft", first_event, timeout=120)[1])

if "--lp" in args:
    print("== 6. LP update (one Nicrron call)")
    check_text("lp update", call("/api/lp-update", {"fund_slug": "plug-and-play"}, timeout=180)[1])

print("== 7. PRISM eval set")
ev = as_json(call("/api/eval/events")[1])
if isinstance(ev, list):
    print(f"   {len(ev)} events, {sum(1 for e in ev if e.get('synthetic'))} synthetic")
else:
    print("   /api/eval/events unavailable")

print("RESULT:", "OK" if not problems else "needs attention")
for p in problems:
    print("   -", p)
sys.exit(1 if problems else 0)
