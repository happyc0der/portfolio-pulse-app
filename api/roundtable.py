from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from typing import Any

import httpx

logger = logging.getLogger(__name__)
last_error: str | None = None
_RETRY = {429, 502, 503, 504}
_WRITE_TOOLS = {"write_file", "claim_task", "update_task"}


def parse_result(payload: Any) -> Any:
    if not isinstance(payload, dict):
        return payload
    result = payload.get("result", payload)
    if isinstance(result, str):
        try:
            result = json.loads(result)
        except (TypeError, ValueError):
            return result
    if isinstance(result, dict) and isinstance(result.get("task"), dict):
        task = result["task"].copy()
        task.setdefault("task_id", task.get("id"))
        return task
    if isinstance(result, dict):
        result = result.copy()
        if "task_id" not in result and result.get("id"):
            result["task_id"] = result["id"]
    return result


async def call(tool: str, key: str, args: dict[str, Any]) -> Any | None:
    global last_error
    if not key:
        last_error = "missing credentials"
        return None
    base_url = (os.environ.get("ROUNDTABLE_URL") or "https://roundtable.bot").rstrip("/")
    body = dict(args)
    request_id = body.get("request_id") or (str(uuid.uuid4()) if tool in _WRITE_TOOLS else None)
    if request_id:
        body["request_id"] = request_id
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            for attempt in range(2):
                response = await client.post(f"{base_url}/api/tools/{tool}", headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"}, json=body)
                if response.status_code in _RETRY and attempt == 0:
                    await asyncio.sleep(0.5)
                    continue
                response.raise_for_status()
                payload = response.json()
                logger.info("Roundtable %s response: %s", tool, json.dumps(payload, ensure_ascii=False, default=str)[:4000])
                last_error = None
                return parse_result(payload)
        return None
    except Exception as exc:
        last_error = f"{type(exc).__name__}: {exc}"
        logger.warning("Roundtable %s failed: %s", tool, last_error)
        return None
