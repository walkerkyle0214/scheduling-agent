"""
Text-chat test harness for the Summit Air assistant via Vapi's /chat API.

Lets you iterate on the prompt + tools without voice or a phone number. It runs
the SAME assistant (same system prompt, same tools hitting your webhook), just
over text, so tool calls exercise your live backend.

Usage:
    export VAPI_API_KEY=...
    export VAPI_ASSISTANT_ID=...       # from create_assistant.py
    python chat_test.py                # interactive REPL
    python chat_test.py "my furnace is dead and my mom is 80"   # one-shot
"""

from __future__ import annotations

import os
import sys

import requests

VAPI_BASE = "https://api.vapi.ai"


def _require(name: str) -> str:
    val = os.environ.get(name)
    if not val:
        sys.exit(f"ERROR: environment variable {name} is required.")
    return val


def send(api_key: str, assistant_id: str, text: str, previous_chat_id: str | None) -> tuple[str, str]:
    payload = {"assistantId": assistant_id, "input": text}
    if previous_chat_id:
        payload["previousChatId"] = previous_chat_id

    resp = requests.post(
        f"{VAPI_BASE}/chat",
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    if resp.status_code >= 300:
        print(f"ERROR {resp.status_code}: {resp.text}", file=sys.stderr)
        sys.exit(1)

    data = resp.json()
    chat_id = data.get("id", previous_chat_id)

    # Collect assistant text from the output messages.
    parts: list[str] = []
    for msg in data.get("output", []) or []:
        if msg.get("role") == "assistant" and msg.get("content"):
            parts.append(msg["content"])
    reply = "\n".join(parts) if parts else "(no text reply — assistant may have only made tool calls)"
    return reply, chat_id


def main() -> None:
    api_key = _require("VAPI_API_KEY")
    assistant_id = _require("VAPI_ASSISTANT_ID")

    # One-shot mode.
    if len(sys.argv) > 1:
        reply, _ = send(api_key, assistant_id, " ".join(sys.argv[1:]), None)
        print(reply)
        return

    print("Summit Air chat test. Type your message, or 'quit' to exit.\n")
    chat_id: str | None = None
    while True:
        try:
            text = input("you > ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if text.lower() in {"quit", "exit"}:
            break
        if not text:
            continue
        reply, chat_id = send(api_key, assistant_id, text, chat_id)
        print(f"agent > {reply}\n")


if __name__ == "__main__":
    main()
