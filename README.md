# Summit Air — AI Phone Scheduling Agent ("Daniel")

An inbound phone agent for a regional HVAC company. It answers as **Daniel**,
figures out the HVAC issue, triages urgency (no heat in winter, no AC with a
medical condition, gas smell), collects name/address/availability, and books a
service call — escalating emergencies to a priority queue.

**Stack:** Vapi (assistant + LLM pass-through + telephony + `vapi`/Savannah voice)
→ one webhook → FastAPI backend → pluggable CRM (SQLite mock; ServiceTitan-ready).
ngrok exposes the backend during development.

---

## Codebase map

```
scheduling-agent/
├── agent/          ← TUNE THIS. The agent's behavior + how it's provisioned.
│   ├── system_prompt.txt      the brain — edit this to change how Daniel behaves
│   ├── create_assistant.py    push prompt + model + voice + tools to Vapi
│   └── attach_number.py       point the phone number at the assistant
│
├── backend/        ← the server the tools call
│   ├── main.py                POST /vapi/tools webhook + /admin/* + /dashboard
│   ├── db.py                  SQLite mock CRM (schema + seed data)
│   └── crm/                   pluggable backends (mock = default, servicetitan = stub)
│
├── dashboard/      ← the live dispatch board (served at /dashboard)
│   └── dashboard.html
│
├── tests/          ← everything for iterating + comparing models
│   ├── evals.py               scored suite + `--compare` model A/B
│   ├── stress_test.py         36 behavior scenarios (auto + review)
│   ├── stress_booking.py      info-gathering / data-capture scenarios
│   ├── chat_test.py           interactive text REPL
│   └── view_state.py          pop the dashboard + print CRM state
│
├── docs/
│   └── TESTING_LOG.md         every issue found in testing + how it was fixed
│
├── start.sh        one command: venv + backend + ngrok, writes WEBHOOK_URL to .env
├── activate.sh     source in any new terminal: loads venv + .env vars
├── .env            all your config in one place (git-ignored)
└── requirements.txt
```

**Presenting / tweaking live?** Everything you'll touch is in **`agent/`** — edit
`system_prompt.txt`, run `python agent/create_assistant.py`, test. That's the loop.

---

## Quick start (one command)

```bash
cp .env.example .env      # then edit .env: add VAPI_API_KEY (IDs may already be filled)
./start.sh                # venv (first run) + backend + ngrok; writes WEBHOOK_URL to .env
```

Leave `start.sh` running (backend + ngrok live there; Ctrl-C stops both). Then in
**another terminal**:

```bash
source activate.sh                 # loads venv + all .env vars (incl. WEBHOOK_URL)
python agent/create_assistant.py   # push prompt/model/voice/tools to the assistant
python tests/chat_test.py          # iterate over text — or call the phone number
```

## Command cheat-sheet

| Do this | Command |
|---|---|
| Push prompt/model/voice changes | `python agent/create_assistant.py` |
| Point number at the assistant | `python agent/attach_number.py assign $PHONE_NUMBER_ID` |
| Interactive text chat | `python tests/chat_test.py` |
| Score the current assistant | `python tests/evals.py` |
| Compare models | `python tests/evals.py --compare gpt-4o-mini gpt-4o` |
| Info-gathering stress test | `python tests/stress_booking.py` |
| Full behavior stress test | `python tests/stress_test.py` |
| Open dashboard + print state | `python tests/view_state.py` |
| Reset mock data (fresh dates) | `curl -X POST localhost:8001/admin/reset` |

## The 4 tools
`lookup_customer` · `check_availability` · `create_booking` · `flag_priority` —
all dispatched from the single `POST /vapi/tools` webhook to the active CRM backend.

---

## Notes

- **Swap the model** in `.env` (`MODEL` / `LLM_PROVIDER`), then re-provision. Compare
  objectively with `python tests/evals.py --compare <a> <b>`.
- **Mock CRM** is a disposable SQLite file (`backend/summit_air.db`) pre-loaded with a
  front-loaded backlog so booking isn't trivial. It reseeds relative to today; if left
  running across days, reset it for fresh dates.
- **Caller-ID** — Daniel looks the caller up by number on his first turn and greets a
  known customer by name.
- **ServiceTitan** — `backend/crm/servicetitan.py` is a documented stub; flip
  `CRM_BACKEND=servicetitan` + add `ST_*` creds to go live. Until then, `mock` is the
  stand-in.
- **Deferred** (see `docs/TESTING_LOG.md` and the prompt): reschedule/cancel tooling,
  live transfer, multi-language, call-recording disclosure.
