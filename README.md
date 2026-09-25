# Knowledge Graph Notes · 知识图谱笔记系统

> **English intro**: A local-first knowledge graph note-taking system built with Vue 3 + D3.js + FastAPI. Upload notes, auto-extract knowledge points, verify them with a 4-way evidence engine (KB consistency / graph / text rules / web search), build cross-file semantic links with a 4-dimensional scoring model, and export summaries to Markdown / Word / PPT. Includes an admin console, personal profile, Mermaid flowcharts and AI-readable digests.
>
> **中文简介**: 本地优先的知识图谱笔记系统。上传笔记 → 智能切割 → 自动抽取知识点 → 四路证据智能判定（知识库/图谱/规则/联网）→ 四维融合打分建立跨文件语义关联 → 一键导出 Markdown/Word/PPT 学习总结。内置后台管理与个人主页。

---

# English

## Overview

**Knowledge Graph Notes** turns your scattered Markdown/text notes into an interactive knowledge graph:

- **Smart split & extraction** — large files are cut at structural boundaries (headings/paragraphs) so no sentence is broken; each knowledge point keeps its heading context and line-number traceability
- **Knowledge point verdict engine** — every extracted point enters a candidate pool and is scored by 4 weighted evidence sources: knowledge-base consistency, graph evidence, text-quality rules, and zero-config web verification (Bing/Sogou/360/Baidu). Score ≥ 0.80 auto-accept, < 0.35 reject, otherwise queued for human review in the admin console
- **4-dimensional link scoring** — `Score = α·text + β·vector + γ·corpus + δ·topology` (default 0.1 / 0.5 / 0.3 / 0.1), live-tunable sliders in the UI
- **Knowledge-base driven relations** — domain corpora (software / embedded / writing) act as the authority source; relations are decided by the KB concept space, not just keyword overlap
- **Zero orphan nodes** — orphan nodes are forcibly adopted via semantic bridging against top PageRank nodes
- **Graph summary & export** — structural summary (levels / domains / hubs / clusters / **learning paths**) → Mermaid flowchart (AI-readable, dashed = KB bridge) → AI digest → export to **Markdown / Word / PPT / Mermaid / JSON**
- **Admin & profile** — password-protected admin console (candidate review with full evidence chain, operation audit trail), personal profile with server-side avatar & background upload
- **Learning toolkit** — local subgraph (1-3 hop BFS), network analytics dashboard (degree / betweenness / PageRank / connected components), smart connection recommendations, `[[wikilinks]]`, graph filters, plugin system, spaced-repetition review, Q&A, timeline

## Tech Stack

| Layer | Tech |
|---|---|
| Desktop shell | Electron (IPC / contextBridge / webContents interception) |
| Frontend | Vue 3 `<script setup>` · Vite 5 · Pinia · D3 v7 · Element Plus · @vueuse/core · Mermaid (dynamic import) |
| Backend | Python FastAPI · SQLAlchemy · SQLite · python-pptx · python-docx |
| Algorithms | Cosine similarity · 4-dim weighted scoring · Union-Find · PageRank · Brandes betweenness · BFS shortest path · spaced repetition |

## Project Structure

```
YR/
├── backend/                # FastAPI backend
│   ├── app/
│   │   ├── api/            # files / knowledge / graph / notes / kb / summary / admin / profile
│   │   ├── services/       # parser / vector_engine / inference / validator / kb_* /
│   │   │                   # file_splitter / knowledge_verifier / web_probe / audit / graph_summary / summary_export
│   │   ├── models/         # 13 ORM tables (incl. candidates / audit_logs / user_profiles)
│   │   ├── config.py / database.py / main.py / seed.py
│   │   └── scripts/        # kb_build.py (--reparse/--sync-corpus/--understand), graph_summary.py
│   ├── requirements.txt
│   └── .env.example        # config template (copy to .env; .env is NOT uploaded)
├── kg-vue3/                # Vue 3 frontend
│   ├── src/
│   │   ├── components/     # GraphCanvas / KnowledgeWorkbench / AdminView / ProfileView /
│   │   │                   # GraphSummaryView / KnowledgeBaseView / MermaidFlow ...
│   │   ├── store/          # graphStore / fileStore / kbStore / summaryStore / noteStore ...
│   │   ├── api/            # fileAPI / knowledgeAPI / graphAPI / noteAPI / kbAPI / summaryAPI / profileAPI / adminAPI
│   │   ├── services/ utils/ plugins/ styles/ domain_corpus/
│   │   └── App.vue
│   ├── package.json
│   └── vite.config.js
├── domain_corpus/          # KB corpora (software.md / embedded.md / writing.md / manifest.json)
├── test_data/              # samples (doc_A~E + kb_demo + summary_examples)
├── app.js / index.html / styles.css / main.js / preload.js   # Electron desktop app
├── server.js               # local static server
├── 启动服务.bat / 知识图谱.bat
└── docker-compose.yml      # one-click deploy (frontend + backend)
```

## Quick Start

### Local dev
```bash
# 1. Backend (port 8080)
cd backend
pip install -r requirements.txt
cp .env.example .env        # adjust ADMIN_TOKEN etc.
py -m uvicorn app.main:app --port 8080

# 2. Frontend (port 5173)
cd kg-vue3
npm install
npm run dev
# open http://localhost:5173
```

### Electron desktop
```bash
npm install
npm start
```

### Docker
```bash
docker compose up -d
```

## Configuration (`.env`)

| Key | Default | Description |
|---|---|---|
| `ADMIN_TOKEN` | `kg-admin` | Admin console password (**change it!**) |
| `MAX_UPLOAD_MB_HARD` | `100` | Max upload size (MB) |
| `SPLIT_TARGET_LINES` | `6000` | Target lines per split piece |
| `MAX_NODES_PER_FILE_TOTAL` | `3000` | Max knowledge points per file after split |
| `VERDICT_USE_WEB` | `true` | Enable web verification |
| `VERDICT_MAX_WEB_CALLS` | `30` | Max web calls per verdict batch |
| `UPLOAD_DIR` | `./uploads` | Avatar / background storage dir |

## License

AGPL-style open source (adjust as needed). See source for details.

---

---

# 中文

## 项目简介

**知识图谱笔记系统**把你的散落笔记变成可交互的知识图谱：

- **智能切割与抽取** — 大文件在标题/段落结构边界落刀（不切断句子），每个知识点保留标题上下文与行号可追溯
- **知识点智能判定** — 抽取先入候选池，四路证据加权打分：知识库一致性 / 图谱证据 / 文本质量规则 / 零配置联网验证（Bing/搜狗/360/百度）。≥0.80 自动采纳，<0.35 驳回，其余进后台人工裁决
- **四维融合关联打分** — `Score = α·文本 + β·向量 + γ·语料 + δ·拓扑`（默认 0.1/0.5/0.3/0.1），界面实时可调
- **知识库驱动关联** — 领域语料（软件/嵌入式/写作）是知识权威源，关联由知识库概念空间决定，而非纯关键词重合
- **零孤立节点** — 孤儿节点强制与 PageRank Top5 中最相似的节点建"潜在语义桥接"
- **图谱总结与导出** — 结构总结（层级/领域/枢纽/知识簇/**学习主线**）→ Mermaid 流程图（AI 可读，虚线=知识库桥接）→ AI 摘要 → 导出 **Markdown / Word / PPT / Mermaid / JSON**
- **后台管理与个人主页** — 口令保护的后台（候选审阅含完整证据链、操作审计台账）、服务端头像/背景图上传
- **学习增强套件** — 局部图谱（1-3 跳 BFS）、网络分析仪表盘（度中心度/介数/PageRank/连通分量）、智能连接推荐、`[[双向链接]]`、图谱筛选、插件系统、间隔重复回顾、知识问答、时间线

## 快速开始

```bash
# 1. 后端（端口 8080）
cd backend
pip install -r requirements.txt
cp .env.example .env        # 按需修改 ADMIN_TOKEN
py -m uvicorn app.main:app --port 8080

# 2. 前端（端口 5173）
cd kg-vue3
npm install
npm run dev
# 浏览器打开 http://localhost:5173
```

- **Electron 桌面版**：`npm install && npm start`
- **Windows 一键启动**：双击 `启动服务.bat` / `知识图谱.bat`
- **Docker 部署**：`docker compose up -d`

## 详细文档

| 文档 | 内容 |
|---|---|
| `技术栈与功能实现清单.md` | 三层全量实现清单（含 F1-F6 / P1-P3 增强功能） |
| `智能切割与知识点判定说明.md` | 切割算法、四路判定、后台管理、个人主页 |
| `图谱总结与导出说明.md` | 总结维度、Mermaid 流程图、AI 摘要、6 种导出格式 |
| `大文件上传保护说明.md` | 四层防崩溃方案与配置 |
| `知识库设计说明.md` | 知识库数据模型与关联算法 |
