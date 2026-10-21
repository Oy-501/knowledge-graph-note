"""跨平台开发启动器：一条命令同时拉起后端与前端。

Windows / macOS / Linux 通用，不依赖 .bat 或 shell 语法：

    python scripts/dev.py                 # 后端 8080 + 前端 5173
    python scripts/dev.py --backend-only
    python scripts/dev.py --frontend-only
    python scripts/dev.py --port 8080 --frontend-port 5173

注意：改后端端口时，前端 API 地址（kg-vue3/.env.development 的
VITE_API_BASE）要同步改，否则前端仍会请求旧端口。
"""
import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "kg-vue3"


def _npm() -> str:
    # Windows 上是 npm.cmd，POSIX 上是 npm
    return shutil.which("npm") or shutil.which("npm.cmd") or ""


def _run(cmd, cwd, env):
    print(f"[{Path(cwd).name}] {' '.join(cmd)}")
    return subprocess.Popen(cmd, cwd=str(cwd), env=env)


def main() -> int:
    parser = argparse.ArgumentParser(description="跨平台开发启动器")
    parser.add_argument("--backend-only", action="store_true")
    parser.add_argument("--frontend-only", action="store_true")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--frontend-port", type=int, default=5173)
    args = parser.parse_args()

    env = os.environ.copy()
    env.setdefault("PYTHONIOENCODING", "utf-8")

    procs = []
    try:
        if not args.frontend_only:
            procs.append(_run(
                [sys.executable, "-m", "uvicorn", "app.main:app",
                 "--host", "127.0.0.1", "--port", str(args.port)],
                BACKEND, env))

        if not args.backend_only:
            npm = _npm()
            if not npm:
                print("未找到 npm，请先安装 Node.js（>= 18）", file=sys.stderr)
                return 2
            procs.append(_run(
                [npm, "run", "dev", "--", "--port", str(args.frontend_port)],
                FRONTEND, env))

        print(f"\n后端 http://127.0.0.1:{args.port}")
        print(f"前端 http://127.0.0.1:{args.frontend_port}")
        print("Ctrl+C 结束\n")

        while True:
            for p in procs:
                code = p.poll()
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
        for p in procs:
            if p.poll() is None:
                p.terminate()
        for p in procs:
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()


if __name__ == "__main__":
    raise SystemExit(main())
