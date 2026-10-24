#!/usr/bin/env python3
"""Call one PRISM MCP tool: python3 scripts/prism-mcp.py <tool> ['{"json": "args"}']

Reads PRISM_MCP_KEY from .env.local (never printed). Example:
    python3 scripts/prism-mcp.py prism_overview '{"days": 1, "response_format": "concise"}'
"""
import json
import pathlib
import sys
import urllib.request

ENV = pathlib.Path(__file__).resolve().parent.parent / ".env.local"
key = next((line.split("=", 1)[1].strip() for line in ENV.read_text().splitlines()
            if line.startswith("PRISM_MCP_KEY=")), "")
if not key:
    sys.exit("PRISM_MCP_KEY is not set in .env.local")
if len(sys.argv) < 2:
    sys.exit(__doc__)

body = {"jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {"name": sys.argv[1], "arguments": json.loads(sys.argv[2]) if len(sys.argv) > 2 else {}}}
req = urllib.request.Request("https://api.prism.blockconvey.com/mcp", data=json.dumps(body).encode(),
                             headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json",
                                      "Accept": "application/json, text/event-stream"})
with urllib.request.urlopen(req, timeout=120) as r:
    raw = r.read().decode()
if raw.startswith("event:") or "\ndata:" in raw:
    raw = "\n".join(line[5:].strip() for line in raw.splitlines() if line.startswith("data:"))
data = json.loads(raw)
result = data.get("result", data)
text = "\n".join(c.get("text", "") for c in result.get("content", [])) if isinstance(result, dict) else ""
print((text or json.dumps(result, indent=2)).replace(key, "[redacted]"))
