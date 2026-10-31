"""自愈诊断：服务、依赖、连接出问题时，先按已知模式修，未知再联网找线索。

安全边界（重要）：
- 自动执行的动作全部是**代码里写死的**白名单函数，绝不执行网页上抓到的命令；
- 破坏性操作（删数据、改配置、重装环境）只出建议，不自动做；
- 联网检索只用于补充诊断报告，不参与「要不要执行」的决策。

用法：
    py scripts/selfheal.py                 # 诊断 + 写报告（不动手）
    py scripts/selfheal.py --auto          # 诊断 + 执行白名单动作
    py scripts/selfheal.py --why "No module named 'foo'"   # 只分析一条错误
"""
import argparse
import re
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
LOGS = ROOT / "logs"
REPORT_DIR = ROOT / "docs" / "selfheal"

sys.path.insert(0, str(BACKEND))

BACKEND_URL = "http://127.0.0.1:8080/api/health"
FRONTEND_URL = "http://127.0.0.1:5173/"

# 错误签名 → 处理方式。动作写在 apply() 里，不来自外部文本。
# 匹配一律忽略大小写：Windows 上同一错误会写成 WinError / winerror 两种。
# query 是联网检索用的提示词：拿整行错误去搜会命中词典页，必须按错误类型搜。
SIGNATURES = [
    {"re": r"No module named '([\w\.]+)'", "kind": "missing_module", "auto": True,
     "query": "Python No module named {arg} 安装 解决方法"},
    {"re": r"address already in use|errno 10048|bind on address|通常每个套接字地址",
     "kind": "port_conflict", "auto": False,
     "query": "Windows Python Errno 10048 端口被占用 解决方法"},
    {"re": r"database is locked|数据库被锁", "kind": "db_locked", "auto": False,
     "query": "SQLite database is locked 解决方法"},
    {"re": r"MemoryError|OutOfMemory|CUDA out of memory|内存不足", "kind": "oom", "auto": False,
     "query": "Python MemoryError 内存不足 解决方法"},
    {"re": r"connection refused|econnrefused|failed to fetch|无法连接",
     "kind": "conn_refused", "auto": True,
     "query": "Python 连接被拒绝 Connection refused 解决方法"},
    {"re": r"disk I/O error|no space left|磁盘空间不足", "kind": "disk", "auto": False,
     "query": "SQLite disk I/O error 磁盘空间不足 解决方法"},
    {"re": r"attempt to write a readonly database|readonly database", "kind": "db_readonly",
     "auto": False,
     "query": "SQLite attempt to write a readonly database 解决方法"},
]


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    LOGS.mkdir(exist_ok=True)
    with open(LOGS / "selfheal.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _http_ok(url: str, expect_json: bool = False) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if resp.status != 200:
                return False
            return True if not expect_json else b'"ok"' in resp.read(200)
    except Exception:
        return False


def probe() -> dict:
    """运行时探针：只读，不修改任何状态。"""
    info = {
        "backend": _http_ok(BACKEND_URL, expect_json=True),
        "frontend": _http_ok(FRONTEND_URL),
        "db": False,
        "db_error": "",
    }
    try:
        from app.config import settings
        db_path = settings.resolved_sqlite_path
    except Exception:
        db_path = str(BACKEND / "kg.db")
    info["db_path"] = db_path
    try:
        con = sqlite3.connect(db_path, timeout=3)
        con.execute("SELECT 1").fetchone()
        con.close()
        info["db"] = True
    except Exception as exc:
        info["db_error"] = f"{type(exc).__name__}: {exc}"
    return info


def _decode_line(chunk: bytes) -> str:
    """逐个尝试常见编码：后端日志里 uvicorn 写 UTF-8、Windows 写 GBK，会混在一起。"""
    for enc in ("utf-8", "gbk"):
        try:
            return chunk.decode(enc)
        except UnicodeDecodeError:
            continue
    return chunk.decode("utf-8", errors="replace")


def tail(path: Path, n: int = 150) -> list:
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    return [_decode_line(line).rstrip("\r") for line in raw.split(b"\n")[-n:]]


def classify(lines: list) -> list:
    """把日志行归到已知签名上；同一类只记第一条，避免报告被刷屏。"""
    hits, seen = [], set()
    for sig in SIGNATURES:
        if sig["kind"] in seen:
            continue
        for line in lines:
            m = re.search(sig["re"], line, re.I)
            if m:
                seen.add(sig["kind"])
                hits.append({
                    "kind": sig["kind"],
                    "auto": sig["auto"],
                    "query": sig["query"],
                    "line": line.strip()[:220],
                    "arg": m.group(1) if m.groups() else "",
                })
                break
    return hits


def _requirement_for(module: str) -> str:
    """只在 requirements.txt 已声明的包里找，避免装来路不明的包。"""
    name = module.split(".")[0].lower().replace("_", "-")
    try:
        for raw in (BACKEND / "requirements.txt").read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            if line.split("==")[0].split(">=")[0].strip().lower().replace("_", "-") == name:
                return line
    except OSError as exc:
        log(f"读取 requirements.txt 失败：{exc}")
    return ""


def apply(hit: dict, auto: bool) -> str:
    """执行白名单动作，返回一句「做了什么」或「建议什么」。"""
    kind = hit["kind"]

    if kind == "missing_module":
        req = _requirement_for(hit["arg"])
        if not req:
            return f"{hit['arg']} 不在 requirements.txt 里，需人工确认包名，未动"
        if not auto:
            return f"建议执行：pip install {req}"
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", req],
                           capture_output=True, timeout=300)
            return f"已执行：pip install {req}"
        except Exception as exc:
            return f"安装失败：{type(exc).__name__}: {exc}"

    if kind == "conn_refused":
        if not auto:
            return "建议执行：py scripts/serve.py（重启前后端）"
        try:
            subprocess.run([sys.executable, str(ROOT / "scripts" / "serve.py")],
                           cwd=str(ROOT), capture_output=True, timeout=60)
            return "已执行：serve.py 拉起前后端"
        except Exception as exc:
            return f"重启失败：{type(exc).__name__}: {exc}"

    if kind == "port_conflict":
        return "端口被占用：先确认占用进程是不是本项目残留（netstat -ano | findstr 8080），确认后再停"

    if kind == "db_locked":
        return "数据库被锁：多为并发写入或上次进程未退出，重启后端可解；长期建议开启 WAL"

    if kind == "db_readonly":
        return ("数据库只读：常是 kill 后端留下 WAL/SHM 残留。停服务后执行 "
                "PRAGMA wal_checkpoint(TRUNCATE) 再启动（先备份 kg.db）")

    if kind == "oom":
        return "内存不足：降低单文件节点上限（MAX_NODES_PER_FILE）或分批上传"

    if kind == "disk":
        return "磁盘空间或 I/O 异常：清理 logs/ 与历史导出文件后重试"

    return "未知签名，仅记录"


# 各类错误的关键词：用来过滤搜索引擎返回的无关页（词典页、下载站）
HINT_KEYS = {
    "missing_module": ["module", "模块", "import", "pip"],
    "port_conflict": ["10048", "端口", "占用", "port", "socket"],
    "db_locked": ["locked", "锁", "sqlite", "database"],
    "db_readonly": ["readonly", "只读", "sqlite", "database", "wal"],
    "oom": ["memory", "内存", "oom"],
    "conn_refused": ["connection", "连接", "refused"],
    "disk": ["disk", "磁盘", "space", "空间"],
}


def _match_keys(text: str, keys: list) -> bool:
    """英文关键词按词边界匹配，否则 support 会被当成含 port。"""
    for key in keys:
        if key.isascii():
            if re.search(rf"\b{re.escape(key)}\b", text):
                return True
        elif key in text:
            return True
    return False


def online_hints(hit: dict) -> list:
    """联网找线索：只用来写报告，不会被当作命令执行。

    搜索结果经常是词典页或下载站，按错误类型的关键词过滤，
    宁可写「未找到」也不把噪音当线索。
    """
    query = (hit.get("query") or hit.get("line", "")[:80]).replace("{arg}", hit.get("arg") or "")
    keys = HINT_KEYS.get(hit.get("kind"), [])
    try:
        from app.services import web_probe
        res = web_probe.search_multi(query, limit=6)
    except Exception as exc:
        return [{"title": f"检索失败：{type(exc).__name__}", "url": "", "provider": ""}]

    out = []
    for item in (res.get("results") or []):
        text = f"{item.get('title', '')} {item.get('snippet', '')}".lower()
        if keys and not _match_keys(text, keys):
            continue
        out.append({
            "title": (item.get("title") or "")[:90],
            "url": item.get("url") or "",
            "provider": item.get("provider") or "",
        })
        if len(out) >= 3:
            break

    return out or [{"title": "未找到相关线索（搜索源可能被限流或结果不相关）",
                    "url": "", "provider": ""}]


def write_report(info: dict, hits: list, actions: list, hints: list, tag: str) -> Path:
    REPORT_DIR.mkdir(parents=True, exist_ok=True)
    path = REPORT_DIR / f"{time.strftime('%Y%m%d-%H%M%S')}-{tag}.md"

    lines = [
        f"# 自愈诊断 {time.strftime('%Y-%m-%d %H:%M:%S')}",
        "",
        "## 探针",
        f"- 后端 8080：{'正常' if info['backend'] else '不可用'}",
        f"- 前端 5173：{'正常' if info['frontend'] else '不可用'}",
        f"- 数据库：{'可读' if info['db'] else '不可读'}（{info['db_path']}）",
    ]
    if info["db_error"]:
        lines.append(f"- 数据库错误：{info['db_error']}")

    lines += ["", "## 命中的错误"]
    if not hits:
        lines.append("无已知签名命中。")
    for i, hit in enumerate(hits, 1):
        lines.append(f"{i}. `{hit['kind']}`（{'可自动' if hit['auto'] else '仅建议'}）")
        lines.append(f"   - 原文：`{hit['line']}`")
        lines.append(f"   - 处理：{actions[i - 1] if i - 1 < len(actions) else ''}")

    lines += ["", "## 联网线索（仅参考，不会被执行）"]
    if not hints:
        lines.append("无。")
    for hint in hints:
        if hint["url"]:
            lines.append(f"- [{hint['title']}]({hint['url']})（{hint['provider']}）")
        else:
            lines.append(f"- {hint['title']}")

    lines += ["", "> 自动动作仅限代码内置白名单（装已声明依赖、重启服务）；",
              "> 网页内容只作为线索，不参与执行。"]

    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def run_once(auto: bool = False, tag: str = "manual", extra_error: str = "") -> dict:
    info = probe()

    err_lines = tail(LOGS / "backend.log") + tail(LOGS / "frontend.log") + tail(LOGS / "serve.log")

    # 探针全绿时，日志里的错误是历史残留，拿它当「当前故障」会误报
    healthy = info["backend"] and info["frontend"] and info["db"]
    if extra_error:
        hits = classify([extra_error])
    elif healthy:
        hits = []
    else:
        hits = classify(err_lines)

    actions = [apply(hit, auto) for hit in hits[:3]]
    hints = []
    for hit in hits[:2]:
        hints.extend(online_hints(hit))

    path = write_report(info, hits, actions, hints, tag)
    log(f"诊断完成 tag={tag} 命中={len(hits)} 报告={path.name}")
    return {"probe": info, "hits": hits, "actions": actions, "hints": hints, "report": str(path)}


def main() -> int:
    parser = argparse.ArgumentParser(description="自愈诊断（默认不动手）")
    parser.add_argument("--auto", action="store_true", help="执行白名单动作")
    parser.add_argument("--why", default="", help="只分析一条错误文本")
    parser.add_argument("--tag", default="manual")
    args = parser.parse_args()

    result = run_once(auto=args.auto, tag=args.tag, extra_error=args.why)

    print(f"报告：{result['report']}")
    for line in (
        f"后端 {'正常' if result['probe']['backend'] else '不可用'} / "
        f"前端 {'正常' if result['probe']['frontend'] else '不可用'} / "
        f"数据库 {'可读' if result['probe']['db'] else '不可读'}"
    , ):
        print(line)

    if not result["hits"]:
        print("未命中已知错误签名")
    for i, hit in enumerate(result["hits"]):
        print(f"- {hit['kind']}：{result['actions'][i] if i < len(result['actions']) else ''}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
