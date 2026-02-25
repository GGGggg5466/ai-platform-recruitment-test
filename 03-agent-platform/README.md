# HW3 Agent Platform：Gateway + MCP + LiteLLM + Langflow + LangGraph（最小侵入增量版）

> 測試環境：**WSL2 Ubuntu + Docker + Docker Compose**
> 
> 
> 測試方式：`curl` / `jq` / `docker compose exec`
> 
> 設計取向：目標 4 重點放在「平台穩定性」而非模型能力（可用性/可觀測性/可控性）
> 

本專案提供一個可驗收的 Agentic 平台骨架：

- Gateway（FastAPI）統一處理：Auth、RBAC、CID（correlation id）、統一錯誤封裝、Budgets、Stateful memory/TTL
- MCP servers：public/internal/admin
- LiteLLM：統一 LLM 上游（支援 mock_upstream 止損）
- Langflow：低碼端整合（容器內可直接呼叫 gateway）
- LangGraph：Agent 執行流程（tool visibility + tool-call policy）

---

## 四個目標（作業要求）與完成狀態

- ✅ 目標1：LangGraph Agent 權限矩陣（動態限制 MCP tools，可見性 + final defense）
- ✅ 目標2：Low-code 封裝（Langflow 自訂組件 + REST API 端到端呼叫）
- ✅ 目標3：MCP 強化（validation / allowlist / 統一錯誤 / correlation id）
- ✅ 目標4：冷啟動與狀態管理（Stateful memory + TTL + budgets + upstream_down 分流）

---

## 專案結構（壓縮檔檔案樹）

```
├── .env
├── .env.example
├── README.md
├── configs
│   ├── agent_permissions.yaml          # 角色→可見/可呼叫工具規則
│   └── tool_registry.yaml              # 工具註冊與對應（server/tool mapping）
├── docker-compose.yml                  # 服務編排（gateway/redis/mcp/langflow/litellm/mock）
├── gateway
│   └── app
│       ├── main.py                     # FastAPI 入口：/auth, /tools/call, /chat, /v1/agent/*
│       ├── auth.py                     # JWT / token
│       ├── policy.py                   # RBAC policy + final defense
│       ├── registry.py                 # tool registry
│       ├── agent.py                    # LangGraph agent / LLM plan / tool execution
│       ├── schemas.py                  # Pydantic schemas（validation 422）
│       ├── observability.py            # correlation id middleware / logs
│       ├── rate_limit.py               # budgets / rate limit（超額回 429）
│       └── audit.py                    # audit / security logging
├── langflow_components
│   ├── GatewayAgentComponent.py
│   └── GatewayLangGraphAgentComponent.py
├── litellm_config.yaml                 # LiteLLM routing/config
├── mcp_servers
│   ├── mcp_public/app/main.py          # public 工具（echo/time）
│   ├── mcp_internal/app/main.py        # internal 工具（read_kb/query_sqlite/run_python）
│   └── mcp_admin/app/main.py           # admin 工具（rotate_key）
├── mock_upstream/app/main.py           # 上游止損（可重現驗收）
└── scripts
    ├── bootstrap_litellm_keys.py        # LiteLLM keys 初始化
    ├── test_flow.sh                    # 驗收流程腳本（簡化）
    └── test_full.sh                    # 完整測試腳本（A–G）
```


## Quick Start：啟動服務

### 1) 一鍵啟動

```
docker compose down--remove-orphans
docker compose up-d
docker composeps
```

### 2) 健康檢查

```
curl-s-o /dev/null-w"gateway_http=%{http_code}\n" http://localhost:8000/docs
```

預期：`200`

---

## 驗收總前置（每次驗收前）

```
docker composeps
```

確認 `gateway / redis / mcp_* / langflow / litellm` 都是 Up。

---

# ✅ 目標1：Agent 權限矩陣（RBAC + Gateway Final Defense）

## 測試目的

驗證角色（employee/admin）在工具可見性與工具呼叫上均受到 RBAC 限制，且 Gateway 層具備 final defense（不靠前端隱藏）。

## 驗收指令

```
TOKEN_EMP=$(curl -s -X POST http://localhost:8000/auth/login -H"Content-Type: application/json" -d'{"user_id":"employee","role":"employee"}' | jq -r .token)
TOKEN_ADMIN=$(curl -s -X POST http://localhost:8000/auth/login -H"Content-Type: application/json" -d'{"user_id":"admin","role":"admin"}' | jq -r .token)

echo"== EMP tools ==";curl-s http://localhost:8000/v1/agent/tools-H"Authorization: Bearer${TOKEN_EMP}" | jq'.role,.visibility, (.tools[]?.full_name)'
echo"== ADMIN tools ==";curl-s http://localhost:8000/v1/agent/tools-H"Authorization: Bearer${TOKEN_ADMIN}" | jq'.role,.visibility, (.tools[]?.full_name)'

curl-i-s-X POST http://localhost:8000/tools/call \
-H"Authorization: Bearer${TOKEN_EMP}"-H"Content-Type: application/json" \
-d'{"server":"mcp_admin","tool_name":"admin.rotate_key","args":{}}' |sed-n'1,80p'

curl-i-s-X POST http://localhost:8000/tools/call \
-H"Authorization: Bearer${TOKEN_ADMIN}"-H"Content-Type: application/json" \
-d'{"server":"mcp_admin","tool_name":"admin.rotate_key","args":{}}' |sed-n'1,80p'
```

## Pass criteria

- employee 看不到 `mcp_admin.*`
- employee call admin tool → **403**（`forbidden_by_policy`）
- admin call admin tool → **200**

---

# ✅ 目標2：Low-code 封裝（Langflow → Gateway）

## 測試目的

驗證 Langflow（低碼端）能在容器內透過 REST 呼叫 Gateway：先 login 拿 token，再 tools/call 成功回 200 + JSON + correlation_id。

## 驗收指令（Langflow 容器內）

```
docker compose exec langflowsh-lc'
python - << "PY"
import json, urllib.request
login_data=json.dumps({"user_id":"admin","role":"admin"}).encode("utf-8")
login_req=urllib.request.Request("http://172.20.0.10:8000/auth/login",data=login_data,headers={"Content-Type":"application/json"})
with urllib.request.urlopen(login_req,timeout=8) as r:
    token=json.loads(r.read().decode())["token"]
print("token_len=",len(token))

payload={"server":"mcp_public","tool_name":"public.echo","args":{"text":"hello"}}
data=json.dumps(payload).encode("utf-8")
req=urllib.request.Request("http://172.20.0.10:8000/tools/call",data=data,headers={"Authorization":f"Bearer {token}","Content-Type":"application/json"})
with urllib.request.urlopen(req,timeout=8) as r:
    print("status",r.status)
    print(r.read().decode("utf-8","ignore"))
PY
'
```

## Pass criteria

- `token_len > 0`
- `/tools/call` 回 **200** 且 JSON `ok=true`
- 回應包含 `correlation_id`

---

# ✅ 目標3：MCP 強化（CID / validation / allowlist / 統一錯誤）

## 測試目的

驗證平台級封裝：端到端可追蹤（CID）、入口 validation（422）、敏感能力 allowlist（ok:false + error.code）。

## 驗收指令

### (A) CID trace

```
TOKEN_ADMIN=$(curl -s -X POST http://localhost:8000/auth/login -H"Content-Type: application/json" -d'{"user_id":"admin","role":"admin"}' | jq -r .token | tr -d'\r\n')

CID=$(curl -i -s -X POST http://localhost:8000/tools/call \
  -H"Authorization: Bearer${TOKEN_ADMIN}" -H"Content-Type: application/json" \
  -d'{"server":"mcp_public","tool_name":"public.echo","args":{"text":"hello"}}' \
  | awk -F': ''tolower($1)=="x-correlation-id"{print $2}' | tr -d'\r')

echo"CID=$CID"
docker compose logs gateway--tail=200 |grep-n"$CID" ||true
docker compose logs mcp_public--tail=200 |grep-n"$CID" ||true
```

### (B) validation 422（缺 tool_name）

```
curl-i-s-X POST http://localhost:8000/tools/call \
-H"Authorization: Bearer${TOKEN_ADMIN}"-H"Content-Type: application/json" \
-d'{"server":"mcp_public","args":{"text":"hello"}}' |sed-n'1,80p'
```

### (C) allowlist / 統一錯誤

```
curl-s-X POST http://localhost:8000/tools/call \
-H"Authorization: Bearer${TOKEN_ADMIN}"-H"Content-Type: application/json" \
-d'{"server":"mcp_internal","tool_name":"internal.query_sqlite","args":{"query_id":"NOT_IN_ALLOWLIST"}}' | jq
```

## Pass criteria

- CID 可在 gateway/mcp_public logs 同時命中
- 缺欄位回 422
- allowlist 拒絕回 `ok:false` 且 `error.code=query_id_not_allowed`

---

# ✅ 目標4：冷啟動與狀態管理（Stateful + TTL + upstream_down + budgets）

> **目標4重點不是模型強弱，而是穩定性**：可用性、可觀測性、可控性、狀態管理。
> 

## 重要設定（方案A：不改 env/compose）

由於 LiteLLM 有 **key→model allowlist**，為避免 `key_model_access_denied`，本專案在目標4驗收時採方案A：

✅ **每次 /chat 明確指定允許的 model 字串**（完全一致）：

- `/models/Qwen3-30B-A3B-Instruct-2507-FP8`

---

## 4A) deny（403）

此項可直接引用目標1 employee 403 證據（不需重跑）。

---

## 4B) Stateful 記憶 + TTL（PASS）

### 驗收指令

```
TOKEN_ADMIN=$(curl -s -X POST http://localhost:8000/auth/login -H"Content-Type: application/json" -d'{"user_id":"admin","role":"admin"}' | jq -r .token | tr -d'\r\n')

# write
curl-s-X POST http://localhost:8000/chat \
-H"Authorization: Bearer${TOKEN_ADMIN}"-H"Content-Type: application/json" \
-d'{"conversation_id":"hi-1","model":"/models/Qwen3-30B-A3B-Instruct-2507-FP8","message":"我叫浩哥"}' | jq

# recall
curl-s-X POST http://localhost:8000/chat \
-H"Authorization: Bearer${TOKEN_ADMIN}"-H"Content-Type: application/json" \
-d'{"conversation_id":"hi-1","model":"/models/Qwen3-30B-A3B-Instruct-2507-FP8","message":"我叫什麼？"}' | jq

# TTL evidence
docker compose exec redis redis-cli TTL"memprof:admin:hi-1"
docker compose exec redis redis-cli HGETALL"memprof:admin:hi-1"
```

### Pass criteria

- write 回應含 `memory.saved=true` 且 name=浩哥
- recall 回應含 `memory.hit=true` 且回答「你叫浩哥」
- Redis TTL 回 **正數**

---

## 4C) upstream_down（502）

### 驗收指令

```
docker composestop litellm

curl-i-s-X POST http://localhost:8000/chat \
-H"Authorization: Bearer${TOKEN_ADMIN}"-H"Content-Type: application/json" \
-d'{"conversation_id":"u-down-1","model":"/models/Qwen3-30B-A3B-Instruct-2507-FP8","message":"hi"}' \
|sed-n'1,140p'

docker composestart litellm
```

### Pass criteria

- 回 **502**
- JSON `ok:false` 且 `error.code=upstream_down`
- header 有 `x-correlation-id`

---

## 4D) budgets（429）

> 建議最後再做，因為觸發後可能會「黏住」。
> 

### 驗收指令

```
BIG=$(python - <<'PY'
print("x"*50000)
PY
)

curl-i-s-X POST http://localhost:8000/v1/agent/run \
-H"Authorization: Bearer${TOKEN_ADMIN}"-H"Content-Type: application/json" \
-d"$(jq -nc --arg msg"$BIG"'{conversation_id:"budget-1", model:"/models/Qwen3-30B-A3B-Instruct-2507-FP8", message:$msg, max_steps:1}')" \
|sed-n'1,160p'
```

### Pass criteria

- 回 **429**
- JSON `ok:false` 且 `error.code=budget_exceeded` / `daily_budget_exceeded`
- header 有 `x-correlation-id`

---

## 踩坑總整理（Troubleshooting / Lessons Learned）

### 1) `.env` 改了但容器內 `os.getenv()` 是 None

- 根因：compose 變數替換 ≠ 容器環境變數注入
- 檢查：

```
docker compose exec gatewaysh-lc'python -c "import os; print(os.getenv(\"BUDGET_DAILY_CHARS\"))"'
```

### 2) Budgets 429 會黏住（改回大值仍 429）

- 根因：budget 是 Redis 每日累積 key（例如 `budget:admin:YYYYMMDD`）
- 解法：刪當日 key（或換 user_id）：

```
docker compose exec redis redis-cli--scan--pattern"budget:admin:*"
docker compose exec redis redis-cli DEL"budget:admin:YYYYMMDD"
```

### 3) 401 invalid_token

- 根因：重啟/重建後 JWT secret 變動，舊 token 作廢
- 解法：驗收前重新 `/auth/login` 取 token

### 4) TTL -2 / -1 誤判

- `2`：key 不存在；`1`：永不過期
- 做法：先 scan 再查 TTL：

```
docker compose exec redis redis-cli--scan--pattern"memprof:*:hi-1"
docker compose exec redis redis-cli TTL"memprof:admin:hi-1"
```

### 5) `key_model_access_denied`

- 根因：LiteLLM key 有 model allowlist，model 字串需完全一致
- 解法：目標4採方案A：/chat 固定帶 `model="/models/Qwen3-30B-A3B-Instruct-2507-FP8"`

### 6) upstream_down 的類型要分類（避免誤判）

- gateway→litellm 連不通（litellm 未 ready / 停止）
- litellm→upstream 連不通（上游過載/網路）
- 本專案要求：回 502 + error.code + CID（可觀測）

---

## 設計思路（Why this design）

- **RBAC = visibility + final defense**：只隱藏工具不夠，必須在 gateway policy 層阻擋越權呼叫
- **統一錯誤封裝**：前端與監控可依 `error.code` 分類處理（forbidden/upstream_down/budget_exceeded…）
- **CID 端到端**：同一請求可串起 gateway/mcp/litellm logs，提高可維運性
- **目標4拆子驗收**：上游不穩是常態，因此用 stateful/TTL/budget/upstream_down 分拆驗收，確保可重現與可交付

---

## 已知限制與止損（Limitations）

- 上游（免 key）可能過載或不穩 → 以 `budgets(429)` + `upstream_down(502)` + `mock_upstream` 做止損與可重現驗收
- 長對話摘要品質不作為硬性評分點，重點放在「狀態與控制機制可驗收」