# Summit Air — AI Phone Scheduling Agent ("Daniel")

An inbound phone agent for a 40-technician regional HVAC company. It answers
calls as **Daniel**, figures out the HVAC issue, triages urgency (no heat in
winter, no AC with a medical condition, gas smell), determines residential vs.
commercial, collects name/address/availability, and books a service call —
escalating emergencies to a priority queue.

**Stack:** Vapi (assistant + `gpt-4o-mini` pass-through + telephony + `vapi`/Savannah
voice) → single webhook → FastAPI backend → pluggable CRM (SQLite mock today,
ServiceTitan-ready). ngrok exposes the backend during development.

---

## Architecture

```
  Caller ──phone──▶ Twilio ──▶ Vapi assistant (Daniel)
                                 │  prompt + gpt-4o-mini + Savannah voice
                                 │  4 tools ──POST /vapi/tools──▶ FastAPI (main.py)
                                 │                                   │
                                 │                                   ▼
                                 │                            crm/ backend interface
                                 │                             ├─ mock  (SQLite, default)
                                 │                             └─ servicetitan (stub)
                                 └── caller ID {{customer.number}} ▶ lookup_customer on call start
```

The webhook talks only to the `CRMBackend` interface, so swapping the scheduling
system never touches the tools, prompt, or Vapi assistant — flip `CRM_BACKEND`.

## Files
| File | Purpose |
|------|---------|
| `main.py` | FastAPI: `POST /vapi/tools` webhook, `/admin/*`, `/dashboard` |
| `db.py` | SQLite schema + seed (customers, techs, slots, backlog bookings) |
| `crm/base.py` | `CRMBackend` interface (the seam) |
| `crm/mock.py` | SQLite implementation — the default backend |
| `crm/servicetitan.py` | Production adapter **stub**, mapping each tool to the real ServiceTitan API |
| `crm/__init__.py` | Factory: picks backend from `CRM_BACKEND` |
| `system_prompt.txt` | Daniel's behavior spec (v2, hardened) |
| `create_assistant.py` | Create/update the Vapi assistant + register the 4 tools + caller-ID wiring |
| `chat_test.py` | Text-chat REPL via Vapi `/chat` (fast, near-free iteration) |
| `stress_test.py` | Runs the EDGE_CASES scenarios through `/chat` with backend assertions |
| `view_state.py` | Pops the dashboard + prints a CRM summary |
| `dashboard.html` | Live dispatch board served at `/dashboard` |
| `attach_number.py` | List / assign a Vapi phone number |

## The 4 tools
`lookup_customer` · `check_availability` · `create_booking` · `flag_priority` —
all dispatched from the single `POST /vapi/tools` webhook.

---

## Quick start (one command)
All config lives in **`.env`** (copy from `.env.example`, add your `VAPI_API_KEY`).

```bash
cp .env.example .env      # then edit .env: add VAPI_API_KEY (IDs may already be filled)
./start.sh                # creates venv on first run, starts backend + ngrok,
                          # and writes the discovered WEBHOOK_URL into .env
```

`start.sh` prints the dashboard URL and the `WEBHOOK_URL`. Leave it running
(backend + ngrok live there; Ctrl-C stops both).

Then, in **another terminal**:
```bash
source activate.sh          # loads the venv + all your .env vars (incl. WEBHOOK_URL)
python create_assistant.py  # push prompt/tools + webhook to the assistant
python chat_test.py         # iterate over text (cheap), or call the phone number
```

`activate.sh` is the "run everything elsewhere" helper — source it in any new
terminal and every script has the venv and env vars it needs.

### Manual setup (if you'd rather not use the scripts)
```bash
python3 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt
uvicorn main:app --port 8001 --reload      # terminal 1
ngrok http 8001                            # terminal 2  -> WEBHOOK_URL = https URL + /vapi/tools
# terminal 3: export VAPI_API_KEY / VAPI_ASSISTANT_ID / WEBHOOK_URL, then:
python create_assistant.py
```

## Testing tools
```bash
python stress_test.py               # run all edge-case scenarios (needs VAPI_API_KEY + ASSISTANT_ID)
python stress_test.py gas jailbreak # just matching scenarios
python view_state.py                # open the live dashboard + summary
python view_state.py all            # also print the seeded backlog
curl -s -X POST localhost:8001/admin/reset   # clean slate between runs
```

### Live dashboard
Open **http://localhost:8001/dashboard** — auto-refreshing dispatch board with the
schedule grid (open / booked / booked-this-session), the priority queue, and
session bookings. Great for the live eval: the evaluator watches flags and
bookings land in real time.

---

## Mock CRM (SQLite)
- `summit_air.db` is disposable; **persists across restarts** (delete it or hit
  `/admin/reset` to wipe). Seeded with 6 techs across 3 counties, 2 known
  customers, and a **front-loaded backlog** (near-term days ~85% booked, later
  days open) so booking isn't trivial.
- Gas / CO / smoke / burning mentions escalate to `EMERGENCY`; other urgent cases
  (no heat + vulnerable person, commercial down) are `URGENT`.

## Caller-ID auto-lookup
`create_assistant.py` appends a runtime block passing Vapi's `{{customer.number}}`
so Daniel calls `lookup_customer` **before greeting** and welcomes known callers by
name. Demo it on the mock:
```bash
curl -s -X POST localhost:8001/admin/add_customer -H 'Content-Type: application/json' \
  -d '{"phone":"+1EVALNUMBER","name":"Their Name","address":"123 St, Washington County"}'
```

## Going live with ServiceTitan (future)
```bash
export CRM_BACKEND=servicetitan
export ST_CLIENT_ID=... ST_CLIENT_SECRET=... ST_APP_KEY=... ST_TENANT_ID=...
```
`crm/servicetitan.py` documents which ServiceTitan API module implements each tool
(CRM search → Capacity → Bookings). Needs Summit Air's API credentials — a
customer-provisioning step. Until then, `mock` is the stand-in.

## Deliberately deferred (see system_prompt.txt / EDGE_CASES.md)
Reschedule/cancel tooling, live `transfer_call`, multi-language, call-recording
disclosure, and the real ServiceTitan hookup — scoped out to keep the callable
agent focused. Documented, not forgotten.
