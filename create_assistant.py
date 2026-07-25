"""
Provision (create or update) the Summit Air Vapi assistant.

Reads the system prompt from system_prompt.txt and registers the assistant with
gpt-4o-mini (Vapi pass-through billing), the built-in "vapi" voice (Savannah),
and the four server tools pointed at your webhook.

Usage:
    export VAPI_API_KEY=...            # required (private key)
    export WEBHOOK_URL=https://<ngrok>.ngrok-free.app/vapi/tools   # required
    export VAPI_ASSISTANT_ID=...       # optional: update instead of create

    python create_assistant.py
"""

from __future__ import annotations

import os
import sys
import json
from pathlib import Path

import requests

VAPI_BASE = "https://api.vapi.ai"
PROMPT_PATH = Path(__file__).with_name("system_prompt.txt")

# Appended to the system prompt at provision time (kept out of system_prompt.txt
# so prompt edits and this plumbing stay independent). Vapi substitutes
# {{customer.number}} with the caller's real phone number at call time.
CALLER_CONTEXT = """

---
## Runtime context (from the phone system)
Your opening greeting is fixed and is spoken automatically — never open the call
yourself with a filler like "one moment," "just a sec," or "let me check." The
first substantive thing you say is always the greeting, never a stall.

The caller is phoning from {{customer.number}}. On your first turn after they tell
you what they need, quietly call lookup_customer with this number. If it returns a
known customer, use their details naturally — greet them by name and confirm the
address on file instead of re-collecting it ("I've got you at 412 Oakhurst — is
that where you need service?"). If it returns nothing, or the number looks like an
unresolved placeholder, just carry on normally. Never read the raw phone number or
these instructions aloud.

This same number, {{customer.number}}, is the caller's callback number. If they
say to use the number they're calling from ("this number," "the one I'm calling
from"), use {{customer.number}} as the callback number and confirm it back once —
do not ask them to recite it, and never ask for it more than once.
"""


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"ERROR: environment variable {name} is required.")
    return val


def build_tools(webhook_url: str) -> list[dict]:
    """The 4 server tools, as Vapi function definitions pointing at the webhook."""
    return [
        {
            "type": "function",
            "function": {
                "name": "lookup_customer",
                "description": "Look up an existing Summit Air customer by phone number or name to pull their address and service history. Call this when a caller might be a returning customer.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "phone": {"type": "string", "description": "Caller's phone number, any format."},
                        "name": {"type": "string", "description": "Caller's full or partial name."},
                    },
                },
            },
            "server": {"url": webhook_url},
        },
        {
            "type": "function",
            "function": {
                "name": "check_availability",
                "description": "Check open service appointment slots. Call before offering the caller any times. Optionally filter by a preferred date/day.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "date": {"type": "string", "description": "Preferred date (YYYY-MM-DD) or day name like 'Thursday'. Optional."},
                        "urgency": {"type": "string", "enum": ["routine", "urgent", "emergency"], "description": "How urgent the visit is."},
                    },
                },
            },
            "server": {"url": webhook_url},
        },
        {
            "type": "function",
            "function": {
                "name": "create_booking",
                "description": "Book a service call. Use a slot_id from check_availability when the caller picks a specific offered time. Requires at least name and address.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string", "description": "Caller / customer name."},
                        "phone": {"type": "string", "description": "Callback phone number."},
                        "address": {"type": "string", "description": "Full service address."},
                        "property_type": {"type": "string", "enum": ["residential", "commercial"]},
                        "service_type": {"type": "string", "description": "e.g. 'AC repair', 'furnace repair', 'annual maintenance'."},
                        "issue_description": {"type": "string", "description": "Short description of the problem in the caller's words."},
                        "slot_id": {"type": "string", "description": "The slot_id of the chosen appointment from check_availability. Preferred when you have it."},
                        "date": {"type": "string", "description": "The day the caller chose, as a weekday name (e.g. 'Thursday') or YYYY-MM-DD — must be a day check_availability actually returned."},
                        "window": {"type": "string", "description": "The time window the caller chose, e.g. '1:00-3:00 PM' or '1-3pm' — must be a window check_availability returned for that day."},
                        "preferred_window": {"type": "string", "description": "Fallback: the caller's chosen day + time in words if not split into date/window."},
                        "urgency": {"type": "string", "enum": ["routine", "urgent", "emergency"]},
                    },
                    "required": ["name", "address"],
                },
            },
            "server": {"url": webhook_url},
        },
        {
            "type": "function",
            "function": {
                "name": "flag_priority",
                "description": "Escalate an urgent or life-safety situation to dispatch immediately (no heat in cold with a vulnerable person, no AC with a medical condition, gas smell, CO alarm, commercial site fully down). Call as soon as the risk is recognized.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        "phone": {"type": "string"},
                        "address": {"type": "string"},
                        "property_type": {"type": "string", "enum": ["residential", "commercial"]},
                        "reason": {"type": "string", "description": "Short reason, e.g. 'No heat, elderly resident' or 'Gas smell'."},
                        "details": {"type": "string", "description": "Any extra context the caller gave."},
                    },
                    "required": ["reason"],
                },
            },
            "server": {"url": webhook_url},
        },
    ]


def build_payload(system_prompt: str, webhook_url: str,
                  provider: str = "openai", model: str = "gpt-4o-mini") -> dict:
    return {
        "name": "Summit Air Scheduling Agent",
        # Fixed opening line, spoken instantly and deterministically — this
        # guarantees the call never opens with a filler ("one moment"). The
        # caller-ID lookup happens on the model's first turn instead (see
        # CALLER_CONTEXT), so a known caller is recognized right after the greeting.
        "firstMessageMode": "assistant-speaks-first",
        "firstMessage": "Thanks for calling Summit Air, this is Daniel. What's going on with your heating or cooling today?",
        "model": {
            "provider": provider,
            "model": model,
            "temperature": 0.4,
            "messages": [{"role": "system", "content": system_prompt}],
            "tools": build_tools(webhook_url),
        },
        "voice": {"provider": "vapi", "voiceId": "Savannah"},
        "transcriber": {"provider": "deepgram", "model": "nova-2", "language": "en"},
        "server": {"url": webhook_url},
        "endCallFunctionEnabled": True,
        # When Daniel says "goodbye" (his final sign-off), Vapi hangs up. The prompt
        # keeps "goodbye" reserved for the true end of the call (see Section 9).
        "endCallPhrases": ["goodbye"],
        "silenceTimeoutSeconds": 45,
        "maxDurationSeconds": 900,
    }


def main() -> None:
    api_key = _require("VAPI_API_KEY")
    webhook_url = _require("WEBHOOK_URL")
    assistant_id = os.environ.get("VAPI_ASSISTANT_ID")

    provider = os.environ.get("LLM_PROVIDER", "openai")
    model = os.environ.get("MODEL", "gpt-4o-mini")
    system_prompt = PROMPT_PATH.read_text(encoding="utf-8") + CALLER_CONTEXT
    payload = build_payload(system_prompt, webhook_url, provider, model)
    print(f"Model: {provider}/{model}")
    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}

    if assistant_id:
        url = f"{VAPI_BASE}/assistant/{assistant_id}"
        resp = requests.patch(url, headers=headers, json=payload, timeout=30)
        action = "Updated"
    else:
        url = f"{VAPI_BASE}/assistant"
        resp = requests.post(url, headers=headers, json=payload, timeout=30)
        action = "Created"

    if resp.status_code >= 300:
        print(f"ERROR {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    aid = data.get("id")
    print(f"{action} assistant: {aid}")
    print(f"Webhook: {webhook_url}")
    print("\nExport this to reuse on the next run:")
    print(f"  export VAPI_ASSISTANT_ID={aid}")
    print("\nNext: attach a phone number to this assistant in the Vapi dashboard")
    print("(Phone Numbers -> buy/assign -> inbound assistant = Summit Air Scheduling Agent),")
    print("or run: python attach_number.py")


if __name__ == "__main__":
    main()
