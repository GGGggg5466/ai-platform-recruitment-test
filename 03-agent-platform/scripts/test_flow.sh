#!/usr/bin/env bash
set -e

echo "1) login as intern"
TOKEN_INTERN=$(curl -s http://localhost:8000/auth/login   -H "Content-Type: application/json"   -d '{"user_id":"u_intern","role":"intern"}' | python -c "import sys, json; print(json.load(sys.stdin)['token'])")

echo "2) list tools (intern)"
curl -s http://localhost:8000/tools -H "Authorization: Bearer $TOKEN_INTERN" | python -m json.tool

echo "3) try call internal tool (should 403)"
curl -s -o /dev/null -w "%{http_code}
" http://localhost:8000/tools/call   -H "Authorization: Bearer $TOKEN_INTERN" -H "Content-Type: application/json"   -d '{"server":"mcp_internal","tool_name":"internal.read_kb","args":{"topic":"x"}}'

echo "4) login as admin"
TOKEN_ADMIN=$(curl -s http://localhost:8000/auth/login   -H "Content-Type: application/json"   -d '{"user_id":"u_admin","role":"admin"}' | python -c "import sys, json; print(json.load(sys.stdin)['token'])")

echo "5) admin call admin tool (should ok)"
curl -s http://localhost:8000/tools/call   -H "Authorization: Bearer $TOKEN_ADMIN" -H "Content-Type: application/json"   -d '{"server":"mcp_admin","tool_name":"admin.rotate_key","args":{"target":"service-A"}}' | python -m json.tool

echo "Done."
