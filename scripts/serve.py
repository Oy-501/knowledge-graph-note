"""常驻运行：守护前后端，进程挂了自动拉起。

与 dev.py 的分工：
  dev.py  前台阻塞、关窗口即停，适合开发时看日志；
  serve.py 子进程以 DETACHED_PROCESS 启动，自身也脱离终端，适合「放着一直跑」。

用法：
    python scripts/serve.py            # 启动守护（后台）
    python scripts/serve.py --status   # 查看状态
    python scripts/serve.py --stop     # 停止守护与前后端
"""
import argparse
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "kg-vue3"
LOGS = ROOT / "logs"
LOGS.mkdir(exist_ok=True)

PID_FILE = LOGS / "serve.pid"
BACKEND_PID = LOGS / "backend.pid"
FRONTEND_PID = LOGS / "frontend.pid"

INTERVAL = 15              # 巡检间隔（秒）
START_GRACE = 35           # 启动宽限期：后端加载模型要十几秒，期间不判死
MAX_QUICK_RESTARTS = 5     # 连续快速重启次数上限，超过就放慢，避免刷爆日志
QUICK_WINDOW = 300         # 判定「快速重启」的时间窗（秒）

BACKEND_PORT = 8080
FRONTEND_PORT = 5173

DETACHED = 0x00000008 | 0x00000200   # DETACHED_PROCESS | CREATE_NEW_PROCESS_GROUP


def log(msg: str) -> None:
    line = f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {msg}"
    with open(LOGS / "serve.log", "a", encoding="utf-8") as f:
        f.write(line + "\n")


def _read_pid(path: pathlib.Path) -> int:
    try:
        return int(path.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return 0


def _alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        # tasklist 在中文 Windows 上输出 GBK，强制 UTF-8 解码会抛 UnicodeDecodeError
        out = subprocess.run(["tasklist", "/FI", f"PID eq {pid}", "/NH"],
                             capture_output=True, text=True,
                             encoding="utf-8", errors="ignore", timeout=10)
        return str(pid) in (out.stdout or "")
    except Exception:
        return False


def _http_ok(url: str, expect_json: bool = False) -> bool:
    try:
        with urllib.request.urlopen(url, timeout=2) as resp:
            if resp.status != 200:
                return False
            if not expect_json:
                return True
            return json.load(resp).get("status") == "ok"
    except Exception:
        return False


def backend_ok() -> bool:
    return _http_ok(f"http://127.0.0.1:{BACKEND_PORT}/api/health", expect_json=True)


def frontend_ok() -> bool:
    return _http_ok(f"http://127.0.0.1:{FRONTEND_PORT}/")


def _kill(pid: int) -> None:
    if pid <= 0:
        return
    try:
        subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"],
                       capture_output=True, timeout=15)
    except Exception:
        pass


def _heal_sqlite() -> None:
    """强杀后端会留下 WAL/SHM 残留，新进程写库时变成只读。

    启动前先做一次 checkpoint：此时没有进程在用库，操作安全。
    不做这一步，每次 kill 之后都要人工「停服 + checkpoint + 重启」才能恢复。
    """
    db = BACKEND / "kg.db"
    if not db.exists() or not (BACKEND / "kg.db-shm").exists():
        return
    try:
        import sqlite3
        con = sqlite3.connect(str(db), timeout=5)
        con.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        con.close()
        log("已清理 WAL 残留（避免库变只读）")
    except Exception as exc:
        log(f"WAL 清理失败：{type(exc).__name__}: {exc}")


def start_backend() -> int:
    _heal_sqlite()
    out = open(LOGS / "backend.log", "ab")
    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.main:app",
         "--host", "127.0.0.1", "--port", str(BACKEND_PORT)],
        cwd=str(BACKEND), stdout=out, stderr=out,
        stdin=subprocess.DEVNULL, creationflags=DETACHED)
    BACKEND_PID.write_text(str(proc.pid), encoding="utf-8")
    log(f"后端已启动 pid={proc.pid}")
    return proc.pid


def start_frontend() -> int:
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        log("未找到 npm，前端无法启动")
        return 0
    out = open(LOGS / "frontend.log", "ab")
    proc = subprocess.Popen(
        ["cmd", "/c", npm, "run", "preview", "--",
         "--port", str(FRONTEND_PORT), "--host", "127.0.0.1"],
        cwd=str(FRONTEND), stdout=out, stderr=out,
        stdin=subprocess.DEVNULL, creationflags=DETACHED)
    FRONTEND_PID.write_text(str(proc.pid), encoding="utf-8")
    log(f"前端已启动 pid={proc.pid}")
    return proc.pid


def stop_all() -> None:
    """停守护与前后端（先停守护，避免它把子进程又拉起来）。"""
    daemon = _read_pid(PID_FILE)
    if daemon and daemon != os.getpid():
        _kill(daemon)
    for path in (BACKEND_PID, FRONTEND_PID):
        _kill(_read_pid(path))
        try:
            path.unlink()
        except OSError:
            pass
    try:
        PID_FILE.unlink()
    except OSError:
        pass


def status() -> int:
    lines = [
        f"守护进程: {'运行中 pid=' + str(_read_pid(PID_FILE)) if _alive(_read_pid(PID_FILE)) else '未运行'}",
        f"后端 8080: {'健康' if backend_ok() else '不可用'} (pid={_read_pid(BACKEND_PID)})",
        f"前端 5173: {'可访问' if frontend_ok() else '不可用'} (pid={_read_pid(FRONTEND_PID)})",
        f"日志目录: {LOGS}",
    ]
    for line in lines:
        print(line)
    return 0


def daemon_loop() -> None:
    PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    log(f"守护启动 pid={os.getpid()}，巡检间隔 {INTERVAL}s")

    restarts = {"backend": [], "frontend": []}
    started = {"backend": 0.0, "frontend": 0.0}   # 上次启动时刻，用于宽限期
    fails = {"backend": 0, "frontend": 0}
    healed = {"backend": 0.0, "frontend": 0.0}

    def diagnose(name: str) -> None:
        """连续失败才诊断，同一服务 10 分钟内只做一次，避免刷报告。"""
        now = time.time()
        if now - healed[name] < 600:
            return
        healed[name] = now
        try:
            log(f"{name} 连续失败 {fails[name]} 次，触发自愈诊断")
            subprocess.Popen(
                [sys.executable, str(BACKEND / "scripts" / "selfheal.py"),
                 "--tag", f"daemon-{name}"],
                cwd=str(ROOT), stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL, creationflags=DETACHED)
        except Exception as exc:
            log(f"自愈诊断启动失败：{type(exc).__name__}: {exc}")

    def need_restart(name: str) -> bool:
        """同一服务短时间内反复挂掉时放慢重启，避免把日志刷爆。"""
        now = time.time()
        recent = [t for t in restarts[name] if now - t < QUICK_WINDOW]
        restarts[name] = recent
        if len(recent) >= MAX_QUICK_RESTARTS:
            log(f"{name} 5 分钟内已重启 {len(recent)} 次，本次跳过")
            return False
        restarts[name].append(now)
        return True

    def ensure(name: str, healthy, starter, pid_file: pathlib.Path) -> None:
        """不健康才重启；刚启动的 N 秒内不判死（uvicorn 加载模型要十几秒）。"""
        now = time.time()
        if healthy():
            started[name] = 0.0
            fails[name] = 0
            return
        if now - started[name] < START_GRACE:
            return
        fails[name] += 1
        _kill(_read_pid(pid_file))
        if need_restart(name):
            started[name] = now
            starter()
        if fails[name] >= 3:
            diagnose(name)

    while True:
        try:
            ensure("backend", backend_ok, start_backend, BACKEND_PID)
            ensure("frontend", frontend_ok, start_frontend, FRONTEND_PID)
        except Exception as exc:   # 守护自身不能因为一次异常就退出
            log(f"巡检异常：{type(exc).__name__}: {exc}")
        time.sleep(INTERVAL)


def main() -> int:
    parser = argparse.ArgumentParser(description="知识图谱系统常驻守护")
    parser.add_argument("--status", action="store_true", help="查看状态")
    parser.add_argument("--stop", action="store_true", help="停止守护与前后端")
    args = parser.parse_args()

    if args.status:
        return status()
    if args.stop:
        stop_all()
        print("已停止")
        return 0

    daemon = _read_pid(PID_FILE)
    if _alive(daemon):
        print(f"守护已在运行 pid={daemon}")
        return status()

    # 首次启动也交给巡检循环：那里有启动宽限期，不会把「正在加载」当成挂了
    daemon_loop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
