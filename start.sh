#!/usr/bin/env bash
# ============================================================
#  Summit Air — bring the whole local stack up with one command.
#  Starts the FastAPI backend + ngrok, discovers the public URL,
#  and writes WEBHOOK_URL back into .env so other terminals
#  (create_assistant.py, the tests) pick it up.
#
#  Usage:   ./start.sh
#  Stop:    Ctrl-C (stops backend + ngrok)
# ============================================================
set -euo pipefail
cd "$(dirname "$0")"

# --- config ---------------------------------------------------------------
if [[ ! -f .env ]]; then
  echo "ERROR: no .env file. Copy .env.example to .env and fill it in."; exit 1
fi
set -a; source .env; set +a
PORT="${PORT:-8001}"
ROOT="$(pwd)"

# --- venv (create + install deps on first run) ----------------------------
if [[ ! -d .venv ]]; then
  echo "First run: creating virtualenv + installing deps..."
  python3 -m venv .venv
  ./.venv/bin/pip install -q -r requirements.txt
fi

# --- clear anything stale on our port / old ngrok -------------------------
lsof -ti:"$PORT" 2>/dev/null | xargs kill -9 2>/dev/null || true
pkill -f "ngrok http" 2>/dev/null || true
sleep 1

# --- backend (runs from backend/ so `import crm` / `import db` resolve) -----
echo "Starting backend on :$PORT ..."
( cd backend && exec "$ROOT/.venv/bin/uvicorn" main:app --port "$PORT" --reload ) \
  >/tmp/summitair_backend.log 2>&1 &
BACKEND_PID=$!

# --- ngrok ----------------------------------------------------------------
echo "Starting ngrok ..."
ngrok http "$PORT" --log=stdout >/tmp/summitair_ngrok.log 2>&1 &
NGROK_PID=$!

# --- discover the public https URL ----------------------------------------
URL=""
for _ in $(seq 1 20); do
  URL=$(curl -s localhost:4040/api/tunnels 2>/dev/null | python3 -c "
import sys, json
try:
    tunnels = json.load(sys.stdin)['tunnels']
    print(next(t['public_url'] for t in tunnels if t['public_url'].startswith('https')))
except Exception:
    pass" 2>/dev/null || true)
  [[ -n "$URL" ]] && break
  sleep 1
done
if [[ -z "$URL" ]]; then
  echo "ERROR: ngrok didn't come up. See /tmp/summitair_ngrok.log"; exit 1
fi
WEBHOOK_URL="$URL/vapi/tools"

# --- persist WEBHOOK_URL into .env ----------------------------------------
python3 - "$WEBHOOK_URL" <<'PY'
import re, sys
url = sys.argv[1]; path = ".env"; s = open(path).read()
if re.search(r'^WEBHOOK_URL=', s, flags=re.M):
    s = re.sub(r'^WEBHOOK_URL=.*$', 'WEBHOOK_URL=' + url, s, flags=re.M)
else:
    s = s.rstrip('\n') + '\nWEBHOOK_URL=' + url + '\n'
open(path, 'w').write(s)
PY

# --- summary --------------------------------------------------------------
cat <<EOF

======================================================================
  Summit Air stack is UP
======================================================================
  Backend    : http://localhost:$PORT      (logs: /tmp/summitair_backend.log)
  Dashboard  : http://localhost:$PORT/dashboard
  ngrok URL  : $URL
  WEBHOOK_URL: $WEBHOOK_URL
               (written to .env)

  In ANOTHER terminal:
     source activate.sh            # load venv + your .env vars
     python create_assistant.py    # push prompt/tools + this webhook to the assistant
     python stress_booking.py      # run the info-gathering tests

  Keep THIS terminal open — backend + ngrok run here. Ctrl-C stops both.
======================================================================
EOF

# --- keep running; clean up children on Ctrl-C ----------------------------
trap 'echo; echo "Stopping backend + ngrok..."; kill "$BACKEND_PID" "$NGROK_PID" 2>/dev/null || true; pkill -f "ngrok http" 2>/dev/null || true; exit 0' INT TERM
wait
