# 知识图谱笔记系统（Knowledge Graph Notes）

基于语义向量 + 领域知识库的知识图谱笔记应用，支持多文件上传、自动抽取知识点、跨文件语义关联、知识库推理溯源、本地/在线双模式运行。

## 项目结构

```
YR/
├── backend/            # Python FastAPI 后端（知识点抽取、向量索引、知识库推理、自测）
├── kg-vue3/            # Vue 3 + D3.js 前端（图谱渲染、知识库管理、自测面板）
├── domain_corpus/      # 领域语料知识库（软件/嵌入式/写作，供本体推理桥接）
├── test_data/          # 测试样例（doc_A~E + kb_demo）
├── app.js / index.html / styles.css / main.js / preload.js   # Electron 桌面版
├── server.js           # 本地静态服务
└── docker-compose.yml  # 一键部署（前端 + 后端）
```

## 快速开始

### 方式一：本地直接运行（浏览器模式）
```bash
# 1. 启动后端
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000

# 2. 启动前端静态服务
npm install
node server.js
# 浏览器打开 http://localhost:8080
```

### 方式二：Docker 一键部署
```bash
docker compose up -d
```

### 方式三：Electron 桌面版
```bash
npm install
npm start
```

## 核心特性

- **多文件上传与关联**：上传 .md/.txt 自动分片、抽取知识点、生成语义向量
- **两级边模型**：知识点边（Kp_Edge）内部计算，文件关联边（Doc_Edge）图谱渲染
- **四维融合打分**：向量相似度 + 关键词重合 + 实体共现 + 领域知识库推理
- **零孤立节点**：全局重建强制语义桥接，异常节点监控面板
- **溯源弹窗**：每条关联展示来源类型、分数分解、原文证据（含知识库 bridge_sentence）
- **自测系统**：验证上传、多文件关联、删除清理、图谱覆盖等核心链路
- **删除功能**：单文件删除 / 清空全部，D3 exit().remove() 确保无残留
