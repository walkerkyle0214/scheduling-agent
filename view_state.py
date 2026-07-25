"""
Pretty-print the Summit Air mock CRM state for quick eyeballing during testing.

Shows the priority queue and bookings, separating the pre-seeded backlog
(booking ids starting with BK-SEED) from bookings the agent made during your
test run — so you can instantly see what your last call/chat produced.

Usage:
    python view_state.py                 # pops open the live dashboard + prints summary
    python view_state.py 8000            # different port
    python view_state.py all             # ALSO print the fake seeded backlog
    python view_state.py text            # terminal only, don't open the browser
    python view_state.py 8000 all text   # combine, any order
    BASE_URL=https://x.ngrok-free.dev python view_state.py
"""

from __future__ import annotations

import os
import sys
import webbrowser

import requests

args = [a.lower() for a in sys.argv[1:]]
show_all = any(a in ("all", "backlog", "full") for a in args)
text_only = any(a in ("text", "notab", "no-open", "noopen") for a in args)
port = next((a for a in args if a.isdigit()), "8001")
base = os.environ.get("BASE_URL", f"http://localhost:{port}")

# Pop the visual dashboard open in the default browser (unless text-only).
if not text_only:
    dash_url = f"{base}/dashboard"
    print(f"Opening dashboard → {dash_url}")
    webbrowser.open(dash_url)

try:
    state = requests.get(f"{base}/admin/state", timeout=10).json()
except Exception as exc:
    sys.exit(f"Could not reach {base}/admin/state — is the backend running? ({exc})")

bookings = state.get("bookings", [])
priority = state.get("priority_queue", [])
seeded = [b for b in bookings if str(b.get("booking_id", "")).startswith("BK-SEED")]
live = [b for b in bookings if not str(b.get("booking_id", "")).startswith("BK-SEED")]

BAR = "=" * 68


def line(label: str, value: str) -> str:
    return f"  {label:<14}{value}"


print(BAR)
print(f"  SUMMIT AIR — CRM STATE   ({base})")
print(BAR)
print(f"  Slots:   {state.get('open_slots', '?')} open / {state.get('booked_slots', '?')} booked")
print(f"  Backlog: {len(seeded)} pre-existing appointments")
print(f"  New:     {len(live)} booking(s) made this session")
print(f"  Priority queue: {len(priority)} entry(ies)")

# --- Priority queue (most important during triage testing) ---
print("\n" + BAR)
print("  PRIORITY QUEUE")
print(BAR)
if not priority:
    print("  (empty)")
for p in priority:
    flag = "🚨" if p.get("level") == "EMERGENCY" else "⚠️ "
    print(f"\n  {flag} [{p.get('level')}]  {p.get('priority_id')}")
    print(line("name", str(p.get("name"))))
    print(line("address", str(p.get("address"))))
    print(line("phone", str(p.get("phone"))))
    print(line("reason", str(p.get("reason"))))
    if p.get("details"):
        print(line("details", str(p.get("details"))))

# --- Bookings made this session ---
print("\n" + BAR)
print("  NEW BOOKINGS (this session)")
print(BAR)
if not live:
    print("  (none yet)")
for b in live:
    when = (f"{b.get('scheduled_day')} {b.get('scheduled_date')} {b.get('scheduled_window')}"
            if b.get("scheduled_date") else f"UNSCHEDULED (requested: {b.get('preferred_window')})")
    print(f"\n  ✅ {b.get('booking_id')}   [{str(b.get('urgency', '')).upper()}]")
    print(line("name", str(b.get("name"))))
    print(line("type", str(b.get("property_type"))))
    print(line("address", str(b.get("address"))))
    print(line("phone", str(b.get("phone"))))
    print(line("issue", str(b.get("issue_description"))))
    print(line("when", when))
    print(line("tech", str(b.get("technician_name"))))

# --- Pre-seeded backlog (only when `all` is passed) ---
if show_all:
    print("\n" + BAR)
    print(f"  SEEDED BACKLOG — {len(seeded)} pre-existing appointments")
    print(BAR)
    if not seeded:
        print("  (none)")
    for b in sorted(seeded, key=lambda x: (str(x.get("scheduled_date")), str(x.get("scheduled_window")))):
        when = f"{b.get('scheduled_day','')} {b.get('scheduled_date','')} {b.get('scheduled_window',''):<16}"
        print(f"  {b.get('booking_id'):<12} {when} {b.get('name')} ({b.get('property_type')}) — {b.get('technician_name')}")
    print("\n" + BAR)
    print(f"  {len(seeded)} backlog + {len(live)} new = {len(bookings)} total bookings")
    print(BAR)
else:
    print("\n" + BAR)
    print(f"  (Backlog of {len(seeded)} pre-existing appointments hidden — run `python view_state.py {port} all` to show.)")
    print(BAR)
