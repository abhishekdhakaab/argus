#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")" && pwd)"
if [ -f "$REPO_ROOT/.env" ]; then
  set -a
  source "$REPO_ROOT/.env"
  set +a
fi

BASE="http://localhost:8080"
AUTH_PASSWORD="${DEV_AUTH_PASSWORD:?Set DEV_AUTH_PASSWORD in .env}"
PASS=0
FAIL=0

ok()   { echo "  PASS  $1"; PASS=$((PASS+1)); }
fail() { echo "  FAIL  $1 — $2"; FAIL=$((FAIL+1)); }

# Passing the stream through the environment leaves stdin available to Python.
parse_sse() {
  ARGUS_RAW="$1" python3 -c "
import os, json
tokens = []
done_data = None
for line in os.environ['ARGUS_RAW'].splitlines():
    line = line.strip()
    if not line.startswith('data: '):
        continue
    try:
        event = json.loads(line[6:])
    except Exception:
        continue
    t = event.get('type')
    if t == 'token':
        tokens.append(event.get('data', ''))
    elif t == 'done':
        done_data = event.get('data', {})
answer  = ''.join(tokens).strip()
cost    = done_data.get('cost_usd',   '?') if done_data else '?'
latency = done_data.get('latency_ms', '?') if done_data else '?'
run_id  = done_data.get('run_id',     '?') if done_data else '?'
print(f'ANSWER:{answer}')
print(f'COST:{cost}')
print(f'LATENCY:{latency}')
print(f'RUN_ID:{run_id}')
"
}

echo ""
echo "=== Argus smoke + full test ==="
echo ""

echo "1. Health check"
HEALTH=$(curl -sf "$BASE/health" || true)
if echo "$HEALTH" | grep -q '"status":"ok"'; then
  DB=$(echo "$HEALTH" | python3 -c "import sys,json; print(json.load(sys.stdin)['db'])" 2>/dev/null)
  ok "gateway alive — db=$DB"
  echo "     $HEALTH"
else
  fail "gateway health" "$HEALTH"
fi

echo ""
echo "2. Auth — get token"
AUTH=$(curl -sf -X POST "$BASE/api/v1/auth/token" \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"tenant-alpha\",\"password\":\"$AUTH_PASSWORD\"}" || true)

TOKEN=$(echo "$AUTH" | python3 -c "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || true)

if [ -n "$TOKEN" ]; then
  ok "token received"
  echo "     ${TOKEN:0:60}..."
else
  fail "auth token" "$AUTH"
  echo "Cannot continue without a token."
  exit 1
fi

echo ""
echo "3. Auth — refresh token"
REFRESH=$(curl -sf -X POST "$BASE/api/v1/auth/refresh" \
  -H "Authorization: Bearer $TOKEN" || true)
if echo "$REFRESH" | grep -q "access_token"; then
  ok "token refreshed"
else
  fail "token refresh" "$REFRESH"
fi

echo ""
echo "4. Ingest — 3 documents"
# Model downloads can make the first RAG startup noticeably slower.
for i in $(seq 1 18); do
  RAG_HEALTH=$(curl -sf http://localhost:8081/health 2>/dev/null || true)
  if echo "$RAG_HEALTH" | grep -q '"status":"ok"'; then break; fi
  [ "$i" -eq 18 ] && { fail "rag-ready" "RAG service not healthy after 90s"; exit 1; }
  sleep 5
done

ingest() {
  curl -sf -X POST "$BASE/api/v1/ingest/documents" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "$1" || true
}

R1=$(ingest '{"text":"The Q3 cloud infrastructure budget is capped at $50,000. Any overrun must be approved by the CTO. AWS spend accounts for 60% of total cloud cost.","source":"cloud-budget-policy.txt"}')
R2=$(ingest '{"text":"Q3 actual cloud spending reached $47,200. AWS was $28,000, GCP was $12,000, and Azure was $7,200. This is within the approved budget.","source":"q3-spend-report.txt"}')
R3=$(ingest '{"text":"The vendor SLA requires 99.9% uptime. Current vendor status is operational. Last incident was 45 days ago lasting 12 minutes.","source":"vendor-sla.txt"}')

for R in "$R1" "$R2" "$R3"; do
  if echo "$R" | grep -q "chunks_inserted"; then
    CHUNKS=$(echo "$R" | python3 -c "import sys,json; print(json.load(sys.stdin).get('chunks_inserted',0))" 2>/dev/null)
    SRC=$(echo "$R"   | python3 -c "import sys,json; print(json.load(sys.stdin).get('source','?'))"    2>/dev/null)
    ok "$SRC — $CHUNKS chunk(s)"
  else
    fail "ingest" "$R"
  fi
done

echo ""
echo "5. Query — SSE streaming (3 queries)"

run_query() {
  local LABEL="$1"
  local Q="$2"
  echo ""
  echo "   [$LABEL] $Q"

  RAW=$(curl -sf -N -X POST "$BASE/api/v1/query" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json" \
    -d "{\"query\":\"$Q\"}" 2>/dev/null || true)

  PARSED=$(parse_sse "$RAW")
  ANSWER=$(echo "$PARSED"  | grep "^ANSWER:"  | sed 's/^ANSWER://')
  COST=$(echo "$PARSED"    | grep "^COST:"    | sed 's/^COST://')
  LATENCY=$(echo "$PARSED" | grep "^LATENCY:" | sed 's/^LATENCY://')
  RUN_ID=$(echo "$PARSED"  | grep "^RUN_ID:"  | sed 's/^RUN_ID://')

  if [ -n "$ANSWER" ]; then
    ok "$LABEL"
    echo "     Answer  : $ANSWER"
    echo "     Latency : ${LATENCY}ms   Cost: \$${COST}   run_id: $RUN_ID"
  else
    fail "$LABEL" "empty answer — raw tail: $(echo "$RAW" | tail -4)"
  fi
}

run_query "doc-only"     "What is the cloud budget policy for Q3?"
run_query "multi-source" "Compare our cloud budget policy with actual Q3 spending"
run_query "vendor"       "What is the current vendor uptime status and SLA?"

echo ""
echo "6. Usage dashboard"
USAGE=$(curl -sf "$BASE/api/v1/tenants/00000000-0000-0000-0000-000000000001/usage" \
  -H "Authorization: Bearer $TOKEN" || true)
if echo "$USAGE" | grep -q "queries_today"; then
  ok "usage endpoint"
  echo "$USAGE" | python3 -c "
import sys, json
d = json.load(sys.stdin)
print(f\"     queries_today={d['queries_today']}  avg_latency={d['avg_latency_ms']:.0f}ms  p95={d['p95_latency_ms']:.0f}ms  total_cost=\${d['total_cost_usd']:.6f}  top_tools={d['top_tools']}\")
" 2>/dev/null
else
  fail "usage" "$USAGE"
fi

echo ""
echo "=============================="
echo "  PASSED: $PASS   FAILED: $FAIL"
echo "=============================="
echo ""
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
