from __future__ import annotations

import asyncio
import json
import os
import secrets
import time
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import httpx
from dotenv import dotenv_values


def get_secret(name: str) -> str:
    value = os.environ.get(name, "")
    if value and value.strip():
        return value.strip()
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    try:
        return str(dotenv_values(env_path).get(name, "") or "").strip()
    except Exception:
        return ""

_client: Any | None = None
_client_checked = False
last_tracing_error: str | None = None


def prism_enabled() -> bool:
    return bool(get_secret("PRISMTRACE_API_KEY") and get_secret("PRISMTRACE_PROJECT_ID"))


def get_prism_client(*, force: bool = False) -> Any | None:
    global _client, _client_checked, last_tracing_error
    if _client_checked and not force:
        return _client
    api_key = get_secret("PRISMTRACE_API_KEY")
    project_id = get_secret("PRISMTRACE_PROJECT_ID")
    host = get_secret("PRISMTRACE_HOST") or "https://prism.blockconvey.com"
    if not api_key or not project_id:
        last_tracing_error = "Missing PRISMTRACE_API_KEY or PRISMTRACE_PROJECT_ID"
        _client = None
        _client_checked = True
        return None
    try:
        from prismtrace import PRISMtrace
        _client = PRISMtrace(api_key=api_key, host=host, project_id=project_id)
        _client_checked = True
        last_tracing_error = None
    except Exception as exc:
        _client = None
        _client_checked = True
        last_tracing_error = f"{type(exc).__name__}: {exc}"
    return _client


def prism_settings() -> tuple[str, str]:
    return get_secret("PRISMTRACE_HOST") or "https://prism.blockconvey.com", get_secret("PRISMTRACE_PROJECT_ID")


def direct_trace_check(host: str, project_id: str) -> dict[str, Any]:
    """POST one trace synchronously to each PRISM host and report the HTTP result.

    The SDK sends from a background thread and only prints failures, so its silence proves
    nothing. Never returns the key."""
    import httpx

    api_key = get_secret("PRISMTRACE_API_KEY")
    payload = {"project_id": project_id, "model": "selftest", "input_messages": [{"role": "user", "content": "ping"}],
               "output_message": "pong", "latency_ms": 0, "token_count_input": 1, "token_count_output": 1,
               "trace_id": secrets.token_hex(8), "agent_id": "selftest", "agent_name": "selftest",
               "session_id": secrets.token_hex(8), "metadata": {"run_kind": "live", "task": "selftest-direct"}}
    results: dict[str, Any] = {}
    for candidate in dict.fromkeys([host.rstrip("/"), "https://api.prism.blockconvey.com", "https://prism.blockconvey.com"]):
        try:
            response = httpx.post(f"{candidate}/api/traces", json=payload, timeout=15,
                                  headers={"x-prismtrace-key": api_key, "Content-Type": "application/json"})
            body = response.text[:300].replace(api_key, "[redacted]") if api_key else response.text[:300]
            results[candidate] = {"status": response.status_code, "body": body}
        except Exception as exc:
            results[candidate] = {"error": f"{type(exc).__name__}: {exc}"[:300]}
    return results


def prism_selftest() -> dict[str, Any]:
    global last_tracing_error
    host, project_id = prism_settings()
    prefix = project_id[:8] if project_id else ""
    client = get_prism_client(force=True)
    if client is None:
        return {"sent": False, "host": host, "project_id_prefix": prefix, "error": last_tracing_error}
    try:
        client.trace_llm(model="selftest", input_messages=[{"role": "user", "content": "ping"}], output="pong", latency_ms=0, token_count_input=1, token_count_output=1, agent_id="selftest", agent_name="selftest", session_id=secrets.token_hex(8), trace_id=secrets.token_hex(8), metadata={"run_kind": "live", "task": "selftest"})
        flush_result = client.flush()
        last_tracing_error = None
        return {"sent": True, "host": host, "project_id_prefix": prefix, "error": None, "flush": flush_result, "direct": direct_trace_check(host, project_id)}
    except Exception as exc:
        last_tracing_error = f"{type(exc).__name__}: {exc}"
        return {"sent": False, "host": host, "project_id_prefix": prefix, "error": last_tracing_error}


def citation_metrics(text: str, sources: list[dict[str, Any]], splitter: Any) -> tuple[int, int, int, int]:
    import re
    try:
        pieces = [part.strip() for part in re.split(r"(?<=[.!?])\s+|\n+", text.strip()) if part.strip()]
    except Exception:
        pieces = [text] if text.strip() else []
    allowed = {str(source.get("number")) for source in sources}
    uncited = unknown = 0
    for piece in pieces:
        citations = re.findall(r"\[(\d+)\]", piece)
        if not citations:
            uncited += 1
        elif any(number not in allowed for number in citations):
            unknown += 1
    try:
        _, dropped, _ = splitter(text, sources, "partner_note")
    except Exception:
        dropped = sum(1 for piece in pieces if not re.search(r"\[\d+\]", piece))
    return len(pieces), uncited, unknown, dropped


# PRISM's evaluators read {input} as the user's last message only, and {context} as what the
# trace's retrieval and tool steps returned, up to about 6,000 characters. Our prompt carries every
# source inside one long JSON message, so the judge saw only the first one or two. Each trace now
# gets a retrieval span listing the numbered sources, so a rubric can check citations against
# {context}, and an LLM span for the call itself, all sent as one spans ingest (see send_trace).
CONTEXT_LIMIT = 5800
_pending_traces: set[asyncio.Task[Any]] = set()


def sources_context(sources: list[dict[str, Any]]) -> str:
    """The numbered sources the model was given, compact enough to fit PRISM's {context}."""
    header = "Numbered sources the drafting model was given (akta.pro). The output may cite only these numbers.\n"
    lines = [f"[{source.get('number')}] {str(source.get('title') or '')[:140]} ({source.get('publisher') or 'unknown'}, {str(source.get('date') or '')[:10]})" for source in sources]
    room = CONTEXT_LIMIT - len(header) - sum(len(line) + 1 for line in lines)
    per_source = room // max(1, len(sources)) - 3
    out = []
    for line, source in zip(lines, sources):
        summary = " ".join(str(source.get("ai_summary") or "").split())
        if per_source > 40 and summary:
            line += ": " + (summary if len(summary) <= per_source else summary[:per_source - 1] + "…")
        out.append(line)
    return (header + "\n".join(out))[:CONTEXT_LIMIT]


def retrieval_query(messages: list[dict[str, str]]) -> str:
    try:
        request = json.loads(messages[-1]["content"])
        name = (request.get("company") or {}).get("name") or request.get("fund") or request.get("fund_name")
        return f"akta.pro news and company data for {name}" if name else "akta.pro portfolio sources"
    except (ValueError, KeyError, IndexError, AttributeError, TypeError):
        return "akta.pro portfolio sources"


async def send_trace(*, trace_id: str, session_id: str, run_name: str, model: str, messages: list[dict[str, str]], raw_output: str, output: str, sources: list[dict[str, Any]], metadata: dict[str, Any], started_at: datetime, latency_ms: int, tokens_in: int, tokens_out: int) -> None:
    """Send one run as spans, the way the SDK's own handlers do. PRISM builds the trace from them:
    its input and output come from the root span, {context} from the akta_sources step, and tokens
    and cost from the LLM step. (A separate /api/traces record for the same id races the spans: the
    first one to arrive wins, which dropped spans on some traces and swapped the output on others.)"""
    global last_tracing_error
    try:
        ended_at = started_at + timedelta(milliseconds=latency_ms)
        root_id = str(uuid.uuid4())
        start, end = started_at.isoformat(), ended_at.isoformat()
        spans = [
            {"span_id": root_id, "parent_span_id": None, "name": run_name, "span_type": "agent",
             "input_text": messages[-1]["content"][:10000], "output_text": output, "start_time": start, "end_time": end,
             "duration_ms": latency_ms, "status": "ok", "model": model, "metadata": metadata},
            {"span_id": str(uuid.uuid4()), "parent_span_id": root_id, "name": "akta_sources", "span_type": "tool",
             "input_text": retrieval_query(messages), "output_text": sources_context(sources), "start_time": start,
             "end_time": start, "duration_ms": 0, "status": "ok", "metadata": {"source_count": len(sources)}},
            {"span_id": str(uuid.uuid4()), "parent_span_id": root_id, "name": "nicrron_chat", "span_type": "llm",
             "input_text": json.dumps(messages, ensure_ascii=False)[:10000], "output_text": raw_output[:10000],
             "start_time": start, "end_time": end, "duration_ms": latency_ms, "status": "ok", "model": model,
             "token_count_input": tokens_in, "token_count_output": tokens_out},
        ]
        host, project_id = prism_settings()
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.post(f"{host.rstrip('/')}/api/spans/ingest", headers={"X-PRISMtrace-Key": get_secret("PRISMTRACE_API_KEY")},
                                         json={"trace_id": trace_id, "project_id": project_id, "session_id": session_id,
                                               "metadata": {"agent_name": run_name, "agent_id": run_name, **metadata}, "spans": spans})
        last_tracing_error = None if response.status_code == 200 else f"PRISM spans ingest returned {response.status_code}: {response.text[:200]}"
    except Exception as exc:
        last_tracing_error = f"{type(exc).__name__}: {exc}"


async def traced_chat(*, messages: list[dict[str, str]], model: str, run_name: str, session_id: str, metadata: dict[str, Any], validator: Any, sources: list[dict[str, Any]], version: str = "v2", timeout: float = 90.0, extra_headers: dict[str, str] | None = None) -> tuple[str, Any]:
    """Call Nicrron once, then best-effort trace without affecting the result."""
    api_key = get_secret("NICRRON_API_KEY")
    if not api_key:
        raise RuntimeError("NICRRON_API_KEY is not configured")
    base_url = os.getenv("NICRRON_BASE_URL", "https://api.nicrron.ai/v1").rstrip("/")
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json", **(extra_headers or {})}
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(f"{base_url}/chat/completions", headers=headers, json={"model": model, "temperature": 0.2, "messages": messages})
    response.raise_for_status()
    body = response.json()
    raw_text = str(body["choices"][0]["message"]["content"])
    generation_id = body.get("id")
    output_text, dropped, _ = validator(raw_text, sources, metadata.get("kind", "partner_note")) if version == "v2" else (raw_text, 0, [])
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    usage = body.get("usage") or {}
    input_tokens = usage.get("prompt_tokens", usage.get("input_tokens"))
    output_tokens = usage.get("completion_tokens", usage.get("output_tokens"))
    trace_metadata = {**metadata, "nicrron_generation_id": generation_id}
    if version == "v2":
        trace_metadata["raw_output"] = raw_text[:4000]
    if prism_enabled():
        # Traced in the background so a slow PRISM never delays the draft.
        task = asyncio.create_task(send_trace(
            trace_id=str(uuid.uuid4()), session_id=session_id or secrets.token_hex(12), run_name=run_name,
            model=body.get("model") or model, messages=messages, raw_output=raw_text, output=output_text, sources=sources,
            metadata=trace_metadata, started_at=started_at, latency_ms=elapsed_ms,
            tokens_in=input_tokens or 0, tokens_out=output_tokens or 0))
        _pending_traces.add(task)
        task.add_done_callback(_pending_traces.discard)
    return output_text, {"raw_text": raw_text, "dropped": dropped, "generation_id": generation_id, "usage": usage, "latency_ms": elapsed_ms}
