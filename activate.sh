# Source this in any NEW terminal to run scripts (create_assistant.py, tests, etc.):
#     source activate.sh
# It activates the Python venv and exports all your .env vars (including the
# WEBHOOK_URL that start.sh discovered).
_dir="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck disable=SC1091
source "$_dir/.venv/bin/activate" 2>/dev/null || echo "(.venv not found — run ./start.sh once to create it)"
set -a; source "$_dir/.env"; set +a
echo "Loaded: assistant=${VAPI_ASSISTANT_ID:-unset}  webhook=${WEBHOOK_URL:-unset}"
