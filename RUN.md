# 运行说明（给拿到分发包的人）

两种方式，任选其一。**推荐 Docker**：不需要装 Python/Node，也不用手动装依赖。

---

## 方式 A：Docker（推荐）

前置：安装 Docker Desktop（Windows/macOS）或 Docker Engine（Linux）。

```bash
# 1. 准备环境变量
cp .env.docker.example .env
# 编辑 .env：把 ADMIN_TOKEN 改成一段随机强口令

# 2. 构建并启动
docker compose up -d --build

# 3. 打开
# http://localhost:8080
```

首次访问会进入**初始化向导**，设置管理员账号与密码即可。

常用命令：

```bash
docker compose logs -f backend   # 看后端日志
docker compose down              # 停止（数据保留在卷里）
docker compose up -d             # 再次启动
```

数据位置：

- `kg_data` 卷：`kg.db`、`uploads/`、`exports/`
- `model_cache` 卷：语义模型权重（首次运行下载，约 470MB）

备份：

```bash
docker run --rm -v yr_kg_data:/data -v "$PWD":/backup alpine \
  tar czf /backup/kg-data-$(date +%Y%m%d).tar.gz -C /data .
```

可选 PostgreSQL：

```bash
DB_MODE=postgres \
DATABASE_URL=postgresql://kg_user:kg_pass@db:5432/knowledge_graph \
docker compose --profile pg up -d --build
```

---

## 方式 B：源码运行

前置：Python 3.10+、Node.js 18+。

### 后端

```bash
cd backend
python -m venv .venv

# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

python -m pip install -r requirements.txt
cp .env.example .env      # Windows: copy .env.example .env
# 编辑 .env：修改 ADMIN_TOKEN
```

> 语义向量依赖 torch/sentence-transformers，体积较大。只想先跑通可以先不装，
> 系统会自动降级为字面重合；需要时再装：
> `python -m pip install torch --index-url https://download.pytorch.org/whl/cpu`

### 前端 + 后端一起启动（项目根目录）

```bash
python scripts/dev.py
# macOS / Linux 也可：bash start.sh
# Windows 也可双击：启动服务.bat
```

打开 http://127.0.0.1:5173 ，首次进入初始化向导。

---

## 首次登录

- 浏览器打开后，如果显示「初始化」，设置用户名/密码，这就是首个管理员。
- 初始化完成后该入口永久关闭（再次调用返回 403）。
- 忘记密码：用注册时生成的恢复码；没有恢复码时，管理员可在后台重置其他账号。

---

## 常见问题

| 现象 | 处理 |
|---|---|
| 8080 被占用 | Docker：改 `.env` 的 `WEB_PORT`；源码：`python scripts/dev.py --port 8090`，并同步改 `kg-vue3/.env.development` 的 `VITE_API_BASE` |
| 页面提示 Failed to fetch | 确认后端已启动；确认前端 `VITE_API_BASE` 与后端端口一致 |
| 模型下载慢/失败 | `.env` 设 `HF_ENDPOINT=https://hf-mirror.com`；或 `VECTOR_BACKEND=tfidf` 先跳过模型 |
| 上传大文件失败 | 后端硬上限 `MAX_UPLOAD_MB_HARD=100`；Docker 的 nginx 已配 120MB |
| 想清空数据重来 | Docker：`docker compose down -v`（会删卷）；源码：删除 `backend/kg.db` 与 `backend/uploads/` |

---

## 目录说明

| 目录 | 内容 |
|---|---|
| `backend/app` | FastAPI 应用（API / 服务 / 模型） |
| `backend/tests` | pytest 全量测试 |
| `kg-vue3/src` | Vue 3 前端源码 |
| `domain_corpus` | 领域语料（启动时导入知识库） |
| `scripts/dev.py` | 跨平台开发启动器 |
| `scripts/package.py` | 重新打源码包 |
| `docker-compose.yml` | 生产编排 |
