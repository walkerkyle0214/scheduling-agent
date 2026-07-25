"""
Attach a phone number to the Summit Air assistant.

Two modes:
  1. List your existing Vapi phone numbers:
        python attach_number.py list
  2. Assign an existing number to the assistant as its inbound handler:
        export VAPI_API_KEY=...
        export VAPI_ASSISTANT_ID=...
        python attach_number.py assign <phoneNumberId>

To BUY a number, do it in the Vapi dashboard (Phone Numbers -> Buy) — free Vapi
numbers are US-only and provisioned there — then run `assign`.
"""

from __future__ import annotations

import os
import sys

import requests

VAPI_BASE = "https://api.vapi.ai"


def _headers() -> dict[str, str]:
    key = os.environ.get("VAPI_API_KEY")
    if not key:
        sys.exit("ERROR: VAPI_API_KEY is required.")
    return {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}


def list_numbers() -> None:
    resp = requests.get(f"{VAPI_BASE}/phone-number", headers=_headers(), timeout=30)
    resp.raise_for_status()
    numbers = resp.json()
    if not numbers:
        print("No phone numbers yet. Buy one in the Vapi dashboard (Phone Numbers -> Buy).")
        return
    for n in numbers:
        print(f"{n.get('id')}  {n.get('number')}  assistant={n.get('assistantId')}")


def assign(phone_number_id: str) -> None:
    assistant_id = os.environ.get("VAPI_ASSISTANT_ID")
    if not assistant_id:
        sys.exit("ERROR: VAPI_ASSISTANT_ID is required.")
    resp = requests.patch(
        f"{VAPI_BASE}/phone-number/{phone_number_id}",
        headers=_headers(),
        json={"assistantId": assistant_id},
        timeout=30,
    )
    if resp.status_code >= 300:
        sys.exit(f"ERROR {resp.status_code}: {resp.text}")
    data = resp.json()
    print(f"Assigned {data.get('number')} -> assistant {assistant_id}")
    print("Call that number to test the agent live.")


def main() -> None:
    if len(sys.argv) < 2 or sys.argv[1] not in {"list", "assign"}:
        print(__doc__)
        sys.exit(1)
    if sys.argv[1] == "list":
        list_numbers()
    else:
        if len(sys.argv) < 3:
            sys.exit("Usage: python attach_number.py assign <phoneNumberId>")
        assign(sys.argv[2])


if __name__ == "__main__":
    main()
