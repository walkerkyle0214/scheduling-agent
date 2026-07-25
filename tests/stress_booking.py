"""
Info-gathering stress harness — focused on data capture during booking.

Every scenario supplies KNOWN name/address/phone values, then asserts those exact
values landed in the stored booking (or priority) record — this is what catches
"the agent collected my info but it shows up as (no name) / address n/a." It also
prints the stored record and two diagnostics per scenario:
  * apologies  — how many times the agent said "sorry"/"apologize" (you flagged over-apologizing)
  * questions  — how many agent turns asked a question (proxy for "keeps asking")

Runs over Vapi /chat (same assistant/prompt/tools as voice — see stress_test.py's
notes on how text differs from voice: NO transcription errors here, so a failure is
a genuine logic/prompt gap, not a mis-hear).

Setup (same as stress_test.py):
    export VAPI_API_KEY=...
    export VAPI_ASSISTANT_ID=...
    export LOCAL_BASE=http://localhost:8001     # optional
    python stress_booking.py               # run all
    python stress_booking.py correction    # scenarios matching a name
"""

from __future__ import annotations

import sys
import time

import requests

from stress_test import chat, _require, LOCAL_BASE


# --- field-capture checks ---------------------------------------------------

def _digits(s):
    return "".join(c for c in str(s or "") if c.isdigit())


def _latest_new_booking(state):
    live = [b for b in state["bookings"] if not str(b["booking_id"]).startswith("BK-SEED")]
    return live[-1] if live else None


def _latest_priority(state):
    pq = state.get("priority_queue", [])
    return pq[-1] if pq else None


def booking_has(name=None, address=None, phone=None):
    def check(state):
        b = _latest_new_booking(state)
        if not b:
            return "no new booking created"
        return _cmp(b, name, address, phone)
    return check


def priority_has(name=None, address=None, phone=None):
    def check(state):
        p = _latest_priority(state)
        if not p:
            return "no priority entry created"
        return _cmp(p, name, address, phone)
    return check


def _cmp(rec, name, address, phone):
    problems = []
    if name and name.lower() not in (rec.get("name") or "").lower():
        problems.append(f"name missing '{name}' (stored: '{rec.get('name')}')")
    if address and address.lower() not in (rec.get("address") or "").lower():
        problems.append(f"address missing '{address}' (stored: '{rec.get('address')}')")
    if phone and _digits(phone) not in _digits(rec.get("phone")):
        problems.append(f"phone missing '{phone}' (stored: '{rec.get('phone')}')")
    return "; ".join(problems) if problems else None


# --- scenarios --------------------------------------------------------------
# Each supplies concrete values and asserts they land in the stored record.

SCENARIOS = [
    {
        "name": "front_loaded_all",  # everything in one breath — must NOT re-ask
        "turns": [
            "Hi, my AC is out. I'm John Reyes at 12 Birch Lane, my number's 555-201-4488, it's residential, and I need someone soon.",
            "Yeah, whatever's the soonest opening.",
            "Yes, book it.",
        ],
        "check": booking_has(name="Reyes", address="12 Birch", phone="5552014488"),
    },
    {
        "name": "piecemeal_ordered",
        "turns": [
            "I need an AC tune-up.",
            "Residential.",
            "Mara Quinn.",
            "9 Elm Street.",
            "555-889-2211.",
            "Soonest opening is fine.",
            "Yes, book it.",
        ],
        "check": booking_has(name="Quinn", address="9 Elm", phone="5558892211"),
    },
    {
        "name": "out_of_order",
        "turns": [
            "My furnace won't start. My callback is 555-333-1000.",
            "It's residential, address is 88 Cedar Court.",
            "Name's Priya Anand.",
            "Book the first opening.",
            "Yes.",
        ],
        "check": booking_has(name="Anand", address="88 Cedar", phone="5553331000"),
    },
    {
        "name": "address_correction",
        "turns": [
            "AC repair, residential. Tom Blake, 100 Oak Street, 555-777-8888.",
            "Actually the address is 110 Oak Street, not 100.",
            "First opening's fine, book it.",
            "Yes.",
        ],
        "check": booking_has(name="Blake", address="110 Oak", phone="5557778888"),
    },
    {
        "name": "phone_correction",
        "turns": [
            "Furnace tune-up, residential. Gina Lee, 5 Maple Ave.",
            "My number is 555-100-2000.",
            "Wait, it's 555-100-2001.",
            "Soonest works, book it.",
            "Yes.",
        ],
        "check": booking_has(name="Lee", address="5 Maple", phone="5551002001"),
    },
    {
        "name": "commercial_full",
        "turns": [
            "Our office AC is down, commercial. Bridgeport Dental Group, 88 Commerce Boulevard, Suite 200. 555-987-6543.",
            "Whatever's soonest.",
            "Yes, book it.",
        ],
        "check": booking_has(name="Bridgeport", address="88 Commerce", phone="5559876543"),
    },
    {
        "name": "suite_unit_address",
        "turns": [
            "Commercial AC issue. Hillside Realty, 400 Main Street, Suite 12B. 555-222-3344.",
            "Soonest opening.",
            "Yes.",
        ],
        "check": booking_has(name="Hillside", address="Suite 12B", phone="5552223344"),
    },
    {
        "name": "spelled_name",
        "turns": [
            "Furnace repair, residential. My name is Krzysztof Nowak.",
            "Address is 3 Willow Lane, 555-808-9090.",
            "Soonest is fine, book it.",
            "Yes.",
        ],
        "check": booking_has(name="Nowak", address="3 Willow", phone="5558089090"),
    },
    {
        "name": "change_time_after_confirm",
        "turns": [
            "AC tune-up, residential. Amy Lang, 8 Rose Street, 555-444-1212.",
            "Yeah, book the first opening.",
            "Actually, can we do a later time that same day?",
            "Yes, that works.",
        ],
        "check": booking_has(name="Lang", address="8 Rose", phone="5554441212"),
    },
    {
        "name": "reluctant_phone",
        "turns": [
            "AC repair, residential. Sam Doyle, 7 Birch Road.",
            "I'd rather not give a phone number.",
            "Just book the soonest.",
            "Yes.",
        ],
        "check": booking_has(name="Doyle", address="7 Birch"),  # phone optional
    },
    {
        "name": "urgent_priority_info",  # Tier B — priority must carry the contact info
        "turns": [
            "My furnace is dead and it's freezing — my mom's 80 and lives with me.",
            "Residential, 44 Larkspur Court. I'm Dan Farrow, 555-330-1200.",
            "Please get someone out as soon as you can.",
        ],
        "check": priority_has(name="Farrow", address="44 Larkspur", phone="5553301200"),
    },
    {
        "name": "emergency_priority_info",  # Tier C — flag must carry name+address
        "turns": [
            "There's a strong gas smell in my kitchen.",
            "Okay, I'm going outside now.",
            "I'm out front. Nadia Okafor, 51 Harper Street, 555-620-7788.",
        ],
        "check": priority_has(name="Okafor", address="51 Harper"),
    },
]


# --- runner -----------------------------------------------------------------

def _diagnostics(agent_lines):
    text = " ".join(agent_lines).lower()
    apologies = text.count("sorry") + text.count("apolog")
    questions = sum(1 for ln in agent_lines if "?" in ln)
    return apologies, questions


def run(sc, api_key, assistant_id):
    requests.post(f"{LOCAL_BASE}/admin/reset", timeout=10)
    print("\n" + "=" * 74)
    print(f"  {sc['name']}")
    print("=" * 74)

    prev = None
    agent_lines = []
    for turn in sc["turns"]:
        print(f"  caller > {turn}")
        reply, prev = chat(api_key, assistant_id, turn, prev)
        agent_lines.append(reply)
        for line in reply.splitlines():
            print(f"  DANIEL > {line}")
        time.sleep(0.4)

    state = requests.get(f"{LOCAL_BASE}/admin/state", timeout=10).json()
    rec = _latest_new_booking(state) or _latest_priority(state)
    print("  " + "-" * 40)
    if rec:
        print(f"  STORED → name={rec.get('name')!r}  address={rec.get('address')!r}  phone={rec.get('phone')!r}")
    else:
        print("  STORED → (nothing created)")
    apologies, questions = _diagnostics(agent_lines)
    print(f"  DIAGNOSTICS → apologies: {apologies}   agent questions: {questions}   turns: {len(sc['turns'])}")

    fail = sc["check"](state)
    if fail:
        print(f"  → ❌ FAIL: {fail}")
        return False
    print("  → ✅ PASS (all provided fields captured)")
    return True


def main():
    api_key = _require("VAPI_API_KEY")
    assistant_id = _require("VAPI_ASSISTANT_ID")
    try:
        requests.get(f"{LOCAL_BASE}/health", timeout=5)
    except Exception:
        sys.exit(f"Local backend not reachable at {LOCAL_BASE}. Start uvicorn (and point WEBHOOK_URL at it).")

    wanted = [a.lower() for a in sys.argv[1:]]
    scenarios = [s for s in SCENARIOS if not wanted or any(w in s["name"] for w in wanted)]

    results = []
    for sc in scenarios:
        results.append((sc["name"], run(sc, api_key, assistant_id)))

    print("\n" + "=" * 74)
    print("  SUMMARY — field capture")
    print("=" * 74)
    for name, ok in results:
        print(f"  {'✅ PASS' if ok else '❌ FAIL'}   {name}")
    fails = [n for n, ok in results if not ok]
    if fails:
        print(f"\n  {len(fails)} scenario(s) dropped provided info: {', '.join(fails)}")
        sys.exit(1)
    print("\n  All provided fields were captured. Skim the DIAGNOSTICS lines for over-apologizing / excess questions.")


if __name__ == "__main__":
    main()
