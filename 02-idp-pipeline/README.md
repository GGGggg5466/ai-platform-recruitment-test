# Intelligent Document Processing（IDP）非同步流水線 API（IDP S+ Blueprint）

> 目標：把 **PDF / 圖片** 等非結構化資料，透過 **Docling / OCR（EasyOCR 類）/ VLM（Gemma 3 類）** 的抽取流程，輸出 **Markdown / JSON**，並自動 **切塊（Chunks）→ 向量化 → 入庫（Qdrant）**，同時把文件/段落關係寫入 **Neo4j** 以支援 GraphRAG。  
> 本專案採 **非同步 Jobs API**（Redis + RQ worker），並提供 **動態路由**、**韌性（timeout/fallback）** 與 **資料血緣（lineage）** 可驗收證據。

---

## 0. 本專案亮點

### ✅ 1) 流水線邏輯：複雜表格/圖表的動態切換 OCR ↔ VLM
- 支援 `route=ocr / route=vlm / route=auto`
- `route=vlm` 時：
  - **先嘗試 VLM 抽取**
  - 若 **timeout / upstream 失敗** → **自動 fallback OCR/Docling 保底**
- 資料血緣（`lineage.json`）會記錄事件鏈（可驗收）：
  - `VLM_EXTRACT_BEGIN/DONE`  
  - 或 `VLM_EXTRACT_BEGIN/ERROR → OCR_EXTRACT_BEGIN/DONE`

## ✅ 本次更新重點（Day6：真寫入 Qdrant / Neo4j + 可驗收證據）

本版本已把「向量庫 / 圖譜庫」從 *mock/占位* 轉為 **真正寫入**（最小改動、維持既有 API/Worker 架構不翻新）：

- **Qdrant（向量資料庫）**：Worker 在 `QDRANT_UPSERT_BEGIN/DONE` 後，會將 `chunks` 對應的 `vector + payload` **upsert 到 collection `idp_chunks`**。
- **Neo4j（圖譜資料庫）**：Worker 在 `NEO4J_WRITE_BEGIN/DONE` 後，會寫入
  - `(:Document {id: <job_id>})`
  - `(:Chunk {id: <job_id>::c<i>, chunk_id: "c<i>", text: ...})`
  - `(:Document)-[:HAS_CHUNK]->(:Chunk)`  
  以建立 GraphRAG 的最小圖譜基礎。
- **Artifacts / Lineage**：每個 job 都會在 `data/jobs/<job_id>/` 產出 `result.json / result.md / lineage.json / quality.json`，並且 API 會回傳這些檔案路徑供追溯。

> 補充：若你用 `route=vlm` 強制走 VLM，但 upstream 失敗，系統會 **fallback 到 OCR**，並在 `route_trace` 與 `lineage.json` 中留完整事件鏈（含 pages）。

### ✅ 2) 向量與圖譜整合：Qdrant + Neo4j（GraphRAG 基礎）
- 抽取後：`chunk → embed → upsert Qdrant`
- 同步：`write Neo4j` 建立 `Document / Chunk` 關係（GraphRAG 索引基礎）
- API 回應會回傳：
  - `stores.qdrant.collection + point_ids`
  - `stores.neo4j.doc_node_id + chunk_node_ids`

> 註：此作業骨架已介面化 Store；若實作環境未啟動真實 Qdrant/Neo4j，仍可回傳 mock ids 以完成可驗收流程。

### ✅ 3) API 性能/後壓/水平擴展（Docker）
- **非同步**：`POST /v1/jobs` 立即回 `job_id`（不阻塞 API）
- **後壓**：Redis queue 作為緩衝
- **水平擴展**：`docker compose up -d --scale worker=3`

### ✅ 4) 資料血緣（Lineage）
- 每個 job 產生 `data/jobs/<job_id>/lineage.json`
- 記錄：抽取路由、錯誤、fallback、chunks、embeddings、stores 等 stage-level 事件

---

## 1. 系統架構與資料流

### 1.1 高階流程（非同步）
```mermaid
flowchart LR
  U[Client] -->|POST /v1/jobs| API[FastAPI]
  API -->|enqueue job| R[Redis Queue (RQ)]
  W1[Worker] -->|dequeue| R
  W1 -->|extract OCR/VLM| P[Pipeline]
  P -->|chunk| C[Chunks]
  P -->|embed| E[Embeddings]
  E --> Q[Qdrant]
  C --> G[Neo4j]
  W1 -->|write artifacts| D[(./data/jobs/<job_id>)]
  API -->|GET /v1/jobs/{id}| U
  API -->|read result/artifacts| D
```

### 1.2 路由決策（route=vlm 的 failover）
```mermaid
flowchart TD
  A[route=vlm & PDF] --> B[計算 pages (pypdf)]
  B --> C[VLM_EXTRACT_BEGIN(pages)]
  C --> D{VLM 成功?}
  D -->|Yes| E[VLM_EXTRACT_DONE(pages)]
  D -->|No (timeout)| F[VLM_EXTRACT_ERROR(pages)]
  F --> G[OCR_EXTRACT_BEGIN(pages, reason=vlm_failed_fallback)]
  G --> H[OCR_EXTRACT_DONE(pages)]
  E --> I[chunk/embed/store]
  H --> I
```

---

## 2. 專案結構（File Tree）

```text
idp_splus_blueprint/
├── app/
│   ├── api.py                  # /v1/jobs endpoints
│   ├── main.py                 # FastAPI app entry
│   ├── worker.py               # RQ worker entrypoint
│   ├── worker_tasks.py         # pipeline 主流程（extract→chunk→embed→store→artifacts）
│   └── ... (core/pipelines/stores 等)
├── tests/
│   ├── test_quality.py
│   ├── test_routing.py
│   └── test_resilience.py
├── sample/
│   ├── sample.pdf
│   ├── scan.png
│   └── chart.png
├── scripts/
│   └── demo.sh
├── data/                       # runtime 產物（jobs artifacts）
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
└── README.md
```

---

## 3. 環境需求

- 平台：WSL2 / Linux 
- Docker + Docker Compose
- 工具：`curl`、`jq`

> 注意：本專案將 `./data` 掛載進容器 `/app/data`，所有 job 產物都會落在本機 `./data/jobs/<job_id>/`。

---

## 4. 一鍵啟動

```bash
docker compose up -d --build
docker compose ps
```

- API：`http://localhost:8081`（compose 將 container 8080 映射到 host 8081）
- Redis：`6379`

### 4.1 服務可用性（取代 /health）
本專案沒有提供 `/health`，所以健康檢查以 FastAPI 內建 OpenAPI 為準：

```bash
curl -s -o /dev/null -w "HTTP=%{http_code}\n" http://localhost:8081/docs
curl -s -o /dev/null -w "HTTP=%{http_code}\n" http://localhost:8081/openapi.json
curl -s http://localhost:8081/openapi.json | jq -r '.paths | keys[]' | head -n 30
```

你會看到：
- `/docs`、`/openapi.json` 回 `HTTP=200`
- routes 含 `/v1/jobs`、`/v1/jobs/{job_id}`

---

## 5. 核心 API 使用方式

### 5.1 送出 Job（PDF/圖片）
```bash
JOB=$(curl -s -X POST "http://localhost:8081/v1/jobs"   -F "file=@sample/sample.pdf;filename=sample.pdf"   -F "route=vlm" | jq -r .job_id)

echo "JOB=$JOB"
```

支援的 `route`：
- `ocr`：強制 OCR
- `vlm`：強制 VLM（失敗自動 fallback OCR）
- `auto`：先 OCR baseline，再依品質 gate 決定是否走 VLM（簡化版）

### 5.2 查詢狀態與結果
```bash
curl -s "http://localhost:8081/v1/jobs/$JOB" | jq
```

重點欄位：
- `status`：`queued/running/finished`
- `chosen_route`：最終採用的路由（`ocr/vlm`）
- `route_trace[]`：每一步嘗試、是否成功與原因（含 `upstream_failed_or_timeout`、`vlm_failed_fallback`）
- `stores`：Qdrant/Neo4j references
- `artifacts`：結果與血緣檔案路徑

---

## 6. Artifacts（產物）與資料血緣（Lineage）

每個 job 會產生：

```text
data/jobs/<job_id>/
├── result.json        # API 回應的完整快照（含 route_trace/stores/artifacts）
├── result.md          # 抽取後 Markdown（此骨架以 text 形式輸出）
├── lineage.json       # 事件流（驗收重點）
└── quality.json       # 品質評分與理由碼
```

### 6.1 事件鏈快速查看
```bash
jq -r '.events[].name' data/jobs/$JOB/lineage.json | head -n 80
```

### 6.2 D2
```bash
jq -r '.events[]
  | select(.name|test("EXTRACT|CHUNK|EMBED|QDRANT|NEO4J|STORE|DONE|ERROR"))
  | "\(.name)\tkind=\(.meta.kind // "-")\tpages=\(.meta.pages // "-")\treason=\(.meta.reason // "-")\terr=\(.meta.error // "-")"
' data/jobs/$JOB/lineage.json
```

---

## 7. 最終驗收

### A) 流水線邏輯：VLM 成功（pages 必須存在）
```bash
JOB_VLM=$(curl -s -X POST "http://localhost:8081/v1/jobs"   -F "file=@sample/sample.pdf;filename=sample.pdf"   -F "route=vlm" | jq -r .job_id)

jq -r '.events[]
  | select(.name=="VLM_EXTRACT_BEGIN" or .name=="VLM_EXTRACT_DONE")
  | "\(.name)\tkind=\(.meta.kind)\tpages=\(.meta.pages)"
' data/jobs/$JOB_VLM/lineage.json
```

預期輸出（示意）：
- `VLM_EXTRACT_BEGIN kind=pdf pages=4`
- `VLM_EXTRACT_DONE ... pages=4`

---

### B) 最後大魔王：VLM timeout → OCR fallback（pages 必須一致）
此驗收會用 **timeout=1 秒** 人為製造 VLM 失敗，觀察自動 fallback 的證據鏈。

#### B1) 把 upstream timeout 調成 1 秒（僅用於驗收）
修改 `docker-compose.yml`：
- 將 `UPSTREAM_TIMEOUT_S=30` 改為 `UPSTREAM_TIMEOUT_S=1`（**api 與 worker 都改**）

重啟：
```bash
docker compose down
docker compose up -d --scale worker=3
docker compose ps
```

#### B2) 送 job 並驗收事件鏈
```bash
JOB_FB=$(curl -s -X POST "http://localhost:8081/v1/jobs"   -F "file=@sample/sample.pdf;filename=sample.pdf"   -F "route=vlm" | jq -r .job_id)

curl -s "http://localhost:8081/v1/jobs/$JOB_FB" | jq '.chosen_route, .route_trace'

jq -r '.events[]
  | select(.name=="VLM_EXTRACT_BEGIN" or .name=="VLM_EXTRACT_ERROR" or .name=="OCR_EXTRACT_BEGIN" or .name=="OCR_EXTRACT_DONE")
  | "\(.name)\tkind=\(.meta.kind)\tpages=\(.meta.pages // "-")\treason=\(.meta.reason // "-")\terr=\(.meta.error // "-")"
' data/jobs/$JOB_FB/lineage.json
```

預期輸出（示意，與實測一致）：
- `VLM_EXTRACT_BEGIN kind=pdf pages=4`
- `VLM_EXTRACT_ERROR kind=pdf pages=4 err=... timed out`
- `OCR_EXTRACT_BEGIN kind=pdf pages=4 reason=vlm_failed_fallback`
- `OCR_EXTRACT_DONE kind=pdf pages=4`

> ✅ 這段就是「動態切換」的最強證據：  
> **VLM 失敗也能追 pages，且 fallback OCR 的 pages 與原 PDF 一致。**

#### B3) 驗收完記得改回 timeout（避免 demo 永遠 timeout）
把 `UPSTREAM_TIMEOUT_S` 改回 `30`，再：
```bash
docker compose up -d --force-recreate api worker
```

---

### C) 向量與圖譜整合（Qdrant + Neo4j references）
直接看 API 回應的 `stores`：
```bash
curl -s "http://localhost:8081/v1/jobs/$JOB_VLM" | jq '.stores'
```

你要在報告描述：
- chunks 向量已入庫（`qdrant.collection` + `point_ids`）
- 文件與 chunk 節點已建立（`neo4j.doc_node_id` + `chunk_node_ids`）

---

### D) API 性能/後壓/水平擴展（worker scale-out）
```bash
docker compose up -d --scale worker=3
docker compose ps
```

報告重點：
- API 立即回 `job_id`（非同步）
- Redis queue 緩衝（backpressure）
- worker 可水平擴展提升吞吐

---

## 8. 靜態測試（pytest）

```bash
docker compose exec api pytest
```

測試涵蓋：
- 品質評分與品質 gate（quality）
- 路由決策（routing）
- 韌性策略（resilience：retry/backoff/circuit breaker 行為）

---

## 9. 常見坑與排錯

### 9.1 `pages=null`（lineage 沒有 pages）
**症狀：**
- `jq` 查 `.meta.pages` 顯示 `null`

**原因：**
- `pypdf` 未安裝，`get_pdf_pages_safe()` 會回 `None`

**確認：**
```bash
docker compose exec worker python -c "import pypdf; print('pypdf OK', pypdf.__version__)"
```

**修正：**
- 在 `pyproject.toml` 加上 `pypdf>=4.0.0`（注意 TOML array 的逗號）
- 或在 `Dockerfile` 的 `CMD` 之前加：
  - `RUN python -m pip install --no-cache-dir pypdf>=4.0.0`

重建：
```bash
docker compose down
docker compose build --no-cache worker
docker compose up -d
```

---

### 9.2 `TOMLDecodeError: Unclosed array`（pyproject.toml 壞掉）
**症狀：**
- `docker compose build` 失敗
- 或本機跑：
```bash
python -c "import tomllib, pathlib; tomllib.loads(pathlib.Path('pyproject.toml').read_text('utf-8')); print('pyproject OK')"
```
出現 `Unclosed array`

**原因：**
- `dependencies = [ ... ]` 少逗號（`,`）導致 TOML array 沒關閉

**修正：**
- 補齊缺少的 `,`（尤其是新增依賴時最常漏）

---

### 9.3 `/health` 回 `{"detail":"Not Found"}`
**原因：**
- 本專案沒有 `/health` endpoint

**替代驗收：**
- 用 `/docs`、`/openapi.json`（HTTP 200）作為健康檢查

---

### 9.4 `jq: unexpected INVALID_CHARACTER`（jq 腳本炸掉）
**原因：**
- shell quoting（引號）錯誤（`"`、`\t` 混用）

**修正建議：**
- 外層用單引號包 jq 程式：`jq -r '...' file.json`
- 字串內用雙引號即可，不要過度跳脫

---

## 10. 我做了哪些關鍵改動

1) **補齊 PDF pages metadata**
- 新增 `get_pdf_pages_safe()`（使用 `pypdf.PdfReader`）
- `route=vlm` 且 `is_pdf` 時，在 `VLM_EXTRACT_BEGIN` / `VLM_EXTRACT_ERROR` / `OCR_EXTRACT_BEGIN/DONE` 都帶 `pages`

2) **統一 VLM DONE 的 schema**
- `emit_vlm_done()`：整理 upstream / retries / out_chars / pages，避免 meta 結構不一致

3) **可驗收的 failover（timeout → fallback OCR）**
- 以 `UPSTREAM_TIMEOUT_S=1` 模擬上游 timeout
- 驗收證據同時具備：
  - API `route_trace`（控制面）
  - lineage `events`（資料血緣）

---

## 11. License
作業/學術用途。


## 🧪 驗收：Qdrant 真寫入（向量資料庫）

### 測試目的
確認 Worker 會把 **chunks → embeddings → upsert** 寫入 Qdrant，並可從 Qdrant API 取回 payload（至少能證明「資料真的在向量庫」）。

### 測試方法與步驟（可直接貼到終端機）
> 假設你已經 `docker compose up -d`，且 API 在 `http://localhost:8081`

1) 送出一個 job（以 `sample/sample.pdf` 為例）：
```bash
JOB=$(curl -s -X POST "http://localhost:8081/v1/jobs"   -F "file=@sample/sample.pdf;filename=sample.pdf"   -F "route=vlm" | jq -r .job_id)
echo "JOB=$JOB"
```

2) 從 API 回傳中取出 Qdrant 的 collection 與 point id：
```bash
COL=$(curl -s "http://localhost:8081/v1/jobs/$JOB" | jq -r '.stores.qdrant.collection')
PID=$(curl -s "http://localhost:8081/v1/jobs/$JOB" | jq -r '.stores.qdrant.point_ids[0]')
echo "COL=$COL"
echo "PID=$PID"
```

3) 確認 Qdrant 已有 collection（至少看得到 `idp_chunks`）：
```bash
curl -s "http://localhost:6333/collections" | jq
```

4) 查 collection 狀態與 point 數量（有增長就是寫入證據之一）：
```bash
curl -s "http://localhost:6333/collections/$COL" | jq '.result.status, .result.points_count'
```

5) 取回「某個 point」的 payload（**這一步是最強證據**）  
> 注意：不同版本 Qdrant 的 API path 會不同；你這個環境中可用的是 `POST /collections/{name}/points`（會回傳 points）。
```bash
curl -s -X POST "http://localhost:6333/collections/$COL/points"   -H "Content-Type: application/json"   --data-raw "$(jq -nc --arg id "$PID" '{ids:[$id], with_payload:true, with_vector:false}')" | jq
```

### Pass Criteria（驗收標準）
- `GET /collections` 能看到 `idp_chunks`
- `GET /collections/idp_chunks` 的 `points_count` **≥ 1**
- `POST /collections/idp_chunks/points` 能回傳包含該 `id` 的 `payload`（例如 `chunk_id`, `text` 等欄位）

### 常見坑（你這次真的踩到）
- **Port 6333 已被占用**：你手動 `docker run -p 6333:6333 qdrant/qdrant` 會報 `port is already allocated`。  
  正確作法是：用 `docker compose ps` 找出已經在跑的 qdrant 容器，不要重複開第二個。
- **`/points/retrieve` 404**：這個是 API path 版本差異，不是你資料沒寫進去。  
  你目前環境用 `POST .../points` 是 OK 的（你已經成功取回 payload）。



## 🧪 驗收：Neo4j 寫入成功（GraphRAG 基礎）

### 測試目的
確認每個 job 除了寫入向量庫，也會同步寫入 Neo4j：
- `Document node`（doc_id = job_id）
- `Chunk nodes`（chunk_node_ids 至少 1 筆）
- `(:Document)-[:HAS_CHUNK]->(:Chunk)` 關聯存在  
以滿足 GraphRAG 後續的圖譜檢索/推理基礎。

### 測試方法與步驟
1) 從 API 取出 neo4j 寫入資訊：
```bash
curl -s "http://localhost:8081/v1/jobs/$JOB" | jq '.stores.neo4j'
```

2) 取得 doc_id / chunk_id（用 cypher-shell 驗證）：
```bash
DOC=$(curl -s "http://localhost:8081/v1/jobs/$JOB" | jq -r '.stores.neo4j.doc_node_id')
CID=$(curl -s "http://localhost:8081/v1/jobs/$JOB" | jq -r '.stores.neo4j.chunk_node_ids[0]')
echo "DOC=$DOC"
echo "CID=$CID"
```

3) 查 Document 是否存在：
```bash
docker compose exec neo4j cypher-shell -u neo4j -p password "MATCH (d:Document {id:'$DOC'}) RETURN d LIMIT 1;"
```

4) 查 Chunk 是否存在：
```bash
docker compose exec neo4j cypher-shell -u neo4j -p password "MATCH (c:Chunk {id:'$CID'}) RETURN c LIMIT 1;"
```

5) 查關聯（HAS_CHUNK）是否存在：
```bash
docker compose exec neo4j cypher-shell -u neo4j -p password "MATCH (d:Document {id:'$DOC'})-[:HAS_CHUNK]->(c:Chunk) RETURN count(c) as chunk_cnt;"
```

### Pass Criteria（驗收標準）
- `stores.neo4j.doc_node_id` 非空
- `stores.neo4j.chunk_node_ids` 至少 1 筆
- `MATCH ... RETURN ...` 查詢有結果（至少回 1 row）
- `chunk_cnt >= 1`

### 常見坑
- `service "neo4j" is not running`：代表 compose 沒有把 neo4j service 啟起來。  
  請先 `docker compose up -d`，並確認 `docker compose ps` 裡有 neo4j。



## 🧪 驗收：Artifacts / Lineage 完整產出（可追溯性）

### 五個檔案各代表什麼（報告必寫）
每個 job 都會在 `data/jobs/<job_id>/` 產出：

- `result.json`：**API 的完整回傳快照**（job_id/status/chosen_route/route_trace/stores/artifacts…）
- `result.md`：**最終抽取出的文本內容**（PDF/圖片經 VLM 或 OCR 後的文字）
- `lineage.json`：**資料血緣事件序列**（每個 stage 的 BEGIN/DONE/ERROR、pages、reason、error…）
- `quality.json`：**品質評分/診斷資訊**（如 OCR 品質 gate 的 score / signals / reason_codes）
- `meta.json`：**輸入檔與處理 metadata**（例如檔名、類型、大小、推測頁數等）

> 為什麼你看到 `quality.json` 常常是 `null`？  
> 因為目前設計是：**只有 `route=auto`（需要做 OCR 品質 gate）時才會產生 quality_report**。  
> 你在驗收多半用 `route=vlm` 或 `route=ocr`（強制路由），所以 `quality_report` 合理會是 `null`，但檔案仍會產出（內容為 `null`）。

### 測試方法與步驟
1) 從 API 取得 artifacts 路徑：
```bash
curl -s "http://localhost:8081/v1/jobs/$JOB" | jq '.artifacts'
```

2) 確認檔案實際存在：
```bash
ls -al data/jobs/$JOB/
```

3) 驗證 lineage 是否具備事件序列（BEGIN/DONE/ERROR/UPSERT/WRITE）：
```bash
jq -r '
  .events[]
  | select(.name|test("BEGIN|DONE|ERROR|UPSERT|WRITE"))
  | "\(.name)\tkind=\(.meta.kind // "-")\tpages=\(.meta.pages // "-")\treason=\(.meta.reason // "-")\terr=\(.meta.error // "-")"
' data/jobs/$JOB/lineage.json
```

### Pass Criteria（驗收標準）
- `artifacts.*_path` 皆非 null（至少 lineage/result/quality/meta 存在）
- `data/jobs/$JOB/` 目錄下檔案存在
- `lineage.json` 有完整事件鏈：例如 `..._BEGIN → ..._DONE`，若有失敗也要有 `..._ERROR`（可寫入報告當作可追溯性證據）

### 補充：result.md 為什麼看起來像「亂碼/16 進制」？
你用的 `sample.pdf` 本身是二進位檔；在某些 mock/簡化抽取路徑下，會把 bytes 以 `b'%PDF-...'` 的形式寫成字串，所以你會看到類似：
- `DOC: b'%PDF-1.5\n...'`

這不代表 pipeline 壞掉，而是代表：
- **這個 sample 內容並非「已抽出的自然語言」**，而是示範「流程可跑通 + 血緣可追溯 + 可寫入 DB」。
- 若要讓 `result.md` 變成可讀文字，你需要在抽取層（OCR/Docling/VLM）換成真正的 extractor（而不是 mock），或改用含可辨識文字的 PDF/圖片作測試。
