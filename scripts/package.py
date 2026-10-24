"""生成可分发源码包：排除数据库、模型权重、依赖目录。

    python scripts/package.py
    python scripts/package.py --no-tests     # 不含 tests/
    python scripts/package.py --out D:/tmp   # 指定输出目录

产物：dist/knowledge-graph-notes-YYYYMMDD-HHMM.zip
"""
import argparse
import zipfile
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

INCLUDE = [
    "backend/app",
    "backend/scripts",
    "backend/tests",
    "backend/requirements.txt",
    "backend/requirements-dev.txt",
    "backend/.env.example",
    "backend/Dockerfile",
    "kg-vue3/src",
    "kg-vue3/public",
    "kg-vue3/index.html",
    "kg-vue3/package.json",
    "kg-vue3/package-lock.json",
    "kg-vue3/vite.config.js",
    "kg-vue3/Dockerfile",
    "kg-vue3/nginx.conf",
    "domain_corpus",
    "scripts",
    "start.sh",
    "启动服务.bat",
    "体检.bat",
    "docker-compose.yml",
    ".env.docker.example",
    "README.md",
    "RUN.md",
]

EXCLUDE_DIRS = {
    "__pycache__", "node_modules", ".git", "models", "uploads", "exports",
    "dist", ".venv", "venv", ".idea", ".vscode", "test_data",
}
EXCLUDE_SUFFIX = {
    ".pyc", ".pyo", ".db", ".sqlite", ".sqlite3", ".log", ".bak",
    ".zip", ".mp4", ".pptx",
}

REQUIRED = [
    "backend/app/main.py",
    "kg-vue3/src/App.vue",
    "docker-compose.yml",
    "README.md",
    "RUN.md",
]


def main() -> int:
    """命令行入口：生成分发包。"""
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", default=str(ROOT / "dist"))
    parser.add_argument("--no-tests", action="store_true")
    args = parser.parse_args()

    include = list(INCLUDE)
    if args.no_tests:
        include = [p for p in include if p != "backend/tests"]

    for rel in REQUIRED:
        if not (ROOT / rel).exists():
            print(f"缺少必需文件：{rel}")
            return 1

    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    out = out_dir / f"knowledge-graph-notes-{stamp}.zip"

    count = 0
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for rel in include:
            path = ROOT / rel
            if not path.exists():
                continue
            files = [path] if path.is_file() else sorted(path.rglob("*"))
            for f in files:
                if not f.is_file():
                    continue
                r = f.relative_to(ROOT)
                if any(part in EXCLUDE_DIRS for part in r.parts):
                    continue
                if f.suffix.lower() in EXCLUDE_SUFFIX:
                    continue
                zf.write(f, r.as_posix())
                count += 1

    size_mb = out.stat().st_size / 1024 / 1024
    print(f"已生成 {out}")
    print(f"文件 {count} 个，压缩后 {size_mb:.2f} MB")
    print("分发后按 RUN.md 运行（Docker 或源码两种方式）。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
