#!/usr/bin/env bash
set -euo pipefail

# Prefer explicit loopback; can be overridden by env BASE=...
BASE="${BASE:-http://127.0.0.1:8000}"

py_get_token(){
  python - <<'PY'
import sys, json
print(json.load(sys.stdin)['token'])
PY
}

# Robust login helper: prints raw body on non-200, avoids JSONDecodeError hiding root cause
login() {
  local role="$1"
  local user="$2"
  local resp body code

  resp="$(curl -sS -w $'\n%{http_code}' -X POST "$BASE/auth/login"     -H "Content-Type: application/json"     -d "{\"user_id\":\"$user\",\"role\":\"$role\"}")"

  body="${resp%$'\n'*}"
  code="${resp##*$'\n'}"

  if [[ "$code" != "200" ]]; then
    echo "[login:$role] HTTP $code" >&2
    echo "[login:$role] RAW BODY:" >&2
    echo "$body" >&2
    exit 1
  fi

  python - <<PY
import json
print(json.loads(r'''$body''')["token"])
PY
}

echo "[0] wait gateway ready..."
for i in $(seq 1 60); do
  if curl -fsS "$BASE/openapi.json" >/dev/null 2>&1; then
    echo "gateway ready: $BASE"
    break
  fi
  echo "  waiting... ($i/60)"
  sleep 1
done

echo "[A] login tokens"
TOKEN_INTERN="$(login intern u_intern)"
TOKEN_EMPLOYEE="$(login employee u_employee)"
TOKEN_ADMIN="$(login admin u_admin)"

echo "[B] /tools allowed snapshot (intern/employee/admin)"
# Print a compact summary: tool_name -> allowed for each role
summarize_tools(){
  local token=$1
  local resp body code
  resp="$(curl -sS -w $'
%{http_code}' "$BASE/tools" -H "Authorization: Bearer $token")"
  body="${resp%$'
'*}"
  code="${resp##*$'
'}"
  if [[ "$code" != "200" ]]; then
    echo "[tools] HTTP $code" >&2
    echo "[tools] RAW BODY:" >&2
    echo "$body" >&2
    exit 1
  fi
  python - <<PY
import json
j=json.loads(r'''$body''')
for t in j.get('tools',[]):
  print(f"{t.get('server')}.{t.get('name')}	{t.get('required_scope')}	allowed={t.get('allowed')}")
PY
}

echo "--- intern tools ---"; summarize_tools "$TOKEN_INTERN" | head -n 30
echo "--- employee tools ---"; summarize_tools "$TOKEN_EMPLOYEE" | head -n 30
echo "--- admin tools ---"; summarize_tools "$TOKEN_ADMIN" | head -n 30

echo "[C] /tools/call RBAC 403/200 (internal)"
# intern should be forbidden
CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/tools/call"   -H "Authorization: Bearer $TOKEN_INTERN" -H "Content-Type: application/json"   -d '{"server":"mcp_internal","tool_name":"internal.query_sqlite","args":{"query_id":"list_users","params":{}}}')
echo "intern internal.query_sqlite => HTTP $CODE (expect 403)"

# employee should pass
curl -s "$BASE/tools/call"   -H "Authorization: Bearer $TOKEN_EMPLOYEE" -H "Content-Type: application/json"   -d '{"server":"mcp_internal","tool_name":"internal.query_sqlite","args":{"query_id":"list_users","params":{}}}' | python -m json.tool

curl -s "$BASE/tools/call"   -H "Authorization: Bearer $TOKEN_EMPLOYEE" -H "Content-Type: application/json"   -d '{"server":"mcp_internal","tool_name":"internal.run_python","args":{"task":"math.add","args":{"a":3,"b":5}}}' | python -m json.tool

echo "[D] /chat stateful memory_size 2 -> 4 (backward compatible demo mode)"
# No model (and DEFAULT_MODEL empty) => old demo reply, but memory still grows 2->4
curl -s "$BASE/chat" -H "Authorization: Bearer $TOKEN_EMPLOYEE" -H "Content-Type: application/json"   -d '{"conversation_id":"c_demo","message":"hello"}' | python -m json.tool
curl -s "$BASE/chat" -H "Authorization: Bearer $TOKEN_EMPLOYEE" -H "Content-Type: application/json"   -d '{"conversation_id":"c_demo","message":"hello again"}' | python -m json.tool

echo "[E] LiteLLM model-level authorization via /chat?model=..."
MODEL_LLM=${LLM_MODEL_NAME:-/models/Qwen3-30B-A3B-Instruct-2507-FP8}
MODEL_VLM=${VLM_MODEL_NAME:-gemma-3-27b-it}

# LLM+VLM only (OLM removed). Policy here:
# - intern/employee: allow LLM only
# - admin: allow LLM + VLM

# intern -> VLM should be 403 blocked by LiteLLM
RESP_HEADERS=$(mktemp)
RESP_BODY=$(mktemp)
STATUS=$(curl -s -D "$RESP_HEADERS" -o "$RESP_BODY" -w "%{http_code}" "$BASE/chat"   -H "Authorization: Bearer $TOKEN_INTERN" -H "Content-Type: application/json"   -d "{\"conversation_id\":\"c_litellm\",\"message\":\"intern try LLM\",\"model\":\"$MODEL_LLM\"}")
echo "intern model=LLM => HTTP $STATUS (expect 200)"
cat "$RESP_BODY" | python -m json.tool || true
rm -f "$RESP_HEADERS" "$RESP_BODY"

# intern -> VLM should be 403
RESP_HEADERS=$(mktemp)
RESP_BODY=$(mktemp)
STATUS=$(curl -s -D "$RESP_HEADERS" -o "$RESP_BODY" -w "%{http_code}" "$BASE/chat"   -H "Authorization: Bearer $TOKEN_INTERN" -H "Content-Type: application/json"   -d "{\"conversation_id\":\"c_litellm\",\"message\":\"intern try VLM\",\"model\":\"$MODEL_VLM\"}")
echo "intern model=VLM => HTTP $STATUS (expect 403)"
grep -i "^x-blocked-by:" "$RESP_HEADERS" || (echo "missing x-blocked-by header" && exit 1)
cat "$RESP_BODY" | python -m json.tool || true
rm -f "$RESP_HEADERS" "$RESP_BODY"

# employee -> LLM should be 200
curl -s "$BASE/chat" -H "Authorization: Bearer $TOKEN_EMPLOYEE" -H "Content-Type: application/json"   -d "{\"conversation_id\":\"c_litellm\",\"message\":\"employee ok LLM\",\"model\":\"$MODEL_LLM\"}" | python -m json.tool

# employee -> VLM should be 403
RESP_HEADERS=$(mktemp)
RESP_BODY=$(mktemp)
STATUS=$(curl -s -D "$RESP_HEADERS" -o "$RESP_BODY" -w "%{http_code}" "$BASE/chat"   -H "Authorization: Bearer $TOKEN_EMPLOYEE" -H "Content-Type: application/json"   -d "{\"conversation_id\":\"c_litellm\",\"message\":\"employee try VLM\",\"model\":\"$MODEL_VLM\"}")
echo "employee model=VLM => HTTP $STATUS (expect 403)"
grep -i "^x-blocked-by:" "$RESP_HEADERS" || (echo "missing x-blocked-by header" && exit 1)
cat "$RESP_BODY" | python -m json.tool || true
rm -f "$RESP_HEADERS" "$RESP_BODY"

# admin -> VLM should be 200
curl -s "$BASE/chat" -H "Authorization: Bearer $TOKEN_ADMIN" -H "Content-Type: application/json"   -d "{\"conversation_id\":\"c_litellm\",\"message\":\"admin ok VLM\",\"model\":\"$MODEL_VLM\"}" | python -m json.tool

echo "[F] audit:events should contain allow/deny/chat"
# Show latest 20 audit events
if command -v docker >/dev/null 2>&1; then
  docker compose exec -T redis redis-cli LRANGE audit:events 0 20
else
  echo "docker not found in PATH; skip audit check"
fi

echo "[G] rate limit 200->429 (may take a moment)"
# Hammer /tools until rate limited. Uses user u_employee.
# Note: rate limit is global per user_id per minute.
CODE=200
COUNT=0
while [ "$CODE" = "200" ] && [ $COUNT -lt 120 ]; do
  CODE=$(curl -s -o /dev/null -w "%{http_code}" "$BASE/tools" -H "Authorization: Bearer $TOKEN_EMPLOYEE")
  COUNT=$((COUNT+1))
  if [ $((COUNT%10)) -eq 0 ]; then echo "  hit=$COUNT code=$CODE"; fi
done
echo "rate-limit result: hit=$COUNT last_code=$CODE (expect eventually 429)"

echo "[OK] all checks done."
