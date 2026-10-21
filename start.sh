#!/usr/bin/env bash
# 跨平台启动（macOS / Linux）：bash start.sh
# 参数与 scripts/dev.py 一致，例如：bash start.sh --backend-only
set -euo pipefail
cd "$(dirname "$0")"

if command -v python3 >/dev/null 2>&1; then
  PY=python3
elif command -v python >/dev/null 2>&1; then
  PY=python
else
  echo "未找到 python3 / python，请先安装 Python 3.10+" >&2
  exit 1
fi

exec "$PY" scripts/dev.py "$@"
