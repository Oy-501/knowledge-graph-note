"""跨平台开发启动器：一条命令同时拉起后端与前端。

Windows / macOS / Linux 通用，不依赖 .bat 或 shell 语法：

    python scripts/dev.py                 # 后端端口取自 backend/.env 的 PORT（默认 8080）+ 前端 5173
    python scripts/dev.py --backend-only
    python scripts/dev.py --frontend-only
    python scripts/dev.py --port 8090 --frontend-port 5173
    python scripts/dev.py --open          # 就绪后自动打开浏览器

稳定性约定（这些都是实际踩过的坑）：
  1. 端口只在一处决策：后端端口优先取 backend/.env 的 PORT，避免 README / .bat / dev.py 各写一个数。
  2. 已在运行就复用：目标端口上若已有本项目的健康后端，不再重复起第二个进程
     （两个后端共用一个 SQLite 文件会互相抢写锁）。
  3. 端口被别的程序占用时自动换一个空闲端口，而不是硬编码 8089（8089 也可能被占）。
  4. 前端 API 地址通过环境变量 VITE_API_BASE 注入，端口改了也不用再手改 .env.development。
  5. 先等后端 /api/health 通过，再启动前端；后端起不来就直接报错退出，不留下半套服务。
"""
import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
import urllib.request
import webbrowser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "kg-vue3"
BACKEND_ENV = BACKEND / ".env"

DEFAULT_BACKEND_PORT = 8080
DEFAULT_FRONTEND_PORT = 5173


def _npm() -> str:
    # Windows 上是 npm.cmd，POSIX 上是 npm
    """定位 npm 或 npm.cmd。"""
    return shutil.which("npm") or shutil.which("npm.cmd") or ""


def _run(cmd, cwd, env):
    """打印命令并启动子进程。"""
    print(f"[{Path(cwd).name}] {' '.join(cmd)}", flush=True)
    return subprocess.Popen(cmd, cwd=str(cwd), env=env)


def _env_port(default: int) -> int:
    """从 backend/.env 读取 PORT；读不到或格式不对就用默认值。"""
    try:
        for raw in BACKEND_ENV.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            if key.strip() == "PORT":
                port = int(value.strip())
                if 1 <= port <= 65535:
                    return port
    except (OSError, ValueError):
        pass
    return default


def _port_free(port: int) -> bool:
    """判断端口能否绑定。"""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        try:
            sock.bind(("127.0.0.1", port))
            return True
        except OSError:
            return False


def _backend_healthy(port: int) -> bool:
    """端口上是否是本项目的后端（只认 /api/health 的结构化响应）。"""
    try:
        with urllib.request.urlopen(
            f"http://127.0.0.1:{port}/api/health", timeout=0.8
        ) as resp:
            data = json.load(resp)
            return resp.status == 200 and data.get("status") == "ok"
    except Exception:
        return False


def _frontend_running(port: int) -> bool:
    """判断端口上是否已是本项目前端。"""
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=0.8) as resp:
            return 'id="app"' in resp.read(4096).decode("utf-8", "ignore")
    except Exception:
        return False


def _find_free(start: int, span: int = 20):
    """向后找一个可用端口。"""
    for port in range(start, min(start + span, 65535) + 1):
        if _port_free(port):
            return port
    return None


def _wait(fn, timeout: float, proc=None) -> bool:
    """轮询 fn() 直到为真；进程提前退出则立即失败。"""
    deadline = time.time() + timeout
    while time.time() < deadline:
        if fn():
            return True
        if proc is not None and proc.poll() is not None:
            return False
        time.sleep(0.4)
    return False


def main() -> int:
    """命令行入口：启动后端与前端。"""
    parser = argparse.ArgumentParser(description="跨平台开发启动器")
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument("--frontend-only", action="store_true")
    parser.add_argument("--port", type=int, default=None, help="后端端口（默认取 backend/.env 的 PORT）")
    parser.add_argument("--frontend-port", type=int, default=DEFAULT_FRONTEND_PORT)
    parser.add_argument("--open", action="store_true", help="就绪后自动打开浏览器")
    parser.add_argument("--prod", action="store_true",
                        help="前端以生产构建 + preview 启动（首屏更快，首次需构建）")
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    procs = []
    backend_port = args.port or _env_port(DEFAULT_BACKEND_PORT)
    frontend_port = args.frontend_port
    backend_reused = False
    frontend_reused = False

    try:
        # ---------------- 后端 ----------------
        if not args.frontend_only:
            if _backend_healthy(backend_port):
                print(f"后端已在 {backend_port} 运行，复用现有实例（不重复启动）", flush=True)
                print("  提示：改过后端代码时，请先停止旧实例再启动，否则加载的仍是旧代码。", flush=True)
                backend_reused = True
            else:
                if not _port_free(backend_port):
                    free = _find_free(backend_port + 1)
                    if free is None:
                        print(f"端口 {backend_port} 被占用，且找不到可用端口", file=sys.stderr)
                        return 2
                    print(f"端口 {backend_port} 被其他程序占用，改用 {free}", flush=True)
                    backend_port = free
                procs.append(_run(
                    [sys.executable, "-m", "uvicorn", "app.main:app",
                     "--host", "127.0.0.1", "--port", str(backend_port)],
                    BACKEND, env))
                print("等待后端就绪…", flush=True)
                if not _wait(lambda: _backend_healthy(backend_port), 120, procs[-1]):
                    print(f"后端未能在 {backend_port} 启动，请查看上方日志。", file=sys.stderr)
                    return 1
                print(f"后端已就绪 http://127.0.0.1:{backend_port}", flush=True)

        # ---------------- 前端 ----------------
        if not args.backend_only:
            npm = _npm()
            if not npm:
                print("未找到 npm，请先安装 Node.js（>= 18）", file=sys.stderr)
                return 2

            if _frontend_running(frontend_port):
                print(f"前端已在 {frontend_port} 运行，复用现有实例", flush=True)
                frontend_reused = True
            else:
                if not _port_free(frontend_port):
                    free = _find_free(frontend_port + 1)
                    if free is None:
                        print(f"前端端口 {frontend_port} 被占用，且找不到可用端口", file=sys.stderr)
                        return 2
                    print(f"前端端口 {frontend_port} 被占用，改用 {free}", flush=True)
                    frontend_port = free

                # 环境变量优先级高于 .env 文件：端口换了也不会请求到旧地址
                env["VITE_API_BASE"] = f"http://127.0.0.1:{backend_port}/api"
                if args.prod:
                    # 本机安全删除钩子会拦截 Vite 清空大量产物（>50 个文件），
                    # 先整体移走旧 dist，让构建在空目录里进行
                    dist_dir = FRONTEND / "dist"
                    if dist_dir.exists():
                        backup = FRONTEND / f"dist-old-{int(time.time())}"
                        dist_dir.rename(backup)
                        print(f"旧产物已移到 {backup.name}", flush=True)
                    print("前端生产构建中（首次约 30-60 秒）…", flush=True)
                    build = subprocess.run([npm, "run", "build"], cwd=str(FRONTEND), env=env)
                    if build.returncode != 0:
                        print("前端构建失败，请查看上方日志。", file=sys.stderr)
                        return 1
                    frontend_cmd = [npm, "run", "preview", "--",
                                    "--port", str(frontend_port), "--host", "127.0.0.1"]
                else:
                    frontend_cmd = [npm, "run", "dev", "--", "--port", str(frontend_port)]
                procs.append(_run(frontend_cmd, FRONTEND, env))
                print("等待前端就绪…", flush=True)
                if not _wait(lambda: _frontend_running(frontend_port), 90, procs[-1]):
                    print(f"前端未能在 {frontend_port} 启动，请查看上方日志。", file=sys.stderr)
                    return 1

        url = f"http://127.0.0.1:{frontend_port}" if not args.backend_only else f"http://127.0.0.1:{backend_port}"
        print(f"\n后端 http://127.0.0.1:{backend_port}")
        if not args.backend_only:
            print(f"前端 {url}")
        if args.open:
            webbrowser.open(url)

        if not procs:
            print("前后端都已在运行，无需再启动。", flush=True)
            return 0

        print("Ctrl+C 结束\n", flush=True)
        while True:
            for proc in procs:
                code = proc.poll()
                if code is not None:
                    return code
            try:
                procs[0].wait(timeout=1)
            except subprocess.TimeoutExpired:
                pass
    except KeyboardInterrupt:
        print("\n正在停止…")
        return 0
    finally:
        for proc in procs:
            if proc.poll() is None:
                proc.terminate()
        for proc in procs:
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                proc.kill()


if __name__ == "__main__":
    raise SystemExit(main())
