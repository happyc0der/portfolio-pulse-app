from __future__ import annotations

import asyncio
import os
import secrets
import time
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


def prism_enabled() -> bool:
    return bool(get_secret("PRISMTRACE_API_KEY") and get_secret("PRISMTRACE_PROJECT_ID"))


def get_prism_client() -> Any | None:
    global _client, _client_checked
    if _client_checked:
        return _client
    _client_checked = True
    api_key = get_secret("PRISMTRACE_API_KEY")
    project_id = get_secret("PRISMTRACE_PROJECT_ID")
    host = get_secret("PRISMTRACE_HOST") or "https://prism.blockconvey.com"
    if not api_key or not project_id:
        return None
    try:
        from prismtrace import PRISMtrace
        _client = PRISMtrace(api_key=api_key, host=host, project_id=project_id)
    except Exception:
        _client = None
    return _client


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


async def traced_chat(*, messages: list[dict[str, str]], model: str, run_name: str, session_id: str, metadata: dict[str, Any], validator: Any, sources: list[dict[str, Any]], version: str = "v2", timeout: float = 90.0, extra_headers: dict[str, str] | None = None) -> tuple[str, Any]:
    """Call Nicrron once, then best-effort trace without affecting the result."""
    api_key = get_secret("NICRRON_API_KEY")
    if not api_key:
        raise RuntimeError("NICRRON_API_KEY is not configured")
    base_url = os.getenv("NICRRON_BASE_URL", "https://api.nicrron.ai/v1").rstrip("/")
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
    trace_id = session_id or secrets.token_hex(12)
    trace_metadata = {**metadata, "nicrron_generation_id": generation_id}
    if version == "v2":
        trace_metadata["raw_output"] = raw_text[:4000]
    prism = get_prism_client()
    if prism is not None:
        async def trace_and_flush() -> None:
            try:
                prism.trace_llm(model=body.get("model") or model, input_messages=messages, output=output_text, latency_ms=elapsed_ms, token_count_input=input_tokens, token_count_output=output_tokens, agent_id=run_name, agent_name=run_name, session_id=trace_id, trace_id=trace_id, metadata=trace_metadata)
                await asyncio.to_thread(prism.flush)
            except Exception:
                return
        try:
            await asyncio.wait_for(trace_and_flush(), timeout=2.0)
        except Exception:
            pass
    return output_text, {"raw_text": raw_text, "dropped": dropped, "generation_id": generation_id, "usage": usage, "latency_ms": elapsed_ms}
