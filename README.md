# 知识图谱笔记系统（Knowledge Graph Notes）

基于语义向量 + 领域知识库的知识图谱笔记应用：多文件上传、智能切割、知识点抽取与判定、
跨文件语义关联、知识库推理溯源、图谱总结与导出（Word/PPT）、后台管理与个人主页，
支持桌面（Electron）/浏览器/后端服务三种形态。

---

## 一、系统架构（三层）

```
┌─────────────────────────────────────────────────────────────┐
│ 桌面壳（Electron）  app.js / main.js / preload.js            │
│   窗口管理 · IPC · webContents 拦截 · 本地文件双写           │
├─────────────────────────────────────────────────────────────┤
│ 前端（Vue 3 + Vite + Pinia + D3 v7 + Element Plus）         │
│   kg-vue3/src/                                              │
│   图谱渲染 · 知识工作台 · 知识库管理 · 图谱总结 · 后台 · 主页 │
├─────────────────────────────────────────────────────────────┤
│ 后端（FastAPI + SQLAlchemy + SQLite）                       │
│   backend/app/                                              │
│   文件解析 · 向量引擎 · 四维关联推理 · 智能判定 · 审计 · 导出│
└─────────────────────────────────────────────────────────────┘
```

## 二、核心功能

### 1. 多文件上传与智能切割
- 上传 `.md/.txt/.csv/.tsv/.json/.log`（硬上限 100MB，`.env` 可调）
- **智能切割**：只在标题/段落结构边界落刀（不切断句子），每片带祖先标题上下文，
  相邻片重叠 2 行防丢句，实测 1.14MB/16027 行文档切 3 片、1200 知识点零缺行
- 解析与采纳解耦：所有知识点先入**候选池**（含原文证据、行号、置信度），再判定

### 2. 知识点智能判定（四路证据加权）
| 证据 | 权重示例 |
|---|---|
| ① 知识库一致性（命中/定义一致/定义冲突） | +0.30 / +0.15 / **-0.25** |
| ② 图谱证据（被锚定/已有连线） | +0.10 / +0.05 |
| ③ 文本质量规则（标题形态/定义句式/长度） | +0.15 / -0.35 / +0.10 |
| ④ 联网证据（Bing/搜狗/360/百度，零配置抓取） | ≥2 命中 +0.15，未联网记 0 |

分级：`≥0.80 采纳` · `<0.35 驳回` · 其余**进后台人工裁决**；判定全程可溯源（证据链 JSON）。

### 3. 图谱关联（四维融合打分）
- `Score = α·Sim_text + β·Sim_vector + γ·Sim_corpus + δ·Sim_topology`
- 默认配比 w1=0.1 / w2=0.5 / w3=0.3 / w4=0.1，前端实时可调
- **知识库推理**（`domain_corpus/`）：软件/嵌入式/写作三份高密度关联语料，跨领域强连
- **零孤立节点**：孤儿节点强制收养（与 PageRank Top5 中最相似的建灰色"潜在语义桥接"）
- 悬浮连线显示溯源：来源类型 + 四项分数分解 + 原文证据片段

### 4. 知识库（KB Layer）
- 知识库是**知识权威源**：文件/知识点关联由知识库概念空间决定，未被覆盖的不参与关联
- 本体图（`kb_relations`）+ 文件知识画像（`file_knowledge_profiles`）+ 文件间关联（`file_knowledge_links`）
- 上传知识库文档 → 自动理解（同义合并/定义冲突/关系落库）→ 一键重建关联
- 前端「知识库」页：概览/上传理解/知识点管理/关联锚定与文件画像

### 5. 图谱总结与导出（新）
- 结构总结：层级 / 领域 / 核心枢纽 / 知识簇（并查集）/ **学习主线** / 知识库桥接 / 孤立点 / 建议
- 生成 **Mermaid 流程图**（AI 原生可读：箭头带真实关系类型、虚线=知识库桥接、按 L1-L4 分层）
- **AI 可读摘要**（固定结构 token 友好，可直接投喂大模型继续学习/出题/写讲义）
- 一键导出：**Markdown / Word (.docx) / PPT (.pptx，10 页 16:9，流程图原生绘制不糊) / Mermaid / JSON**
- 前端「图谱总结」页签 + CLI（`py scripts/graph_summary.py`）；示例见 `test_data/summary_examples/`

### 6. 大文件保护（防崩溃）
- 四层防护：限量读取（>20MB 413 不进内存）→ 解析截断（行数/节点上限）→
  推理剪枝（内存索引 + 候选剪枝 + 配对数/时间/输出三重预算）→ 渲染降级（>600 节点只画高热度标签）
- 前端回显"已截断"徽标 + 上传前按后端上限校验

### 7. 后台管理（口令保护）
- 顶部导航「后台管理」→ 输入 `ADMIN_TOKEN`（默认 `kg-admin`，请改）
- 概览（规模/判定分布/近 7 天操作/分数分布）· 知识点审阅（完整证据链抽屉 + 单条/批量裁决 + 重跑联网判定）
- 操作审计台账（每个动作的依据摘要 + 明细 JSON）· 用户与文件

### 8. 个人主页
- 头像/背景图**上传到服务端**（换设备不丢），类型按文件头魔数校验，文件名随机化
- 背景参数（不透明度/模糊/范围）实时预览，一键应用到界面
- 「我的数据」概览（文件/知识点/候选/待审/知识库条目/操作记录）

### 9. 学习增强套件
- 局部图谱（深度 1/2/3 跳 BFS 扩展）、知识网络分析仪表盘（度中心度/介数/PageRank/连通分量）
- 智能连接推荐、`[[双向链接]]`（镜像 div 光标定位）、图谱交互筛选（颜色/大小/文件夹/标签/关系类型）
- 轻量插件系统（内置导出 JSON/Markdown、笔记统计）、学习路径导出、间隔重复回顾、知识问答、知识时间线

---

## 三、目录结构

```
YR/
├── backend/                # Python FastAPI 后端
│   ├── app/
│   │   ├── api/            # files / knowledge / graph / notes / kb / summary / admin / profile
│   │   ├── services/       # parser / vector_engine / inference / validator / kb_* /
│   │   │                   # file_splitter / knowledge_verifier / web_probe / audit / graph_summary / summary_export
│   │   ├── models/         # 13 张表 ORM（含 candidates / audit_logs / user_profiles）
│   │   ├── config.py / database.py / main.py / seed.py
│   │   └── scripts/        # kb_build.py（--reparse/--sync-corpus/--understand）、graph_summary.py
│   ├── requirements.txt
│   └── .env.example        # 配置模板（复制为 .env 使用，.env 不上传）
├── kg-vue3/                # Vue 3 前端
│   ├── src/
│   │   ├── components/     # GraphCanvas / KnowledgeWorkbench / AdminView / ProfileView /
│   │   │                   # GraphSummaryView / KnowledgeBaseView / MermaidFlow ...
│   │   ├── store/          # graphStore / fileStore / kbStore / summaryStore / noteStore ...
│   │   ├── api/            # fileAPI / knowledgeAPI / graphAPI / noteAPI / kbAPI / summaryAPI / profileAPI / adminAPI
│   │   ├── services/ utils/ plugins/ styles/ domain_corpus/
│   │   └── App.vue
│   ├── package.json
│   └── vite.config.js
├── domain_corpus/          # 领域知识库（software.md / embedded.md / writing.md / manifest.json）
├── test_data/              # 测试样例（doc_A~E + kb_demo + summary_examples）
├── app.js / index.html / styles.css / main.js / preload.js   # Electron 桌面版
├── server.js               # 本地静态服务
├── 启动服务.bat / 知识图谱.bat
└── docker-compose.yml      # 一键部署（前端 + 后端）
```

## 四、快速开始

### 方式一：本地开发运行
```bash
# 1. 后端（端口 8080）
cd backend
pip install -r requirements.txt
cp .env.example .env        # 按需修改 ADMIN_TOKEN 等
py -m uvicorn app.main:app --port 8080

# 2. 前端（端口 5173）
cd kg-vue3
npm install
npm run dev
# 浏览器打开 http://localhost:5173
```

### 方式二：Electron 桌面版
```bash
npm install
npm start
```

### 方式三：双击批处理（Windows）
- `启动服务.bat`：一键启动后端 + 前端
- `知识图谱.bat`：启动知识图谱批处理

### 方式四：Docker 一键部署
```bash
docker compose up -d
```

## 五、技术栈

| 层 | 技术 |
|---|---|
| 桌面壳 | Electron（IPC / contextBridge / webContents 拦截） |
| 前端 | Vue 3 `<script setup>` · Vite 5 · Pinia · D3 v7 · Element Plus · @vueuse/core · Mermaid（动态 import） |
| 后端 | Python FastAPI · SQLAlchemy · SQLite · python-pptx · python-docx |
| 算法 | 余弦相似度 · 四维融合打分 · 并查集 · PageRank · Brandes 介数 · BFS 最短路径 · 间隔重复 |

## 六、配置（`.env`）

| 项 | 默认 | 说明 |
|---|---|---|
| `ADMIN_TOKEN` | `kg-admin` | 后台管理口令（**请修改**） |
| `MAX_UPLOAD_MB_HARD` | `100` | 上传硬上限（MB） |
| `SPLIT_TARGET_LINES` | `6000` | 单片目标行数 |
| `MAX_NODES_PER_FILE_TOTAL` | `3000` | 切割后单文件知识点总量上限 |
| `VERDICT_USE_WEB` | `true` | 是否联网判定 |
| `VERDICT_MAX_WEB_CALLS` | `30` | 单批判定最大联网次数 |
| `UPLOAD_DIR` | `./uploads` | 头像/背景图存储目录 |

## 七、详细说明文档

| 文档 | 内容 |
|---|---|
| `技术栈与功能实现清单.md` | 三层全量实现清单（含 F1-F6 / P1-P3 增强功能） |
| `智能切割与知识点判定说明.md` | 切割算法、四路判定、后台管理、个人主页 |
| `图谱总结与导出说明.md` | 总结维度、Mermaid 流程图、AI 摘要、6 种导出格式 |
| `大文件上传保护说明.md` | 四层防崩溃方案与配置 |
| `知识库设计说明.md` | 知识库数据模型与关联算法 |
