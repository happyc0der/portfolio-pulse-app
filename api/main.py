import asyncio
import json
import os
import time
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from api import tracing
from api.citations import citation_checked_text
from api.tracing import citation_metrics, prism_enabled, prism_selftest, traced_chat
from api import roundtable
from dotenv import dotenv_values, load_dotenv

app = FastAPI()

@app.middleware("http")
async def json_error_middleware(request, call_next):
    try:
        return await call_next(request)
    except HTTPException as exc:
        return JSONResponse(status_code=exc.status_code, content={"error": exc.detail if isinstance(exc.detail, str) else "request_error", "detail": exc.detail})
    except Exception as exc:
        import logging, traceback
        logging.getLogger("portfolio_pulse").error("Unhandled API error: %s\n%s", exc, traceback.format_exc())
        return JSONResponse(status_code=500, content={"error": "internal_server_error", "detail": str(exc)})

API_DIR = Path(__file__).resolve().parent
ENV_FILE = API_DIR.parent / ".env"
# All backend reads are relative to api/. Choose a writable cache root at runtime.
_API_CACHE_CANDIDATE = API_DIR / "cache"
try:
    _API_CACHE_CANDIDATE.mkdir(parents=True, exist_ok=True)
    _probe = _API_CACHE_CANDIDATE / ".write-probe"
    _probe.write_text("ok", encoding="utf-8")
    _probe.unlink(missing_ok=True)
    DATA_DIR = _API_CACHE_CANDIDATE
except OSError:
    DATA_DIR = Path("/tmp/portfolio-pulse")
    DATA_DIR.mkdir(parents=True, exist_ok=True)
BASE_DIR = API_DIR
load_dotenv(ENV_FILE, override=False)
SECRET_NAMES = ("AKTA_API_KEY", "NICRRON_API_KEY", "PRISMTRACE_API_KEY", "PRISMTRACE_PROJECT_ID", "PRISMTRACE_HOST", "ROUNDTABLE_PROJECT", "SIGNAL_WATCHER_KEY", "DRAFTER_KEY", "DRAFTER_ID")


def get_secret(name: str) -> str:
    value = os.environ.get(name, "")
    if value and value.strip():
        return value.strip()
    # Re-read dotenv on demand: keys may be added after this long-lived process starts.
    try:
        value = dotenv_values(ENV_FILE).get(name, "") or ""
    except Exception:
        value = ""
    return str(value).strip()


FUNDS_FILE = API_DIR / "data" / "funds.json"
CACHE_DIR = DATA_DIR
CACHE_DIR.mkdir(parents=True, exist_ok=True)
# A committed copy of the cache (same layout), refreshed before the demo. The published backend's
# disk resets on every publish, so reads fall back to it whenever the live cache has no file.
SNAPSHOT_DIR = API_DIR / "data" / "snapshot"


def snapshot_refreshed_at() -> float | None:
    try:
        return float(json.loads((SNAPSHOT_DIR / "manifest.json").read_text(encoding="utf-8"))["refreshed_at"])
    except (OSError, ValueError, KeyError, TypeError):
        return None


def cache_file(*parts: str) -> Path:
    live = CACHE_DIR.joinpath(*parts)
    if live.is_file():
        return live
    snapshot = SNAPSHOT_DIR.joinpath(*parts)
    return snapshot if snapshot.is_file() else live
AKTA_BASE = "https://api.akta.pro/api/v1"
NICRRON_BASE_URL = "https://api.nicrron.ai/v1"


def roundtable_config() -> tuple[bool, str]:
    required = ("ROUNDTABLE_PROJECT", "SIGNAL_WATCHER_KEY", "DRAFTER_KEY", "DRAFTER_ID")
    missing = [name for name in required if not get_secret(name)]
    return (not missing, "missing " + ", ".join(missing) if missing else "configured")


CUSTOM_FUNDS_FILE = "custom_funds.json"


def read_custom_funds() -> list[dict[str, Any]]:
    try:
        funds = json.loads(cache_file(CUSTOM_FUNDS_FILE).read_text(encoding="utf-8"))
        return [fund for fund in funds if isinstance(fund, dict) and fund.get("slug")] if isinstance(funds, list) else []
    except (OSError, json.JSONDecodeError):
        return []


# The published backend runs as several server instances, each with its own temporary disk, so a
# fund added live on one instance was missing on the others (QA saw it vanish within minutes). Each
# added fund and its news are saved as one file in the team's Roundtable folder, and any instance
# that lacks it loads it from there.
SHARED_FUNDS_PREFIX = "funds/"
SHARED_FUNDS_TTL = 20.0
SLIM_ARTICLE_FIELDS = ("id", "title", "url", "publisher", "published_date", "sentiment", "tags", "article_type", "ai_summary", "original_language", "newsworthiness_score", "is_breaking")
_shared_seen: dict[str, Any] = {"at": 0.0, "sizes": {}}


def slim_article(article: dict[str, Any]) -> dict[str, Any]:
    """Roundtable files hold at most 200,000 characters, so a shared fund keeps only what the rules,
    drafts and LP updates read."""
    slim = {field: article[field] for field in SLIM_ARTICLE_FIELDS if field in article}
    slim["ai_summary"] = str(slim.get("ai_summary") or "")[:350]
    slim["tags"] = [{"code": tag.get("code"), "name": tag.get("name")} for tag in (article.get("tags") or [])[:2] if isinstance(tag, dict)]
    return slim


def write_json_atomic(path: Path, data: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    os.replace(temp, path)


def shared_fund_bundle(slug: str, fund: dict[str, Any], companies: list[dict[str, Any]] | None = None, base: dict[str, Any] | None = None) -> dict[str, Any]:
    bundle = base if isinstance(base, dict) else {"news": {}, "filters": {}, "search": {}}
    bundle["fund"] = {key: value for key, value in fund.items() if key != "companies"}
    bundle["fund"]["companies"] = [{key: value for key, value in company.items() if key in {"name", "website", "uuid"}} for company in fund["companies"]]
    for company in fund["companies"] if companies is None else companies:
        key = slugify(company["name"])
        recent = sorted(read_articles(slug, company["name"]), key=lambda article: str(article.get("published_date", "")), reverse=True)[:10]
        bundle.setdefault("news", {})[key] = [slim_article(article) for article in recent]
        try:
            bundle.setdefault("filters", {})[key] = json.loads(cache_file(slug, f"{key}.filters.json").read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            pass
        search = read_akta_cache(company["name"], "search")
        if search:
            bundle.setdefault("search", {})[key] = search
    bundle["saved_at"] = time.time()
    return bundle


async def save_shared_fund(slug: str, companies: list[dict[str, Any]] | None = None) -> None:
    connected, _ = roundtable_config()
    fund = next((item for item in read_custom_funds() if item["slug"] == slug), None)
    if not connected or fund is None:
        return
    key, bank, path = get_secret("SIGNAL_WATCHER_KEY"), get_secret("ROUNDTABLE_PROJECT"), f"{SHARED_FUNDS_PREFIX}{slug}.json"
    base = None
    if companies is not None:
        # Batches of one import can run on different instances: merge into what is saved.
        current = await roundtable.call("read_file", key, {"bank": bank, "path": path})
        try:
            base = json.loads(current["content"]) if isinstance(current, dict) and current.get("content") else None
        except (TypeError, ValueError):
            base = None
        if base is None:
            companies = None
    bundle = shared_fund_bundle(slug, fund, companies, base)
    await roundtable.call("write_file", key, {"bank": bank, "path": path, "content": json.dumps(bundle, ensure_ascii=False), "message": f"Fund added live: {fund['name']}"})
    _shared_seen["at"] = 0.0


def apply_shared_bundle(bundle: dict[str, Any]) -> None:
    fund = bundle.get("fund") or {}
    slug = fund.get("slug")
    if not slug:
        return
    others = [item for item in read_custom_funds() if item["slug"] != slug]
    write_json_atomic(CACHE_DIR / CUSTOM_FUNDS_FILE, others + [fund])
    for key, articles in (bundle.get("news") or {}).items():
        if articles:
            write_json_atomic(CACHE_DIR / slug / f"{key}.json", articles)
    for key, meta in (bundle.get("filters") or {}).items():
        write_json_atomic(CACHE_DIR / slug / f"{key}.filters.json", meta)
    for key, search in (bundle.get("search") or {}).items():
        path = AKTA_CACHE_DIR / key / "search.json"
        if not path.is_file():
            write_json_atomic(path, search)


def hydrate_shared_funds() -> None:
    connected, _ = roundtable_config()
    if not connected or time.time() - _shared_seen["at"] < SHARED_FUNDS_TTL:
        return
    _shared_seen["at"] = time.time()
    key, bank = get_secret("SIGNAL_WATCHER_KEY"), get_secret("ROUNDTABLE_PROJECT")
    listing = roundtable.call_sync("list_files", key, {"bank": bank, "prefix": SHARED_FUNDS_PREFIX})
    rows = listing.get("files", []) if isinstance(listing, dict) else listing if isinstance(listing, list) else []
    for row in rows:
        path, size = str(row.get("path") or ""), row.get("size")
        if not path.endswith(".json") or _shared_seen["sizes"].get(path) == size:
            continue
        found = roundtable.call_sync("read_file", key, {"bank": bank, "path": path})
        try:
            apply_shared_bundle(json.loads(found["content"]))
            _shared_seen["sizes"][path] = size
        except (TypeError, ValueError, KeyError, OSError):
            continue


def load_funds() -> list[dict[str, Any]]:
    hydrate_shared_funds()
    with FUNDS_FILE.open(encoding="utf-8") as source:
        data = json.load(source)
    builtin = {fund["slug"] for fund in data}
    # Funds added live from the home page (akta-built portfolios) come after the built-in ones.
    data += [fund for fund in read_custom_funds() if fund["slug"] not in builtin]
    for fund in data:
        for company in fund.get("companies", []):
            company.setdefault("articles", [])
    return data


def slugify(value: str) -> str:
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", value.lower())).strip("-")


def get_fund(slug: str) -> dict[str, Any]:
    fund = next((item for item in load_funds() if item.get("slug") == slug), None)
    if fund is None:
        raise HTTPException(status_code=404, detail="Fund not found")
    return fund


def company_domain(website: str) -> str:
    parsed = urlparse(website if "://" in website else f"https://{website}")
    return parsed.netloc or parsed.path


def read_articles(fund_slug: str, company_name: str) -> list[dict[str, Any]]:
    path = cache_file(fund_slug, f"{slugify(company_name)}.json")
    if not path.is_file():
        return []
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, list) else []
    except (OSError, json.JSONDecodeError):
        return []


def akta_cache_for(company: dict[str, Any], endpoint: str) -> dict[str, Any] | None:
    """Cached akta company data, only when akta's company match has this company's website.
    A name match once gave Eliyan the data of "Eliya Chocolates"."""
    search = read_akta_cache(company["name"], "search") or {}
    match = (search.get("data") or {}).get("match") if isinstance(search.get("data"), dict) else None
    if match and not same_domain(match.get("website", ""), company.get("website", "")):
        return None
    return search if endpoint == "search" else read_akta_cache(company["name"], endpoint)


def same_domain(first: str, second: str) -> bool:
    clean = lambda value: company_domain(value or "").lower().removeprefix("www.")
    return bool(clean(first)) and clean(first) == clean(second)


def company_signals(slug: str, company: dict[str, Any], articles: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    articles = read_articles(slug, company["name"]) if articles is None else articles
    clean, irrelevant, language = filter_company_articles(company, articles)
    market = [article for article in clean if is_market_noise(article)]
    clean = [article for article in clean if not is_market_noise(article)]
    classified = [signal for article in clean if (signal := classify_article(article, company)) is not None]
    merged, duplicates = merge_repeat_reports(classified, company)
    indicators = [{**event, "id": f"{slugify(company['name'])}-{event['id']}"} for event in derive_indicator_events(akta_cache_for(company, "A"))]
    return {"articles": clean, "signals": merged + indicators, "indicators": indicators, "filtered_irrelevant": irrelevant, "filtered_language": language, "filtered_market": len(market), "filtered_duplicates": duplicates}


def fund_with_cache(slug: str) -> dict[str, Any]:
    fund = get_fund(slug)
    for company in fund["companies"]:
        company["articles"] = read_articles(slug, company["name"])
        cache_path = cache_file(slug, f"{slugify(company['name'])}.json")
        company["cached_at"] = cache_path.stat().st_mtime if cache_path.is_file() else None
        company["from_snapshot"] = cache_path.is_relative_to(SNAPSHOT_DIR)
        company["lookup_status"] = "unknown"
        if not company["articles"] and cache_path.is_file():
            try:
                cached_data = json.loads(cache_path.read_text(encoding="utf-8"))
                company["lookup_status"] = cached_data.get("lookup_status", "unknown") if isinstance(cached_data, dict) else "unknown"
                company["articles"] = cached_data.get("articles", []) if isinstance(cached_data, dict) else cached_data
            except (OSError, json.JSONDecodeError):
                pass
        clean_articles, inferred_irrelevant, inferred_language = filter_company_articles(company, company["articles"])
        filter_meta_path = cache_file(slug, f"{slugify(company['name'])}.filters.json")
        try:
            filter_meta = json.loads(filter_meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            filter_meta = {}
        filtered_irrelevant = int(filter_meta.get("filtered_irrelevant", inferred_irrelevant))
        filtered_language = int(filter_meta.get("filtered_language", inferred_language))
        built = company_signals(slug, company, company["articles"])
        all_signals = built["signals"]
        company["filtered_irrelevant"] = filtered_irrelevant
        company["filtered_language"] = filtered_language
        company["filtered_market"] = built["filtered_market"]
        company["filtered_duplicates"] = built["filtered_duplicates"]
        company["filtered_count"] = max(0, len(read_articles(slug, company["name"])) - len(all_signals))
        company["indicator_events"] = built["indicators"]
        company["articles"] = all_signals
        company["pulse"] = calculate_pulse(all_signals)
        # akta's company search reports public / acquired companies. For a VC those are exits:
        # their stock moves and insider sales are not portfolio events, so the UI keeps them out
        # of "Needs your attention" and the severity counts.
        search = akta_cache_for(company, "search") or {}
        match = (search.get("data") or {}).get("match") if isinstance(search.get("data"), dict) else None
        status = str((match or {}).get("company_status") or "").lower()
        correction = EXIT_CORRECTIONS.get(company["name"].casefold())
        if correction and status not in EXITED_STATUSES:
            status = "acquired"
        company["company_status"] = status or None
        company["exit_note"] = correction
        company["exited"] = status in EXITED_STATUSES
        if company["from_snapshot"]:
            company["cached_at"] = snapshot_refreshed_at() or company["cached_at"]
    # Active companies first (exits last), then by pulse.
    fund["companies"].sort(key=lambda company: (company["exited"], not company["articles"], -company["pulse"], company["name"].casefold()))
    timestamps = [company["cached_at"] for company in fund["companies"] if company["cached_at"] is not None]
    fund["last_refreshed"] = max(timestamps) if timestamps else None
    return fund


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "prism": "on" if prism_enabled() else "off", "prism_last_error": tracing.last_tracing_error, "keys": {name: "set" if get_secret(name) else "missing" for name in SECRET_NAMES}}


def history_versions(result: Any) -> list[dict[str, Any]]:
    if isinstance(result, list):
        return result
    if isinstance(result, dict):
        versions = result.get("versions", result.get("history", result.get("items", [])))
        return versions if isinstance(versions, list) else []
    return []


@app.get("/api/prism/selftest")
def prism_trace_selftest() -> dict[str, Any]:
    return prism_selftest()


@app.get("/api/roundtable/status")
def roundtable_status() -> dict[str, Any]:
    connected, reason = roundtable_config()
    return {"connected": connected, "reason": reason if not connected else "connected"}


@app.get("/api/roundtable/history")
async def roundtable_history(path: str) -> dict[str, Any]:
    connected, reason = roundtable_config()
    if not connected:
        return {"connected": False, "reason": reason, "versions": []}
    files = await roundtable_files(get_secret("SIGNAL_WATCHER_KEY"), get_secret("ROUNDTABLE_PROJECT"), path)
    return {"connected": files is not None, "reason": roundtable.last_error if files is None else "", "versions": files or []}


async def roundtable_files(key: str, bank: str, path: str) -> list[dict[str, Any]] | None:
    # Roundtable's get_folder_history answers "Folder not found" for our folders, so list the
    # shared folder's files instead and keep those under the requested path.
    result = await roundtable.call("list_files", key, {"bank": bank})
    if result is None:
        return None
    folder = path.strip("/")
    if "." in folder.rsplit("/", 1)[-1]:
        folder = folder.rsplit("/", 1)[0] if "/" in folder else ""
    return [{"version": item["path"], "created_at": f"{item.get('size', 0)} bytes"}
            for item in (result if isinstance(result, list) else [])
            if isinstance(item, dict) and str(item.get("path", "")).startswith(folder)]


@app.get("/api/roundtable/selftest")
async def roundtable_selftest() -> dict[str, Any]:
    connected, reason = roundtable_config()
    if not connected:
        return {"connected": False, "reason": reason, "banks": None, "write": None}
    key, bank = get_secret("SIGNAL_WATCHER_KEY"), get_secret("ROUNDTABLE_PROJECT")
    banks = await roundtable.call("list_banks", key, {})
    wrote = await roundtable.call("write_file", key, {"bank": bank, "path": "selftest/portfolio-pulse.json", "content": json.dumps({"ok": True, "timestamp": utcnow().isoformat()}), "message": "Portfolio Pulse connection self-test"})
    return {"connected": banks is not None and wrote is not None, "reason": "ok" if banks is not None and wrote is not None else (roundtable.last_error or "Roundtable request failed"), "banks": banks, "write": wrote}


@app.get("/api/funds")
def list_funds() -> list[dict[str, Any]]:
    result = []
    for fund in load_funds():
        result.append({"slug": fund["slug"], "name": fund["name"], "company_count": len(fund["companies"]), "custom": bool(fund.get("custom"))})
    return result


INVESTOR_WORDS = ("venture", "capital", "invest", "private equity", "fund", "accelerator", "angel")


@app.get("/api/akta/search")
async def akta_company_search(q: str = "") -> dict[str, Any]:
    """Search-as-you-type over akta's company search (free). Investment firms are listed first."""
    query = q.strip()
    if len(query) < 2:
        return {"results": []}
    api_key = get_secret("AKTA_API_KEY")
    if not api_key:
        return {"results": [], "error": "akta.pro is not connected"}
    async with httpx.AsyncClient() as client:
        response = await client.get(f"{AKTA_BASE}/company/search/", params={"query": query}, headers={"x-api-key": api_key}, timeout=20)
    if response.status_code == 204:
        return {"results": []}
    if response.status_code != 200:
        return {"results": [], "error": f"akta.pro search failed (HTTP {response.status_code})"}
    results = []
    for row in (response.json().get("data") or [])[:10]:
        if not isinstance(row, dict) or not row.get("uuid"):
            continue
        category = str(row.get("product_category") or "")
        results.append({"uuid": row["uuid"], "name": row.get("name") or "", "website": row.get("website") or "",
                        "category": category, "status": row.get("company_status"),
                        "is_investor": any(word in category.lower() for word in INVESTOR_WORDS)})
    results.sort(key=lambda item: not item["is_investor"])
    return {"results": results[:8]}


class FundImportRequest(BaseModel):
    uuid: str
    name: str
    website: str | None = None


@app.post("/api/funds/import")
async def import_fund(request: FundImportRequest) -> dict[str, Any]:
    """Build a fund's portfolio from akta: companies whose funding rounds list this investor."""
    api_key = get_secret("AKTA_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="akta.pro is not connected")
    if cap_reached():
        raise HTTPException(status_code=429, detail="akta credit cap reached")
    builtin = {fund["slug"]: fund for fund in json.loads(FUNDS_FILE.read_text(encoding="utf-8"))}
    slug = slugify(request.name) or slugify(request.uuid)
    if slug in builtin:
        return {"slug": slug, "name": builtin[slug]["name"], "company_count": len(builtin[slug]["companies"]), "total_matches": None, "credits": 0, "existing": True}
    hydrate_shared_funds()
    added = next((fund for fund in read_custom_funds() if fund["slug"] == slug), None)
    if added and any(read_articles(slug, company["name"]) for company in added["companies"]):
        return {"slug": slug, "name": added["name"], "company_count": len(added["companies"]), "total_matches": None, "credits": 0, "existing": True}
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    bodies = [{"filters": {"funding_detail.funding_rounds.investors.uuid": [request.uuid]}, "limit": 25},
              {"query": f"portfolio companies of the venture capital firm {request.name}", "limit": 25}]
    payload: dict[str, Any] = {}
    async with httpx.AsyncClient() as client:
        for body in bodies:
            response = await client.post(f"{AKTA_BASE}/list/generate/companies/", json=body, headers=headers, timeout=150)
            if response.status_code == 200:
                payload = response.json()
                break
    credits = float(payload.get("credits_consumed") or 0)
    ledger_add(credits)
    companies, seen = [], set()
    for row in payload.get("data") or []:
        website = str(row.get("website") or "").strip().rstrip("/")
        if not website or not row.get("name"):
            continue
        website = website if website.startswith("http") else f"https://{website}"
        website = website.replace("http://", "https://")
        key = company_domain(website).lower().removeprefix("www.")
        name_key = str(row["name"]).strip().casefold()
        if key in seen or name_key in seen:
            continue
        seen.update({key, name_key})
        companies.append({"name": row["name"], "website": website})
    if not companies:
        raise HTTPException(status_code=404, detail=f"akta.pro has no portfolio companies on record for {request.name}")
    total = payload.get("total_count")
    fund = {"slug": slug, "name": request.name, "sourceUrl": request.website or "", "custom": True,
            "sourceNote": f"Portfolio assembled live by akta.pro: List Generation on funding rounds that list {request.name} as an investor ({total if total is not None else len(companies)} companies; top {len(companies)} shown).",
            "companies": companies}
    custom = [item for item in read_custom_funds() if item["slug"] != slug] + [fund]
    path = CACHE_DIR / CUSTOM_FUNDS_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    # Write then rename, so a request reading the fund list never sees a half-written file.
    temp = path.with_suffix(".tmp")
    temp.write_text(json.dumps(custom, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp, path)
    await save_shared_fund(slug)
    return {"slug": slug, "name": request.name, "company_count": len(companies), "total_matches": total, "credits": credits, "existing": False}


@app.get("/api/funds/{slug}")
def read_fund(slug: str) -> dict[str, Any]:
    return fund_with_cache(slug)


@app.get("/api/funds/{slug}/companies/{company_slug}/status")
async def company_status(slug: str, company_slug: str) -> dict[str, Any]:
    fund = get_fund(slug)
    company = next((item for item in fund["companies"] if slugify(item["name"]) == company_slug), None)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    api_key = get_secret("AKTA_API_KEY")
    if not api_key:
        return {"status": "unavailable", "message": "AKTA_API_KEY is not configured."}
    try:
        async with httpx.AsyncClient() as client:
            response = await akta_request(client, "/company/search/", {"query": company.get("website", "")}, api_key)
        if response.status_code != 200:
            return {"status": "unavailable"}
        data = response.json().get("data", [])
        domain = company_domain(company.get("website", "")).lower().removeprefix("www.")
        found = any(company_domain(item.get("website", "")).lower().removeprefix("www.") == domain for item in data)
        return {"status": "found" if found else "not_found"}
    except (httpx.HTTPError, ValueError, TypeError):
        return {"status": "unavailable"}


async def akta_request(client: httpx.AsyncClient, path: str, params: dict[str, Any], api_key: str) -> httpx.Response:
    return await client.get(f"{AKTA_BASE}{path}", params=params, headers={"x-api-key": api_key}, timeout=30.0, follow_redirects=False)


async def fetch_company_news(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, fund_slug: str, company: dict[str, Any], api_key: str) -> dict[str, Any]:
    async with semaphore:
        website = company.get("website", "")
        try:
            response = await akta_request(client, "/news/", {
                "primary_company": website,
                "start_date": (date.today() - timedelta(days=90)).isoformat(),
                "limit": 20,
                "group_articles": "true",
            }, api_key)
            credits = 0
            raw_count = 0
            filtered_irrelevant = 0
            filtered_language = 0
            articles: list[dict[str, Any]] = []
            if response.status_code == 204:
                articles = []
            elif response.status_code == 401:
                found = await lookup_company(client, semaphore, website, api_key)
                return {"status": "failed", "articles": [], "credits": 0, "error": "invalid_key" if found else "company_not_found_in_akta"}
            elif response.status_code == 403:
                found = await lookup_company(client, semaphore, website, api_key)
                return {"status": "failed", "articles": [], "credits": 0, "error": "plan_required" if found else "company_not_found_in_akta"}
            elif response.is_error:
                found = await lookup_company(client, semaphore, website, api_key)
                return {"status": "failed", "articles": [], "credits": 0, "error": f"akta_http_{response.status_code}" if found else "company_not_found_in_akta"}
            else:
                payload = response.json()
                credits = float(payload.get("credits_consumed") or 0)
                ledger_add(credits)
                raw_articles = [sanitize_article(item) for item in payload.get("data", []) if isinstance(item, dict)]
                deduplicated_articles = deduplicate_articles(raw_articles)
                articles, filtered_irrelevant, filtered_language = filter_company_articles(company, deduplicated_articles)
                raw_count = len(deduplicated_articles)
            cache_path = CACHE_DIR / fund_slug / f"{slugify(company['name'])}.json"
            cache_path.parent.mkdir(parents=True, exist_ok=True)
            cache_path.write_text(json.dumps(articles, ensure_ascii=False, indent=2), encoding="utf-8")
            filter_meta_path = CACHE_DIR / fund_slug / f"{slugify(company['name'])}.filters.json"
            filter_meta_path.write_text(json.dumps({"filtered_irrelevant": filtered_irrelevant, "filtered_language": filtered_language}, indent=2), encoding="utf-8")
            signals = [signal for article in articles if (signal := classify_article(article)) is not None]
            return {"status": "news" if signals else "quiet", "articles": articles, "credits": credits, "filtered": max(0, raw_count - len(signals)), "filtered_irrelevant": filtered_irrelevant if response.status_code != 204 else 0, "filtered_language": filtered_language if response.status_code != 204 else 0}
        except (httpx.HTTPError, ValueError, TypeError, OSError) as exc:
            await lookup_company(client, semaphore, website, api_key)
            return {"status": "failed", "articles": [], "credits": 0, "error": str(exc)}


def sanitize_article(article: dict[str, Any]) -> dict[str, Any]:
    # `tags` is the live schema. Only fall back to the older `types` key when
    # the response does not contain `tags` at all (an explicitly empty tags list is meaningful).
    tags = article.get("tags") if "tags" in article else article.get("types", [])
    entities = article.get("entities") if isinstance(article.get("entities"), dict) else {}
    return {
        "id": article.get("id"),
        "group_id": article.get("group_id"),
        "title": article.get("title"),
        "url": article.get("url"),
        "publisher": article.get("publisher"),
        "published_date": article.get("published_date"),
        "original_language": article.get("original_language"),
        "sentiment": str(article.get("sentiment") or "neutral").lower(),
        "newsworthiness_score": article.get("newsworthiness_score"),
        "ai_summary": article.get("ai_summary"),
        "tags": tags if isinstance(tags, list) else [],
        "is_press_release": bool(article.get("is_press_release", False)),
        "is_breaking": bool(article.get("is_breaking", False)),
        "article_type": article.get("article_type"),
        "sentiment_score": article.get("sentiment_score"),
        "entities": {"person": entities.get("person", [])},
    }


def article_primary_tag(article: dict[str, Any]) -> dict[str, Any] | None:
    tags = article.get("tags") or []
    primary = next((tag for tag in tags if isinstance(tag, dict) and tag.get("is_primary")), None)
    chosen = primary or next((tag for tag in tags if isinstance(tag, dict)), None)
    return chosen


def article_day(article: dict[str, Any]) -> str:
    return str(article.get("published_date") or "")[:10]


def article_tag_code(article: dict[str, Any]) -> str | None:
    tag = article_primary_tag(article)
    return str(tag.get("code")) if tag and tag.get("code") else None


def deduplicate_articles(articles: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Select one representative per story group, preferring an English source,
    # then newsworthiness. Missing group IDs are kept as separate articles.
    grouped: dict[str, list[dict[str, Any]]] = {}
    standalone: list[dict[str, Any]] = []
    for article in articles:
        group_id = article.get("group_id")
        if group_id:
            grouped.setdefault(str(group_id), []).append(article)
        else:
            standalone.append(article)
    chosen: list[dict[str, Any]] = []
    for group in grouped.values():
        chosen.append(max(group, key=lambda item: (str(item.get("original_language") or "").upper() == "EN", float(item.get("newsworthiness_score") or 0))))
    # Remove translated duplicates where an English article on the same day has
    # the same primary tag, even when the provider assigned different group IDs.
    english_keys = {
        (article_day(item), article_tag_code(item))
        for item in chosen + standalone
        if str(item.get("original_language") or "").upper() == "EN" and article_tag_code(item)
    }
    chosen.extend(standalone)
    deduped = [item for item in chosen if not (str(item.get("original_language") or "").upper() != "EN" and article_primary_tag(item) and (article_day(item), article_tag_code(item)) in english_keys)]
    return sorted(deduped, key=lambda item: str(item.get("published_date") or ""), reverse=True)


EXITED_STATUSES = {"public", "acquired"}  # akta also reports "delisted" for some startups, so it is not used
# akta.pro still lists these acquired companies as private; each correction names its source.
EXIT_CORRECTIONS = {
    "the browser company": "Acquired by Atlassian (announced September 2025)",
    "zestyai": "Acquired by Aon (FinTech Futures, September 2026)",
    "hugging face": "Joining Nvidia in a $12.9 billion deal (reported October 2026)",
}
# Robo-written market posts (analyst ratings, price targets, fund position changes, insider trades)
# say nothing about how the company is doing.
MARKET_NOISE = re.compile(r"\([A-Z]{2,5}\)|price target|\bEPS\b|earnings per share|(?:shares|stock|stake|position|holdings) (?:of|in) |(?:buys|sells|acquires|trims|lifts|boosts|raises|lowers|cuts|reduces|increases|takes) (?:its |a |new )?(?:stake|position|holdings)|insider (?:sale|sell|buy|trad)|short interest|(?:NYSE|NASDAQ|Nasdaq|NYSEARCA|OTCMKTS):|(?:upgraded|downgraded|reiterated|initiated) (?:by|at|to)|analyst rating", re.IGNORECASE)
MARKET_PUBLISHERS = {"marketbeat", "defense world", "etf daily news", "ticker report", "the lincolnian online", "americanbankingnews", "zolmax", "the enterprise leader", "wkrb news", "modern readers", "the cerbat gem", "dispatch tribunal", "the markets daily", "stock titan", "marketscreener", "insidermonkey"}
RAISE_WORDS = re.compile(r"\b(?:raises?|raised|raising|secures?|secured|closes?|closed|lands?|landed|bags?|nabs?|gets?|announces?|completes?|valuation|funding|round|invests?|investment)\b", re.IGNORECASE)
LEADER_CHANGE = re.compile(r"\b(?:steps? down|stepping down|resign\w*|ousted|replac\w*|depart\w*|fired|leaves|leaving|out as|succeed\w*)\b", re.IGNORECASE)
SHUTDOWN = re.compile(r"\b(?:shut(?:s|ting)? down|shutter\w*|discontinu\w*|sunset\w*|wind(?:s|ing)? down|lay(?:s|ing)? off|layoffs?|job cuts|cuts? (?:\d+ )?jobs)\b", re.IGNORECASE)


def is_market_noise(article: dict[str, Any]) -> bool:
    publisher = str(article.get("publisher") or "").strip().casefold()
    return publisher in MARKET_PUBLISHERS or bool(MARKET_NOISE.search(str(article.get("title") or "")))


def raise_is_theirs(company: dict[str, Any], title: str) -> bool:
    """A funding headline is the company's own raise only when the company comes before the raise
    ("Ramp Secures $1.85 Billion"), not "Lagos Life developer raises $500,000 ... with Flutterwave"."""
    verb = RAISE_WORDS.search(title)
    if not verb:
        return True
    return company_named(company, title[:verb.start()])


def company_named(company: dict[str, Any], text: str) -> bool:
    """The company itself is named, not just its industry: needed before anything becomes severity 3."""
    return article_is_relevant(company, {"title": text, "ai_summary": ""})


def merge_repeat_reports(signals: list[dict[str, Any]], company: dict[str, Any] | None = None) -> tuple[list[dict[str, Any]], int]:
    """One story arrives many times (the Eliyan bid three times, the Granola lawsuit five). Signals of
    the same category at severity 2 or 3 within 7 days of each other are one story: keep the strongest
    report and count the others on it."""
    def day(signal: dict[str, Any]) -> date | None:
        try:
            return date.fromisoformat(str(signal.get("published_date", ""))[:10])
        except ValueError:
            return None
    def strength(signal: dict[str, Any]) -> tuple:
        named = bool(company) and company_named(company, str(signal.get("title") or ""))
        return (signal.get("severity", 0), named, float(signal.get("newsworthiness_score") or 0), str(signal.get("published_date", "")))
    kept: list[dict[str, Any]] = []
    stories: list[list[dict[str, Any]]] = []
    for signal in sorted(signals, key=lambda item: str(item.get("published_date", ""))):
        when = day(signal)
        if signal.get("indicator") or signal.get("severity", 0) < 2 or when is None:
            kept.append(signal)
            continue
        story = next((group for group in stories if group[-1]["category"] == signal["category"] and (when - day(group[-1])).days <= 7), None)
        if story is None:
            stories.append([signal])
        else:
            story.append(signal)
    merged = 0
    for story in stories:
        best = max(story, key=strength)
        kept.append({**best, "duplicates": len(story) - 1})
        merged += len(story) - 1
    kept.sort(key=lambda item: str(item.get("published_date", "")), reverse=True)
    return kept, merged
# akta sometimes labels Spanish, German, Portuguese, French or Italian articles as "EN".
# Two or more of these common function words in a headline mean it is not English.
NON_ENGLISH_WORDS = {
    "el", "los", "las", "del", "una", "por", "para", "con", "como", "que", "der", "die", "das", "und",
    "mit", "für", "ist", "nicht", "auf", "dos", "das", "não", "uma", "com", "pelo", "les", "des", "une",
    "pour", "avec", "est", "dans", "della", "degli", "nel", "sono", "anche",
}


def looks_non_english(text: str) -> bool:
    words = re.findall(r"[a-zà-ÿ]+", (text or "").lower())
    hits = sum(1 for word in words if word in NON_ENGLISH_WORDS)
    letters = re.findall(r"[^\W\d_]", text or "")
    non_latin = sum(1 for ch in letters if ord(ch) > 0x24F)
    return hits >= 2 or (bool(letters) and non_latin / len(letters) > 0.3)


def company_main_word(company: dict[str, Any]) -> str:
    company_name = re.sub(r"\b(incorporated|corporation|company|technologies|technology|insurance|health|labs|laboratories|group|inc|llc|ltd|co)\b", " ", company.get("name", ""), flags=re.IGNORECASE)
    words = re.findall(r"[a-z0-9]+", company_name.lower())
    if words:
        return words[0]
    domain = company_domain(company.get("website", "")).lower().removeprefix("www.")
    return re.split(r"[.-]", domain)[0]


def article_is_relevant(company: dict[str, Any], article: dict[str, Any]) -> bool:
    title_summary = f"{article.get('title') or ''} {article.get('ai_summary') or ''}".casefold()
    name = str(company.get("name") or "").strip().casefold()
    main_word = company_main_word(company).casefold()
    if name and name in title_summary:
        return True
    # Company names are sometimes naturally spaced in article text (e.g. "Fishwife").
    compact_name = re.sub(r"[^a-z0-9]+", "", name)
    compact_text = re.sub(r"[^a-z0-9]+", "", title_summary)
    if compact_name and compact_name in compact_text:
        return True
    return bool(main_word and re.search(rf"(?<![a-z0-9]){re.escape(main_word)}(?![a-z0-9])", title_summary))


def filter_company_articles(company: dict[str, Any], articles: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], int, int]:
    kept: list[dict[str, Any]] = []
    irrelevant = language = 0
    for article in articles:
        if str(article.get("original_language") or "").strip().upper() != "EN" or looks_non_english(str(article.get("title") or "")):
            language += 1
            continue
        if not article_is_relevant(company, article):
            irrelevant += 1
            continue
        kept.append(article)
    return kept, irrelevant, language


def sum_credits(responses: list[dict[str, Any]]) -> float:
    return round(sum(float(item.get("credits", 0) or 0) for item in responses), 4)


SIGNAL_RULES: dict[str, tuple[str, int, str]] = {
    "CM01": ("Funding", 2, "Congratulate; offer intros to later-stage investors"),
    "CM02": ("Funding", 2, "Congratulate; offer intros to later-stage investors"),
    "CM09": ("Funding", 2, "Congratulate; offer intros to later-stage investors"),
    "WT02": ("People-negative", 3, "Check-in call with the founder this week"),
    "LG04": ("People-negative", 3, "Check-in call with the founder this week"),
    "LG01": ("People-positive", 1, "Congratulate the new leader"),
    "WT01": ("People-positive", 1, "Congratulate the new leader"),
    "LG02": ("People-positive", 1, "Congratulate the new leader"),
    "SD01": ("Product", 1, "Amplify it; offer customer intros"),
    "SD02": ("Product", 1, "Amplify it; offer customer intros"),
    "SD03": ("Product", 1, "Amplify it; offer customer intros"),
    "SD04": ("Product", 1, "Amplify it; offer customer intros"),
    "SD05": ("Product", 1, "Amplify it; offer customer intros"),
    "SD08": ("Product", 1, "Amplify it; offer customer intros"),
    "SD11": ("Product", 1, "Amplify it; offer customer intros"),
    "II01": ("Product", 1, "Amplify it; offer customer intros"),
    "II02": ("Product", 1, "Amplify it; offer customer intros"),
    "CM03": ("Corporate", 3, "Exit tracking; prepare the LP disclosure"),
    "CM04": ("Corporate", 3, "Exit tracking; prepare the LP disclosure"),
    "CM05": ("Corporate", 3, "Exit tracking; prepare the LP disclosure"),
    "CM06": ("Corporate", 3, "Exit tracking; prepare the LP disclosure"),
    "CM07": ("Corporate", 3, "Exit tracking; prepare the LP disclosure"),
    "CM11": ("Corporate", 3, "Exit tracking; prepare the LP disclosure"),
    "RC03": ("Risk", 3, "Risk flag: call the founder, prepare an LP note"),
    "RC06": ("Risk", 3, "Risk flag: call the founder, prepare an LP note"),
    "RC07": ("Risk", 3, "Risk flag: call the founder, prepare an LP note"),
    "RK04": ("Risk", 3, "Risk flag: call the founder, prepare an LP note"),
    "RK05": ("Risk", 3, "Risk flag: call the founder, prepare an LP note"),
    "RK06": ("Risk", 3, "Risk flag: call the founder, prepare an LP note"),
    "RK07": ("Risk", 3, "Risk flag: call the founder, prepare an LP note"),
}


REPORTED_NEWS_TYPES = {"news_analysis", "investigative"}


def classify_article(article: dict[str, Any], company: dict[str, Any] | None = None) -> dict[str, Any] | None:
    tag = article_primary_tag(article)
    code = str(tag.get("code") or "").upper() if tag else ""
    rule = SIGNAL_RULES.get(code)
    if not rule:
        return None
    category, severity, action = rule
    sentiment = str(article.get("sentiment") or "neutral").lower()
    if code == "LG01":
        category, severity, action = ("People-negative", 3, "Check-in call with the founder this week") if sentiment == "negative" else ("People-positive", 1, "Congratulate the new leader")
    # Negative sentiment escalates only reported news. Explainers, opinion, reviews and promotional
    # pieces about a launch are not risks to the company (akta marks ~2/3 of articles "explainer").
    article_type = str((article.get("article_type") or {}).get("code") or "news_analysis").lower()
    title = str(article.get("title") or "")
    if code in {"LG01", "LG02", "WT01"} and LEADER_CHANGE.search(title):
        category, severity, action = "People-negative", 3, "Check-in call with the founder this week"
    elif category == "Product" and SHUTDOWN.search(title):
        category, severity, action = "Risk", 2, "Read it; check in with the founder"
    elif category in {"Funding", "Product", "People-positive"} and sentiment == "negative" and article_type in REPORTED_NEWS_TYPES:
        # A down round or writedown is serious; bad press about a product or a hire is worth a read.
        category, severity, action = ("Risk", 3, "Risk flag: call the founder, prepare an LP note") if category == "Funding" else ("Risk", 2, "Negative coverage: read it before the next founder call")
    # Severity 3 asks a partner to act today, so it needs reported news that names the company in the
    # headline. Opinion pieces, explainers, listicles and industry stories that mention it drop to 2.
    named = company is None or company_named(company, title)
    if named and company is not None and category == "Funding" and not raise_is_theirs(company, title):
        named = False
    if severity == 3 and (article_type not in REPORTED_NEWS_TYPES or not named):
        severity = 2
        action = "Track it; confirm with the founder before telling LPs" if category == "Corporate" else "Read it; raise it on the next founder call"
    # The action has to fit the story: a passing mention asks for nothing, and bad news is never
    # met with "Congratulate" or "Amplify it".
    if not named:
        severity, action = (min(severity, 2), "Industry story that mentions the company: read it before the next founder call") if category == "Risk" else (1, "Mentions the company in passing; no action needed")
    elif sentiment == "negative" and category in {"Product", "Funding", "People-positive"}:
        action = {"Product": "Read it; check whether customers are affected", "Funding": "Read it; ask the founder about the round and runway"}.get(category, "Read it; check in with the founder")
    elif sentiment == "neutral" and category == "Product":
        action = "Note it for the next portfolio update"
    return {**article, "category": "People" if category.startswith("People-") else category, "severity": severity, "suggested_action": action, "tag_code": code, "tag_name": str(tag.get("name") or "")}


def calculate_pulse(articles: list[dict[str, Any]], today: date | None = None) -> float:
    current = today or date.today()
    total = 0.0
    for article in articles:
        try:
            published = datetime.fromisoformat(str(article.get("published_date", "")).replace("Z", "+00:00"))
            published_day = published.date()
        except (ValueError, TypeError):
            continue
        days = max(0, (current - published_day).days)
        total += int(article.get("severity", 0)) * (0.5 ** (days / 90))
    return round(total, 1)


def derive_indicator_events(headcount_cache: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not headcount_cache or headcount_cache.get("status") != "ok":
        return []
    envelope = headcount_cache.get("data") or {}
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if not isinstance(data, dict):
        return []
    events: list[dict[str, Any]] = []
    total = data.get("total_employees")
    periods = data.get("growth_periods") or []
    six_month = next((period.get("change_percentage") for period in periods if period.get("month_difference") == 6), None)
    event_date = str(data.get("date") or headcount_cache.get("fetched_at") or utcnow().date().isoformat())[:10]
    if isinstance(total, (int, float)) and total >= 20 and isinstance(six_month, (int, float)) and six_month <= -5:
        severity = 3 if six_month <= -10 else 2
        events.append({"id": f"headcount-{event_date}", "category": "Leading indicator", "severity": severity, "suggested_action": f"Headcount down {abs(six_month):g}% in 6 months: check in with the founder", "title": f"Headcount down {abs(six_month):g}% in 6 months", "published_date": event_date, "indicator": True, "indicator_type": "headcount"})
    if isinstance(total, (int, float)) and total >= 20 and isinstance(six_month, (int, float)) and six_month >= 20:
        events.append({"id": f"headcount-up-{event_date}", "category": "Leading indicator", "severity": 1, "suggested_action": "Hiring fast: ask which roles; offer candidate intros", "title": f"Headcount up {six_month:g}% in 6 months", "published_date": event_date, "indicator": True, "indicator_type": "headcount growth"})
    monthly = sorted(data.get("headcount_monthly") or [], key=lambda row: str(row.get("date", "")))
    if len(monthly) >= 4:
        latest, prior = monthly[-1], monthly[-4]
        latest_count, prior_count = latest.get("employee_count"), prior.get("employee_count")
        if isinstance(latest_count, (int, float)) and isinstance(prior_count, (int, float)) and prior_count > 0:
            pct = (latest_count / prior_count - 1) * 100
            if pct <= -5 and not any(e["indicator_type"] in {"headcount", "headcount growth"} for e in events):
                events.append({"id": f"headcount-monthly-{latest.get('date')}", "category": "Leading indicator", "severity": 2, "suggested_action": f"Headcount down {abs(pct):.0f}% over 3 months: check in with the founder", "title": f"Headcount down {abs(pct):.0f}% over 3 months", "published_date": str(latest.get("date", event_date))[:10], "indicator": True, "indicator_type": "headcount"})
    return events


async def lookup_company(client: httpx.AsyncClient, semaphore: asyncio.Semaphore, website: str, api_key: str) -> bool:
    # Search is a best-effort diagnostic only; refresh results still report the news error.
    try:
        async with semaphore:
            response = await akta_request(client, "/company/search/", {"query": website}, api_key)
        if response.status_code == 200:
            matches = response.json().get("data", [])
            domain = company_domain(website).lower().removeprefix("www.")
            return any(company_domain(item.get("website", "")).lower().removeprefix("www.") == domain for item in matches)
    except (httpx.HTTPError, ValueError, TypeError):
        pass
    return False


async def record_company_status(companies: list[dict[str, Any]], api_key: str) -> None:
    """Free akta company search for companies with no cached status, so exits (public companies)
    are recognised in funds imported live. Best effort: a failure leaves the company active."""
    missing = [company for company in companies if not read_akta_cache(company["name"], "search")]
    if not missing:
        return
    async with httpx.AsyncClient() as client:
        async def one(company: dict[str, Any]) -> None:
            try:
                response = await client.get(f"{AKTA_BASE}/company/search/", params={"query": company["website"]}, headers={"x-api-key": api_key}, timeout=15)
                rows = response.json().get("data", []) if response.status_code == 200 else []
            except (httpx.HTTPError, ValueError):
                return
            domain = company_domain(company["website"]).lower().removeprefix("www.")
            match = next((row for row in rows if company_domain(row.get("website", "")).lower().removeprefix("www.") == domain), None)
            write_akta_cache(company["name"], "search", {"id": (match or {}).get("uuid") or company["website"], "product_category": (match or {}).get("product_category"), "match": match}, "ok" if match else "no_data", 0)
        await asyncio.gather(*(one(company) for company in missing))


# The published backend stops a request at 30 s, and akta allows 8 headcount calls a minute, so the
# headcount pass runs in parallel inside what is left of this budget. Cached results are kept; the
# rest refresh on the next run.
SLICE_BUDGET_S = 18


async def refresh_headcount(companies: list[dict[str, Any]], budget: float) -> None:
    async def one(company: dict[str, Any]) -> None:
        try:
            search = await resolve_akta_company(company)
            resolved = search.get("data", {}) if isinstance(search.get("data"), dict) else {}
            await fetch_akta_endpoint(company, "A", resolved.get("id") or company.get("website"))
        except Exception:
            pass
    try:
        await asyncio.wait_for(asyncio.gather(*(one(company) for company in companies)), budget)
    except asyncio.TimeoutError:
        pass


async def refresh_fund_slice(slug: str, start: int = 0, count: int = 6) -> dict[str, Any]:
    fund = get_fund(slug)
    companies = fund.get("companies", [])
    start = max(0, start)
    count = min(6, max(1, count))
    selected = companies[start:start + count]
    with_news = quiet = failed = 0
    credits = 0.0
    api_key = get_secret("AKTA_API_KEY")
    if not api_key:
        return {"done": 0, "next_start": None, "with_news": 0, "quiet": 0, "failed": len(selected), "credits": 0, "message": "Akta not connected"}
    started = asyncio.get_running_loop().time()
    semaphore = asyncio.Semaphore(3)
    async with httpx.AsyncClient() as client:
        results = await asyncio.gather(*(fetch_company_news(client, semaphore, slug, company, api_key) for company in selected))
    await record_company_status(selected, api_key)
    if any(item["slug"] == slug for item in read_custom_funds()):
        await save_shared_fund(slug, selected)
    for result in results:
        if result.get("status") == "news": with_news += 1
        elif result.get("status") == "quiet": quiet += 1
        else: failed += 1
    credits = sum_credits(results)
    # Headcount refresh for the highest-pulse ten happens once the slice reaches fund end.
    next_start = start + len(selected)
    if next_start >= len(companies):
        remaining = SLICE_BUDGET_S - (asyncio.get_running_loop().time() - started)
        if remaining > 2:
            await refresh_headcount(fund_with_cache(slug)["companies"][:10], remaining)
    return {"done": len(selected), "next_start": next_start if next_start < len(companies) else None, "with_news": with_news, "quiet": quiet, "failed": failed, "credits": credits, "credits_total": float(ledger_read().get("credits_consumed", 0)), "credit_cap_reached": cap_reached()}


@app.post("/api/funds/{slug}/refresh")
async def refresh_fund(slug: str, start: int = 0, count: int = 6) -> dict[str, Any]:
    return await refresh_fund_slice(slug, start, count)


# Akta secondary data integration. Each company is keyed by its existing portfolio slug.
AKTA_CACHE_DIR = CACHE_DIR / "akta"
AKTA_CACHE_TTL = {"search": None, "A": 14, "B": 14, "C": 7, "D": 14, "E": 30}
AKTA_PATHS = {
    "search": "/company/search/", "A": "/company/headcount-trends/", "B": "/company/website-traffic/",
    "C": "/company/jobs/", "D": "/company/enrichment/", "E": "/list/generate/companies/",
}
LONG_TIMEOUT_ENDPOINTS = {"A", "B", "C"}
REQUEST_SEMAPHORE = asyncio.Semaphore(3)
RATE_LOCK = asyncio.Lock()
PATH_REQUESTS: dict[str, list[float]] = {}
AKTA_STOPPED = False


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def akta_company_dir(company_name: str) -> Path:
    return AKTA_CACHE_DIR / slugify(company_name)


def read_akta_cache(company_name: str, endpoint: str) -> dict[str, Any] | None:
    path = cache_file("akta", slugify(company_name), f"{endpoint}.json")
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        return payload if isinstance(payload, dict) else None
    except (OSError, json.JSONDecodeError):
        return None


def cache_is_fresh(entry: dict[str, Any] | None, endpoint: str) -> bool:
    if not entry:
        return False
    if entry.get("status") == "not_on_plan":
        ttl = 1
    elif entry.get("status") == "no_data":
        ttl = 7
    else:
        ttl = AKTA_CACHE_TTL.get(endpoint)
    if ttl is None:
        return True
    try:
        fetched = datetime.fromisoformat(str(entry["fetched_at"]).replace("Z", "+00:00"))
        return utcnow() - fetched < timedelta(days=ttl)
    except (KeyError, ValueError, TypeError):
        return False


def write_akta_cache(company_name: str, endpoint: str, data: Any, status: str = "ok", credits: float = 0) -> dict[str, Any]:
    payload = {"status": status, "data": data, "fetched_at": utcnow().isoformat(), "credits_consumed": credits}
    path = akta_company_dir(company_name) / f"{endpoint}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return payload


def ledger_read() -> dict[str, Any]:
    path = cache_file("akta", "ledger.json")
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {"credits_consumed": 0.0}
    except (OSError, json.JSONDecodeError):
        return {"credits_consumed": 0.0}


def ledger_add(credits: float) -> float:
    ledger = ledger_read()
    ledger["credits_consumed"] = round(float(ledger.get("credits_consumed", 0)) + float(credits or 0), 4)
    ledger["updated_at"] = utcnow().isoformat()
    AKTA_CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (AKTA_CACHE_DIR / "ledger.json").write_text(json.dumps(ledger, indent=2), encoding="utf-8")
    return float(ledger["credits_consumed"])


def credit_cap() -> float:
    try:
        return float(os.getenv("AKTA_CREDIT_CAP", "150"))
    except ValueError:
        return 150.0


def cap_reached() -> bool:
    return float(ledger_read().get("credits_consumed", 0)) >= credit_cap()


async def rate_limit_path(path: str) -> None:
    # Sliding one-minute path-specific window; no more than 8 started requests.
    while True:
        async with RATE_LOCK:
            now = asyncio.get_running_loop().time()
            recent = [stamp for stamp in PATH_REQUESTS.get(path, []) if now - stamp < 60]
            PATH_REQUESTS[path] = recent
            if len(recent) < 8:
                recent.append(now)
                PATH_REQUESTS[path] = recent
                return
            wait = max(0.05, 60 - (now - recent[0]))
        await asyncio.sleep(wait)


async def request_akta(client: httpx.AsyncClient, method: str, path: str, *, params: dict[str, Any] | None = None, json_body: dict[str, Any] | None = None, endpoint: str = "other") -> httpx.Response:
    global AKTA_STOPPED
    api_key = get_secret("AKTA_API_KEY")
    if not api_key or AKTA_STOPPED:
        raise RuntimeError("AKTA_NOT_CONNECTED")
    timeout = 120.0 if endpoint in LONG_TIMEOUT_ENDPOINTS else 30.0
    for attempt in range(2):
        await rate_limit_path(path)
        async with REQUEST_SEMAPHORE:
            response = await client.request(method, f"{AKTA_BASE}{path}", params=params, json=json_body, headers={"x-api-key": api_key}, timeout=timeout, follow_redirects=False)
        if response.status_code == 401:
            AKTA_STOPPED = True
            return response
        if (response.status_code == 429 or response.status_code >= 500) and attempt == 0:
            await asyncio.sleep(5)
            continue
        return response
    return response


def response_credits(response: httpx.Response) -> float:
    try:
        body = response.json()
        return float(body.get("credits_consumed") or 0) if isinstance(body, dict) else 0.0
    except (ValueError, TypeError):
        return 0.0


def normalize_response(response: httpx.Response) -> tuple[str, Any, float]:
    credits = response_credits(response)
    if response.status_code == 401:
        return "unauthorized", None, credits
    if response.status_code == 403:
        return "not_on_plan", None, credits
    if response.status_code == 204:
        return "no_data", None, credits
    if response.is_error:
        return "error", None, credits
    try:
        payload = response.json()
    except ValueError:
        return "no_data", None, credits
    data = payload.get("data") if isinstance(payload, dict) else None
    if data is None or data == [] or data == {}:
        return "no_data", data, credits
    return "ok", payload, credits


async def fetch_akta_endpoint(company: dict[str, Any], endpoint: str, company_id: str | None = None, *, force: bool = False) -> dict[str, Any]:
    name = company["name"]
    cached = read_akta_cache(name, endpoint)
    if not force and cache_is_fresh(cached, endpoint):
        return cached or {}
    if endpoint == "search":
        return await resolve_akta_company(company, force=force)
    if cap_reached():
        return {"status": "credit_cap", "data": None, "fetched_at": None, "credits_consumed": 0}
    if not get_secret("AKTA_API_KEY"):
        return {"status": "not_connected", "data": None, "fetched_at": None, "credits_consumed": 0}
    async with httpx.AsyncClient() as client:
        if endpoint == "search":
            method, path, params, body = "GET", AKTA_PATHS[endpoint], {"query": company.get("website", "")}, None
        elif endpoint == "E":
            category = company.get("product_category") or "technology"
            method, path, params, body = "POST", AKTA_PATHS[endpoint], None, {"query": f"private {category} companies", "limit": 8}
        else:
            method, path, params, body = "GET", AKTA_PATHS[endpoint], {"company": company_id or company.get("akta_id") or company.get("website", "")}, None
            if endpoint == "C":
                params["limit"] = 10
            if endpoint == "D":
                params["sections"] = "firmographic,strategic_signal,management_profile,financial_estimate,funding_detail"
        try:
            response = await request_akta(client, method, path, params=params, json_body=body, endpoint=endpoint)
        except (httpx.HTTPError, RuntimeError):
            return {"status": "error", "data": None, "fetched_at": None, "credits_consumed": 0}
    status, payload, credits = normalize_response(response)
    if credits:
        ledger_add(credits)
    if status == "unauthorized":
        return {"status": status, "data": None, "fetched_at": None, "credits_consumed": credits}
    if status == "error":
        return {"status": status, "data": None, "fetched_at": None, "credits_consumed": credits}
    if status == "not_on_plan":
        return write_akta_cache(name, endpoint, None, status, credits)
    data = payload
    # Cache plan/no-data statuses with their shorter fixed TTLs.
    return write_akta_cache(name, endpoint, data, status, credits)


async def resolve_akta_company(company: dict[str, Any], force: bool = False) -> dict[str, Any]:
    cached = read_akta_cache(company["name"], "search")
    if not force and cache_is_fresh(cached, "search"):
        return cached or {}
    if cap_reached():
        return cached or {"status": "credit_cap", "data": {"id": company.get("website", ""), "product_category": None}, "credits_consumed": 0}
    if not get_secret("AKTA_API_KEY"):
        return {"status": "not_connected", "data": {"id": company.get("website", ""), "product_category": None}, "credits_consumed": 0}
    result = await fetch_akta_endpoint(company, "search", force=force)
    if result.get("status") in {"ok", "no_data"}:
        found = (((result.get("data") or {}).get("data") or []) if isinstance(result.get("data"), dict) else [])
        first = next((row for row in found if isinstance(row, dict) and same_domain(row.get("website", ""), company.get("website", ""))), None)
        id_value = first.get("uuid") if first else None
        category = first.get("product_category") if first else None
        # fetch_akta_endpoint already recorded search credits in the ledger; preserve them in its cache.
        result = write_akta_cache(company["name"], "search", {"id": id_value or company.get("website", ""), "product_category": category, "match": first}, result.get("status", "no_data"), result.get("credits_consumed", 0))
    return result


async def load_company_akta(fund_slug: str, company_slug: str, do_refresh: bool = False, endpoints: tuple[str, ...] = ("D", "B", "C")) -> dict[str, Any]:
    fund = get_fund(fund_slug)
    company = next((item for item in fund["companies"] if slugify(item["name"]) == company_slug), None)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    search = await resolve_akta_company(company)
    match = search.get("data", {}).get("match") if isinstance(search.get("data"), dict) else None
    company_id = (search.get("data", {}).get("id") if isinstance(search.get("data"), dict) else None) or company.get("website", "")
    product_category = (match or {}).get("product_category") or (search.get("data", {}).get("product_category") if isinstance(search.get("data"), dict) else None)
    company["product_category"] = product_category
    output: dict[str, Any] = {"company": {"name": company["name"], "website": company["website"], "id": company_id, "product_category": product_category}, "endpoints": {"search": search}}
    if do_refresh:
        tasks = [fetch_akta_endpoint(company, endpoint, company_id) for endpoint in endpoints]
        results = await asyncio.gather(*tasks)
        output["endpoints"].update(dict(zip(endpoints, results)))
    else:
        for endpoint in ("A", "B", "C", "D"):
            output["endpoints"][endpoint] = read_akta_cache(company["name"], endpoint)
            entry = output["endpoints"][endpoint]
            if entry and entry.get("status") in {"not_on_plan", "no_data"} and not cache_is_fresh(entry, endpoint):
                output["endpoints"][endpoint] = {"status": "retry", "data": None, "fetched_at": entry.get("fetched_at"), "credits_consumed": 0}
    output["credit_cap_reached"] = cap_reached()
    output["api_key_missing"] = not bool(get_secret("AKTA_API_KEY"))
    return output


@app.get("/api/credits")
def credits_status() -> dict[str, float]:
    return {"credits_consumed": float(ledger_read().get("credits_consumed", 0)), "credit_cap": credit_cap()}


@app.get("/api/companies/{fund_slug}/{company_slug}/akta")
async def company_akta_cached(fund_slug: str, company_slug: str) -> dict[str, Any]:
    return await load_company_akta(fund_slug, company_slug, False)


@app.post("/api/companies/{fund_slug}/{company_slug}/akta/refresh")
async def company_akta_refresh(fund_slug: str, company_slug: str) -> dict[str, Any]:
    return await load_company_akta(fund_slug, company_slug, True)


DRAFT_SYSTEM_PROMPT = "You are a VC platform associate. Write plain, specific sentences. Every sentence that states a fact must end with a citation like [2] to one of the provided sources. Never invent facts. If the sources do not support a claim, leave it out."
DRAFT_CACHE_DIR = CACHE_DIR / "drafts"


# Generated drafts and LP updates are shared through the team's Roundtable folder: whoever opens one
# first waits for the model, and every server instance serves it after that.
SHARED_CACHE_PREFIX = "cache/"


async def shared_cache_get(name: str) -> dict[str, Any] | None:
    connected, _ = roundtable_config()
    if not connected:
        return None
    found = await roundtable.call("read_file", get_secret("SIGNAL_WATCHER_KEY"), {"bank": get_secret("ROUNDTABLE_PROJECT"), "path": f"{SHARED_CACHE_PREFIX}{name}"})
    try:
        return json.loads(found["content"]) if isinstance(found, dict) and found.get("content") else None
    except (TypeError, ValueError):
        return None


async def shared_cache_put(name: str, data: dict[str, Any]) -> None:
    connected, _ = roundtable_config()
    content = json.dumps(data, ensure_ascii=False)
    if connected and len(content) < 190_000:
        await roundtable.call("write_file", get_secret("SIGNAL_WATCHER_KEY"), {"bank": get_secret("ROUNDTABLE_PROJECT"), "path": f"{SHARED_CACHE_PREFIX}{name}", "content": content, "message": f"Generated {name}"})


def draft_cache_path(fund_slug: str, event_id: str, kind: str, version: str = "v2") -> Path:
    # One draft per version, so the v1/v2 comparison never shows the other version's cached text.
    key = slugify(f"{fund_slug}-{event_id}-{kind}-{version}")
    return DRAFT_CACHE_DIR / f"{key}.json"


def collect_draft_sources(fund_slug: str, company: dict[str, Any], event_id: str) -> list[dict[str, Any]]:
    articles = company_signals(fund_slug, company)["articles"]
    cutoff = date.today() - timedelta(days=90)
    recent: list[dict[str, Any]] = []
    for article in articles:
        try:
            published = date.fromisoformat(str(article.get("published_date", ""))[:10])
        except ValueError:
            continue
        if published >= cutoff:
            recent.append(article)
    clicked = next((article for article in recent if str(article.get("id")) == str(event_id)), None)
    recent.sort(key=lambda article: str(article.get("published_date", "")), reverse=True)
    if clicked:
        recent.remove(clicked)
        recent.insert(0, clicked)
    sources: list[dict[str, Any]] = []
    for article in recent:
        sources.append({
            "number": len(sources) + 1,
            "title": article.get("title") or "Untitled article",
            "publisher": article.get("publisher") or "Unknown publisher",
            "date": article.get("published_date"),
            "url": article.get("url"),
            "ai_summary": article.get("ai_summary") or "",
            "kind": "article",
            "event_id": str(article.get("id") or ""),
        })
    for endpoint, label in (("A", "headcount trends"), ("B", "website traffic"), ("C", "jobs"), ("D", "enrichment")):
        cached = akta_cache_for(company, endpoint)
        if not cached or cached.get("status") != "ok":
            continue
        data = cached.get("data") or {}
        endpoint_data = data.get("data") if isinstance(data, dict) else None
        if not endpoint_data:
            continue
        as_of = endpoint_data.get("date") if isinstance(endpoint_data, dict) else None
        as_of = as_of or str(cached.get("fetched_at", ""))[:10]
        sources.append({"number": len(sources) + 1, "title": f"{company['name']}: akta.pro {label}, as of {as_of}", "publisher": "akta.pro", "date": as_of, "url": None, "ai_summary": json.dumps(endpoint_data, ensure_ascii=False), "kind": "indicator"})
    return sources


from pydantic import BaseModel


class DraftRequest(BaseModel):
    fund_slug: str
    company_slug: str
    event_id: str
    kind: str
    regenerate: bool = False
    version: str = "v2"


async def roundtable_event_draft(request: "DraftRequest", company: dict[str, Any], sources: list[dict[str, Any]], output: dict[str, Any]) -> dict[str, Any]:
    connected, reason = roundtable_config()
    if not connected: return {"connected": False, "reason": reason}
    bank, project = get_secret("ROUNDTABLE_PROJECT"), get_secret("ROUNDTABLE_PROJECT")
    watcher_key, drafter_key = get_secret("SIGNAL_WATCHER_KEY"), get_secret("DRAFTER_KEY")
    company_slug = slugify(company["name"])
    file_path = f"signals/{company_slug}/{request.event_id}.json"
    event_obj = next((source for source in sources if str(source.get("event_id")) == request.event_id), None) or next((source for source in sources if source.get("kind") == "article"), {})
    signal_content = {"event": event_obj, "source_articles": [{"title": source.get("title"), "url": source.get("url"), "date": source.get("date")} for source in sources if source.get("kind") == "article"]}
    written = await roundtable.call("write_file", watcher_key, {"bank": bank, "path": file_path, "content": json.dumps(signal_content, ensure_ascii=False), "message": f"Signal: {company['name']}, {event_obj.get('title','signal')}, severity {event_obj.get('severity',1)}"})
    if written is None: return {"connected": False, "reason": roundtable.last_error or "Signal save failed"}
    versions = [{"bank": bank, "path": file_path, "version": extract_version(written)}]
    created = await roundtable.call("claim_task", watcher_key, {"project": project, "assignee": get_secret("DRAFTER_ID"), "goal": f"Draft partner note for {company['name']}: {event_obj.get('title','portfolio event')}", "input": {"kind": "event_draft", "path": file_path, "event_id": request.event_id}})
    task_id = extract_task_id(created)
    if not task_id: return {"connected": False, "reason": roundtable.last_error or "Task creation failed"}
    status, task_error = "available", None
    task_version = None
    available = await roundtable.call("list_tasks", drafter_key, {"project": project, "assignee": "me", "status": "available"})
    task = find_task(available, task_id)
    if task:
        task_version = task.get("version")
        claimed = await roundtable.call("claim_task", drafter_key, {"project": project, "task_id": task_id, "expected_version": task_version})
        if claimed is None: task_error = roundtable.last_error or "Could not claim drafting task"
        elif isinstance(claimed, dict): task_version = claimed.get("version", task_version)
    else: task_error = "Task was not available to Drafter"
    fetched = await roundtable.call("get_task", drafter_key, {"task_id": task_id})
    read_result = await roundtable.call("read_file", drafter_key, {"bank": bank, "path": file_path})
    if fetched is None or read_result is None: task_error = task_error or roundtable.last_error or "Could not read task input"
    draft_path = f"drafts/{request.event_id}.md"
    write_draft = await roundtable.call("write_file", drafter_key, {"bank": bank, "path": draft_path, "content": output.get("text", ""), "message": f"Cited draft for {company['name']}"})
    if write_draft is not None: versions.append({"bank": bank, "path": draft_path, "version": extract_version(write_draft)})
    if write_draft is None: task_error = task_error or roundtable.last_error or "Draft file write failed"
    status = "blocked" if task_error else "done"
    task_result = {"summary": "Cited draft prepared" if status == "done" else "Draft handoff failed", "sources": versions, "data": {"event_id": request.event_id}}
    status, close_error = await roundtable_close_task(watcher_key, drafter_key, task_id, task_version, status, task_result if status == "done" else {"error": task_error}, "Cited draft written")
    return {"connected": True, "task_id": task_id, "status": status, "sources": versions, "reason": task_error or close_error or ""}


async def roundtable_close_task(watcher_key: str, drafter_key: str, task_id: str, version: Any, status: str, result: dict[str, Any], progress: str) -> tuple[str, str | None]:
    """The Drafter closes its task, then the Signal Watcher reads the status back, so the app shows
    what Roundtable recorded. update_task takes progress as text, and get_task takes only task_id
    (any other field is rejected as "Invalid arguments", which left every task open before)."""
    updated = await roundtable.call("update_task", drafter_key, {"task_id": task_id, "expected_version": version, "status": status, "progress": progress if status == "done" else "", "result": result})
    if updated is None:
        return "not closed", roundtable.last_error or "Could not close the task"
    latest = await roundtable.call("get_task", watcher_key, {"task_id": task_id})
    return (latest.get("status", status) if isinstance(latest, dict) else status), None


def extract_version(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    version = result.get("version_id") or result.get("version") or (result.get("file", {}).get("version") if isinstance(result.get("file"), dict) else None)
    # write_file returns the version as an object; the app links to its id.
    return str(version.get("id")) if isinstance(version, dict) and version.get("id") else version if isinstance(version, str) else None


def extract_task_id(result: Any) -> str | None:
    if not isinstance(result, dict):
        return None
    task = result.get("task") if isinstance(result.get("task"), dict) else result
    value = task.get("task_id") or task.get("id")
    return str(value) if value else None


def find_task(result: Any, task_id: str) -> dict[str, Any] | None:
    if isinstance(result, dict):
        rows = result.get("tasks", result.get("items", []))
        if isinstance(rows, list):
            return next((row for row in rows if isinstance(row, dict) and str(row.get("task_id") or row.get("id")) == task_id), None)
        if str(result.get("task_id") or result.get("id")) == task_id:
            return result
    if isinstance(result, list):
        return next((row for row in result if isinstance(row, dict) and str(row.get("task_id") or row.get("id")) == task_id), None)
    return None


@app.post("/api/draft")
async def draft_action(request: DraftRequest) -> dict[str, Any]:
    if request.kind not in {"partner_note", "founder_email"}:
        raise HTTPException(status_code=400, detail="kind must be partner_note or founder_email")
    if request.version not in {"v1", "v2"}:
        raise HTTPException(status_code=400, detail="version must be v1 or v2")
    fund = get_fund(request.fund_slug)
    company = next((item for item in fund["companies"] if slugify(item["name"]) == request.company_slug), None)
    if company is None:
        raise HTTPException(status_code=404, detail="Company not found")
    cache_path = draft_cache_path(request.fund_slug, request.event_id, request.kind, request.version)
    # Server instances keep separate disks: local copy, then the committed snapshot, then the team folder.
    cached_path = cache_file("drafts", cache_path.name)
    if cached_path.is_file() and not request.regenerate:
        try:
            cached_draft = json.loads(cached_path.read_text(encoding="utf-8"))
            cached_draft["cached"] = True
            return cached_draft
        except (OSError, json.JSONDecodeError):
            pass
    if not request.regenerate and (shared := await shared_cache_get(f"drafts/{cache_path.name}")):
        write_json_atomic(cache_path, shared)
        shared["cached"] = True
        return shared
    api_key = get_secret("NICRRON_API_KEY")
    if not api_key:
        raise HTTPException(status_code=503, detail="Nicrron AI is not connected")
    sources = collect_draft_sources(request.fund_slug, company, request.event_id)
    if not sources:
        raise HTTPException(status_code=422, detail="No cached sources are available for this event")
    clicked = next((source for source in sources if source["kind"] == "article" and str(source.get("event_id")) == request.event_id), None)
    if clicked is None:
        cached_articles = read_articles(request.fund_slug, company["name"])
        clicked_article = next((item for item in cached_articles if str(item.get("id")) == request.event_id), None)
        if clicked_article:
            clicked = next((source for source in sources if source.get("url") == clicked_article.get("url")), None)
    if clicked is None:
        clicked = next((source for source in sources if source["kind"] == "article"), None)
    task = "Write exactly three concise bullets: what happened, why it matters for our position, and what to ask the founder (two or three direct questions, each ending with a question mark, without numbering words like 'First' or 'Second')." if request.kind == "partner_note" else "Write an email to the founder of at most 90 words, warm in tone, with one concrete offer (an intro, a customer, or a candidate). Include a greeting and sign-off."
    user_content = {"company": {"name": company["name"], "website": company.get("website")}, "task": task, "clicked_event": clicked, "sources": [{k:v for k,v in source.items() if k != 'event_id'} for source in sources]}
    messages = [{"role": "system", "content": DRAFT_SYSTEM_PROMPT}, {"role": "user", "content": json.dumps(user_content, ensure_ascii=False)}]
    run_name = f"draft-{request.version}"
    run_id = f"{run_name}-{__import__('secrets').token_hex(12)}"
    metadata = {
        "run_kind": "live", "prompt_version": request.version, "validator_on": request.version == "v2",
        "task": "draft", "event_id": request.event_id, "pass_number": 1, "source_count": len(sources),
        "sentence_count": 0, "uncited_sentences": 0, "unknown_citations": 0, "dropped_sentences": 0,
        "kind": request.kind,
    }
    checked, trace_info = await traced_chat(messages=messages, model="anthropic/claude-opus-5-5", run_name=run_name, session_id=run_id, metadata=metadata, validator=citation_checked_text, sources=sources, version=request.version, timeout=90.0)
    raw_text = trace_info["raw_text"]
    sentence_count, uncited, unknown, dropped_count = citation_metrics(raw_text, sources, citation_checked_text)
    if request.version == "v2":
        checked, removed, cited = citation_checked_text(raw_text, sources, request.kind)
    else:
        checked, removed, cited = raw_text, 0, []
    output = {"text": checked, "sources": sources, "cited_sources": cited, "sentences_removed": removed, "cached": False, "version": request.version, "metrics": {"sentence_count": sentence_count, "uncited_sentences": uncited, "unknown_citations": unknown, "dropped_sentences": dropped_count}}
    rt_meta = await roundtable_event_draft(request, company, sources, output)
    output["roundtable"] = rt_meta
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(output, ensure_ascii=False, indent=2), encoding="utf-8")
    await shared_cache_put(f"drafts/{cache_path.name}", output)
    return output


class LPUpdateRequest(BaseModel):
    fund_slug: str
    version: str = "v2"
    regenerate: bool = False


@app.post("/api/lp-update")
async def lp_update(request: LPUpdateRequest) -> dict[str, Any]:
    if request.version not in {"v1", "v2"}:
        raise HTTPException(status_code=400, detail="version must be v1 or v2")
    fund = get_fund(request.fund_slug)
    cache_name = f"{slugify(fund['slug'])}-{request.version}.json"
    cache_path = cache_file("lp-updates", cache_name)
    if cache_path.is_file() and not request.regenerate:
        try:
            cached = json.loads(cache_path.read_text(encoding="utf-8"))
            cached["cached"] = True
            return cached
        except (OSError, json.JSONDecodeError):
            pass
    if not request.regenerate and (shared := await shared_cache_get(f"lp-updates/{cache_name}")):
        write_json_atomic(CACHE_DIR / "lp-updates" / cache_name, shared)
        shared["cached"] = True
        return shared

    rt_connected, rt_reason = roundtable_config()
    sources: list[dict[str, Any]] = []
    concerns: list[dict[str, Any]] = []
    cutoff = date.today() - timedelta(days=90)
    company_articles: dict[str, list[dict[str, Any]]] = {}
    processed = {item["name"]: item for item in fund_with_cache(fund["slug"])["companies"]}
    for company in fund["companies"]:
        built = processed.get(company["name"], {})
        # Exits are reported to LPs separately; their stock news is not portfolio news.
        classified = [] if built.get("exited") else [signal for signal in built.get("articles", []) if not signal.get("indicator")]
        recent = []
        for article in classified:
            try:
                if date.fromisoformat(str(article.get("published_date", ""))[:10]) >= cutoff:
                    recent.append(article)
            except ValueError:
                continue
        company_articles[company["name"]] = recent
        indicators = [] if built.get("exited") else built.get("indicator_events", [])
        all_signals = recent + [event for event in indicators if event.get("severity", 0) > 0]
        if any(item.get("severity") == 3 or (item.get("indicator") and item.get("severity", 0) >= 2) for item in all_signals):
            concerns.append({"company": company, "events": all_signals})
    events_for_roundtable: list[dict[str, Any]] = []
    for company in fund["companies"]:
        for article in company_articles[company["name"]]:
            article["company"] = company["name"]
            article["source_kind"] = "article"
            events_for_roundtable.append(article)
    events_for_roundtable.sort(key=lambda item: (item.get("severity", 0), str(item.get("published_date", ""))), reverse=True)
    events_for_roundtable = events_for_roundtable[:24]
    sources.extend(events_for_roundtable)
    for company in fund["companies"]:
        for indicator in ([] if processed.get(company["name"], {}).get("exited") else processed.get(company["name"], {}).get("indicator_events", [])):
            if indicator.get("severity", 0) > 0:
                indicator["company"] = company["name"]
                indicator["source_kind"] = "indicator"
                sources.append(indicator)
    numbered: list[dict[str, Any]] = []
    for number, item in enumerate(sources, start=1):
        is_indicator = item.get("source_kind") == "indicator"
        title = item.get("title") or "Company news"
        date_value = item.get("published_date") or item.get("date")
        numbered.append({"number": number, "title": (f"{item.get('company')}: {item.get('title')} (akta.pro {item.get('indicator_type', 'headcount')} data, as of {date_value})" if is_indicator else title), "publisher": "akta.pro" if is_indicator else (item.get("publisher") or "Unknown publisher"), "date": date_value, "url": None if is_indicator else item.get("url"), "ai_summary": item.get("ai_summary") or item.get("suggested_action") or title, "kind": "indicator" if is_indicator else "article", "company": item.get("company"), "severity": item.get("severity", 1), "category": item.get("category")})
    if not numbered:
        # An empty cache still produces a clear, human-reviewable placeholder update without inventing portfolio facts.
        result = {"text": f"# {fund['name']}: portfolio update\n\nLast 90 days, as of {date.today().isoformat()}\n\n## Portfolio highlights\n\nNo recent public portfolio events are available in the cache.\n\n## Companies to watch\n\nNo current severity 3 events or negative leading indicators are available.\n\nDrafted from public news and company data via akta.pro. Every claim is cited; 0 sentences were removed by the citation check.", "markdown": f"# {fund['name']}: portfolio update\n\nLast 90 days, as of {date.today().isoformat()}\n\n## Portfolio highlights\n\nNo recent public portfolio events are available in the cache.\n\n## Companies to watch\n\nNo current severity 3 events or negative leading indicators are available.\n\nDrafted from public news and company data via akta.pro. Every claim is cited; 0 sentences were removed by the citation check.\n\n## Sources\n", "version": request.version, "sources": [], "cited_sources": [], "sentences_removed": 0, "cached": False}
        # Not cached: an empty update must not outlive the next refresh (Betaworks kept one).
        result["roundtable"] = await roundtable_lp_update(fund, [], result, request)
        return result
    watch = []
    for entry in concerns[:3]:
        company = entry["company"]
        watch.append({"company": company["name"], "events": [{"source_index": next((s["number"] for s in numbered if s["company"] == company["name"] and s["title"] == (event.get("title") or "Company news")), None), "title": event.get("title"), "action": event.get("suggested_action")} for event in entry["events"] if event.get("severity") == 3 or event.get("indicator")]})
    prompt = f"Create this Markdown LP update. Follow exactly this structure: title '{fund['name']}: portfolio update'; subtitle 'Last 90 days, as of {date.today().isoformat()}'; section 'Portfolio highlights' with 5 to 8 newest-first bullets; section 'Companies to watch' with 2 or 3 severity-3 or negative-indicator companies, each concern and action. Cite every factual sentence with [n]. The company watch sources are: {json.dumps(watch, ensure_ascii=False)}. Do not write a closing line; the app adds one. Write only the update an LP will read: no notes about the sources, your choices or these instructions."
    messages = [{"role": "system", "content": DRAFT_SYSTEM_PROMPT}, {"role": "user", "content": json.dumps({"fund": fund["name"], "task": prompt, "sources": numbered}, ensure_ascii=False)}]
    run_name = f"lp-update-{request.version}"
    run_id = f"{run_name}-{__import__('secrets').token_hex(12)}"
    metadata = {"run_kind": "live", "prompt_version": request.version, "validator_on": request.version == "v2", "task": "lp_update", "event_id": "lp-update", "pass_number": 1, "source_count": len(numbered), "kind": "partner_note"}
    _, info = await traced_chat(messages=messages, model="anthropic/claude-opus-5-5", run_name=run_name, session_id=run_id, metadata=metadata, validator=citation_checked_text, sources=numbered, version=request.version, timeout=90.0)
    raw_text = info["raw_text"]
    if request.version == "v2":
        # The app writes the title and subtitle itself; the model's copies carry no citation and
        # would otherwise count as removed sentences.
        body = "\n".join(line for line in raw_text.strip().splitlines()
                         if not re.match(r"^\s*#\s+", line) and not re.match(r"^\s*[*_]*last 90 days", line, re.IGNORECASE))
        text, removed, cited = citation_checked_text(body, numbered, "partner_note")
    else:
        text, removed, cited = raw_text, 0, []
    closing = "Drafted from public news and company data via akta.pro. Every sentence cites its source."
    text = text.rstrip() + "\n\n" + closing
    cited_sources = [source for source in numbered if source["number"] in cited]
    header = f"# {fund['name']}: portfolio update\n\nLast 90 days, as of {date.today().isoformat()}\n\n"
    markdown = (header if request.version == "v2" else "") + text + "\n\n## Sources\n" + "\n".join(f"[{source['number']}] {source['title']} — {source['publisher']}, {str(source.get('date') or '')[:10]}" + (f" ({source['url']})" if source.get("url") else "") for source in (cited_sources or numbered))
    result = {"text": text, "markdown": markdown, "version": request.version, "sources": numbered, "cited_sources": cited, "sentences_removed": removed, "cached": False}
    cache_path = CACHE_DIR / "lp-updates" / cache_name
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    result["roundtable"] = await roundtable_lp_update(fund, numbered, result, request)
    cache_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    await shared_cache_put(f"lp-updates/{cache_name}", result)
    return result


async def roundtable_lp_update(fund: dict[str, Any], sources: list[dict[str, Any]], output: dict[str, Any], request: "LPUpdateRequest") -> dict[str, Any]:
    connected, reason = roundtable_config()
    if not connected:
        return {"connected": False, "reason": reason}
    bank = get_secret("ROUNDTABLE_PROJECT")
    watcher_key, drafter_key = get_secret("SIGNAL_WATCHER_KEY"), get_secret("DRAFTER_KEY")
    quarter = f"{date.today().year}-Q{((date.today().month-1)//3)+1}"
    path = f"lp-updates/{fund['slug']}/{quarter}.md"
    wrote = await roundtable.call("write_file", watcher_key, {"bank": bank, "path": path, "content": output.get("markdown", output.get("text", "")), "message": f"LP update for {fund['name']}"})
    if wrote is None:
        return {"connected": False, "reason": roundtable.last_error or "LP update save failed"}
    versions = [{"bank": bank, "path": path, "version": extract_version(wrote)}]
    task = await roundtable.call("claim_task", watcher_key, {"project": get_secret("ROUNDTABLE_PROJECT"), "assignee": get_secret("DRAFTER_ID"), "goal": f"Prepare LP update for {fund['name']}", "input": {"kind": "lp_update", "path": path}})
    task_id = extract_task_id(task)
    if not task_id:
        return {"connected": False, "reason": "Task creation failed"}
    project = get_secret("ROUNDTABLE_PROJECT")
    available = await roundtable.call("list_tasks", drafter_key, {"project": project, "assignee": "me", "status": "available"})
    item = find_task(available, task_id)
    expected = item.get("version") if item else task.get("version") if isinstance(task, dict) else None
    claim = await roundtable.call("claim_task", drafter_key, {"project": project, "task_id": task_id, "expected_version": expected})
    if isinstance(claim, dict): expected = claim.get("version", expected)
    await roundtable.call("get_task", drafter_key, {"task_id": task_id})
    await roundtable.call("read_file", drafter_key, {"bank": bank, "path": path})
    status, close_error = await roundtable_close_task(watcher_key, drafter_key, task_id, expected, "done", {"summary": "LP update prepared", "sources": versions, "data": {"fund_slug": fund["slug"]}}, "LP update written")
    history = await roundtable_files(watcher_key, bank, path)
    return {"connected": True, "task_id": task_id, "status": status, "sources": versions, "history": history or [], "reason": close_error or ""}


def build_eval_events() -> list[dict[str, Any]]:
    events: list[dict[str, Any]] = []
    for fund in load_funds():
        for company in fund.get("companies", []):
            articles = read_articles(fund["slug"], company["name"])
            classified = [classify_article(article) for article in articles]
            for signal in classified:
                if signal:
                    sources = []
                    for i, article in enumerate(sorted(articles, key=lambda a: a.get("published_date", ""), reverse=True)[:6], start=1):
                        sources.append({"number": i, "title": article.get("title"), "publisher": article.get("publisher"), "date": article.get("published_date"), "url": article.get("url"), "ai_summary": article.get("ai_summary")})
                    events.append({"event_id": "", "fund_slug": fund["slug"], "company_slug": slugify(company["name"]), "company": company["name"], "event": signal, "sources": sources, "synthetic": False})
    events.sort(key=lambda item: (item["event"].get("severity", 0), item["event"].get("published_date", "")), reverse=True)
    events = events[:20]
    while len(events) < 20:
        index = len(events) + 1
        fund = load_funds()[(index - 1) % 3]
        company = fund["companies"][(index - 1) % len(fund["companies"])]
        events.append({"event_id": "", "fund_slug": fund["slug"], "company_slug": slugify(company["name"]), "company": company["name"], "synthetic": True, "event": {"id": f"synthetic-{index}", "title": f"Portfolio update for {company['name']}", "category": "Funding", "severity": 2, "suggested_action": "Ask the founder for a concise progress update", "published_date": date.today().isoformat()}, "sources": [{"number": 1, "title": f"{company['name']} company update", "publisher": "Portfolio Pulse fixture", "date": date.today().isoformat(), "url": company.get("website"), "ai_summary": f"Synthetic evaluation fixture for {company['name']}."}]})
    for i, event in enumerate(events, start=1):
        event["event_id"] = f"e{i:02d}"
    fixture = DATA_DIR / "eval_events.json"
    fixture.parent.mkdir(parents=True, exist_ok=True)
    fixture.write_text(json.dumps(events, ensure_ascii=False, indent=2), encoding="utf-8")
    return events


@app.get("/api/eval/events")
def eval_event_ids() -> list[dict[str, Any]]:
    fixture = cache_file("eval_events.json")
    if not fixture.exists() or not json.loads(fixture.read_text(encoding="utf-8")):
        events = build_eval_events()
    else:
        events = json.loads(fixture.read_text(encoding="utf-8"))
    return [{"event_id": item["event_id"], "company": item["company"], "category": item["event"].get("category"), "severity": item["event"].get("severity"), "synthetic": item.get("synthetic", False)} for item in events]


@app.post("/api/eval/rebuild")
def eval_rebuild() -> dict[str, Any]:
    events = build_eval_events()
    return {"count": len(events), "synthetic": sum(bool(item.get("synthetic")) for item in events)}


@app.post("/api/eval/replay")
async def eval_replay(body: dict[str, Any]) -> dict[str, Any]:
    version = body.get("version", "v2")
    pass_number = int(body.get("pass", 1))
    start = max(0, int(body.get("start", 0)))
    count = min(3, max(1, int(body.get("count", 3))))
    if version not in {"v1", "v2"}:
        raise HTTPException(status_code=400, detail="version must be v1 or v2")
    fixtures = json.loads((DATA_DIR / "eval_events.json").read_text(encoding="utf-8"))
    selected_fixtures = fixtures[start:start + count]
    semaphore = asyncio.Semaphore(3)
    async def run_one(item: dict[str, Any]) -> dict[str, Any]:
        async with semaphore:
            try:
                sources = item["sources"]
                clicked = item["event"]
                messages = [{"role": "system", "content": DRAFT_SYSTEM_PROMPT}, {"role": "user", "content": json.dumps({"company": item["company"], "task": "Write exactly three concise bullets: what happened, why it matters for our position, and what to ask the founder (two or three direct questions, each ending with a question mark, without numbering words like 'First' or 'Second').", "clicked_event": clicked, "sources": sources}, ensure_ascii=False)}]
                run_name = f"draft-{version}"
                run_id = f"{run_name}-{item['event_id']}-p{pass_number}"
                metadata = {"run_kind": "eval", "prompt_version": version, "validator_on": version == "v2", "task": "draft", "event_id": item["event_id"], "pass_number": pass_number, "source_count": len(sources), "kind": "partner_note"}
                raw, info = await traced_chat(messages=messages, model="anthropic/claude-opus-5-5", run_name=run_name, session_id=run_id, metadata=metadata, validator=citation_checked_text, sources=sources, version=version, timeout=25.0, extra_headers={"x-nicrron-cache": "false"})
                metrics = citation_metrics(info["raw_text"], sources, citation_checked_text)
                return {"event_id": item["event_id"], "ok": True, "uncited_sentences": metrics[1], "unknown_citations": metrics[2], "dropped_sentences": metrics[3]}
            except httpx.HTTPStatusError as exc:
                retry = exc.response.headers.get("retry-after")
                return {"event_id": item["event_id"], "ok": False, "uncited_sentences": 0, "unknown_citations": 0, "dropped_sentences": 0, "error": "Nicrron rate limit" if exc.response.status_code == 429 else "Nicrron request failed", "retry_after": retry}
            except Exception:
                return {"event_id": item["event_id"], "ok": False, "uncited_sentences": 0, "unknown_citations": 0, "dropped_sentences": 0, "error": "Could not run replay"}
    results = await asyncio.gather(*(run_one(item) for item in selected_fixtures))
    retry_after = next((item.get("retry_after") for item in results if item.get("retry_after")), None)
    next_start = None if start + len(selected_fixtures) >= len(fixtures) else start + len(selected_fixtures)
    return {"results": results, "next_start": next_start, "retry_after": retry_after}
