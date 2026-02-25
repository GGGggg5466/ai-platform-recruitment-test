# AI Platform Recruitment Test（Monorepo）

本專案為「AI 平台團隊招募測試任務」之交付內容，採 **monorepo** 形式整理三個模組（02/03/04），以利 reviewer 在同一個 repo 內快速瀏覽與驗收。

---

## Repo 結構

> 以資料夾序號對應題目模組（建議 reviewer 從 02 → 03 → 04 依序閱讀）

├── 02-idp-pipeline/ # 資料工程流水線（IDP Pipeline）
├── 03-agent-platform/ # Agent 平台（Gateway + MCP Servers）
├── 04-ai-safety-quality/ # AI 安全性與品質監控（Safety/Quality）
├── .gitignore
└── README.md


---

## 環境與執行方式（共通）

- 開發/執行環境：**WSL2 (Ubuntu) + Docker + Docker Compose**
- 操作方式：使用終端機執行 `docker compose`、`bash scripts/*.sh`、`curl` 測試
- 每個模組均提供自己的 `README.md`（含啟動與驗收步驟）

> 若你只想「快速驗收」：請直接進入各模組資料夾並照該模組 README 操作即可。

---

## 模組一覽與快速入口

### 02 — 資料工程流水線（IDP Pipeline）
**目標概述**
- 將文件/圖片/（可能包含 PDF）輸入進行處理與抽取
- 產出結構化結果（含處理流程/血緣 lineage 等資訊）
- 連接持久化元件（例如向量庫/圖資料庫）以支援後續檢索與追蹤

**快速入口**
- 位置：`02-idp-pipeline/`
- 驗收：請見 `02-idp-pipeline/README.md`

---

### 03 — Agent 平台（Gateway + MCP Servers）
**目標概述**
- 以 Gateway 作為統一入口，依權限/策略進行工具呼叫與流量控制
- 整合 MCP servers（admin/internal/public…）提供可控的工具能力
- 支援 Langflow / LiteLLM 相關設定與測試腳本

**快速入口**
- 位置：`03-agent-platform/`
- 驗收：請見 `03-agent-platform/README.md`（常用腳本：`scripts/test_full.sh`）

---

### 04 — AI 安全性與品質監控（Safety / Quality）
**目標概述**
- 針對 Prompt Injection / Safety probes 等風險做可驗收測試
- 產出評估結果（報告 / artifacts），用於安全性與品質的驗證與追蹤
- 以「能重現、可驗收」為主，不將大量工具輸出納入版控

**快速入口**
- 位置：`04-ai-safety-quality/`
- 驗收：請見 `04-ai-safety-quality/README.md`

---

## 版控策略（重要）

本 repo 僅提交「可重現執行所需的程式與設定」，以下類型**不納入版控**：

- `.env` / secrets（僅保留 `.env.example`）
- runtime artifacts（例如：資料庫 volume、job 輸出、評估工具輸出）
- cache / logs（`__pycache__`、`*.pyc`、tool caches）
- Windows `*:Zone.Identifier` 類檔案

相關規則已整合於根目錄 `.gitignore`。

---

## 如何驗收（總覽）

1. 進入模組資料夾（02/03/04）
2. 依各模組 `README.md` 啟動服務（通常為 `docker compose up -d` 或 scripts）
3. 依 README 執行測試腳本 / curl 驗證
4. 觀察輸出與 artifacts（以各模組 README 的驗收標準為準）

---

## 交付說明

- 本 repo 以「最小可驗收」為原則整理，優先確保 reviewer 能快速啟動與重現結果
- 若需查看實作細節與測試方式，請直接閱讀各模組 README 與 scripts
