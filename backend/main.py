"""
Summit Air — AI phone agent backend.

A single FastAPI app that exposes one webhook (`POST /vapi/tools`) for Vapi's
server-tool calls. The four tools (lookup_customer, check_availability,
create_booking, flag_priority) are dispatched to a pluggable CRM backend
(see the `crm` package). Select the backend with CRM_BACKEND:

    CRM_BACKEND=mock          -> SQLite mock (default)
    CRM_BACKEND=servicetitan  -> live ServiceTitan adapter (needs ST_* creds)

Admin helpers (`POST /admin/reset`, `GET /admin/state`) work when the active
backend supports them (the mock does).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse

import crm

app = FastAPI(title="Summit Air Agent Backend")
backend = crm.get_backend()
# dashboard.html lives in the sibling dashboard/ folder (repo_root/dashboard/).
DASHBOARD_HTML = Path(__file__).resolve().parent.parent / "dashboard" / "dashboard.html"

TOOL_HANDLERS = {
    "lookup_customer": backend.lookup_customer,
    "check_availability": backend.check_availability,
    "create_booking": backend.create_booking,
    "flag_priority": backend.flag_priority,
}


@app.post("/vapi/tools")
async def vapi_tools(request: Request) -> JSONResponse:
    """Dispatch Vapi's tool-calls payload to the active CRM backend.

    Vapi sends: {"message": {"toolCallList": [{"id", "function": {"name", "arguments"}}]}}
    We return:  {"results": [{"toolCallId", "result": "<json string>"}]}
    """
    body = await request.json()
    message = body.get("message", {}) if isinstance(body, dict) else {}
    tool_calls = message.get("toolCallList") or message.get("toolCalls") or []

    results = []
    for call in tool_calls:
        call_id = call.get("id")
        fn = call.get("function", {}) or {}
        name = fn.get("name")
        raw_args = fn.get("arguments", {})

        if isinstance(raw_args, str):
            try:
                args = json.loads(raw_args) if raw_args.strip() else {}
            except json.JSONDecodeError:
                args = {}
        else:
            args = raw_args or {}

        handler = TOOL_HANDLERS.get(name)
        if handler is None:
            result_payload: dict[str, Any] = {"error": f"Unknown tool: {name}"}
        else:
            try:
                result_payload = handler(args)
            except Exception as exc:  # never 500 back to Vapi mid-call
                result_payload = {"error": f"Tool {name} failed: {exc}"}

        results.append({"toolCallId": call_id, "result": json.dumps(result_payload)})

    return JSONResponse({"results": results})


# ---------------------------------------------------------------------------
# Admin / testing
# ---------------------------------------------------------------------------

@app.post("/admin/reset")
async def admin_reset() -> dict[str, str]:
    backend.admin_reset()
    return {"status": "reset", "backend": backend.name}


@app.get("/admin/state")
async def admin_state() -> dict[str, Any]:
    return backend.admin_state()


@app.post("/admin/add_customer")
async def admin_add_customer(request: Request) -> dict[str, Any]:
    """Register a known customer (e.g. the evaluator's number) to demo caller-ID
    recognition. Body: {"phone": "...", "name": "...", "address": "...", ...}."""
    body = await request.json()
    return backend.admin_add_customer(body if isinstance(body, dict) else {})


@app.get("/dashboard", response_class=HTMLResponse)
async def dashboard() -> str:
    """Live dispatch board — schedule grid, priority queue, session bookings."""
    return DASHBOARD_HTML.read_text(encoding="utf-8")


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "backend": backend.name}
