"""抓 Learn Anything 主题页 → 标题/域名/URL → 中文翻译 → 落本地语料。

网站是 SPA（TanStack Start + Clerk），纯 HTTP 只返回空壳，列表必须浏览器渲染后取 DOM。
这里调用 agent-browser 完成渲染与提取；翻译走 services/translate。

用法：
    py scripts/la_import.py web
    py scripts/la_import.py web math --no-translate
"""
import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
OUT_DIR = ROOT / "domain_corpus" / "learn_anything"

sys.path.insert(0, str(BACKEND))

# 条目结构：标题在 L2 容器首行，域名是链接自身文本
EXTRACT_JS = (
    "(() => {"
    "const out=[...document.querySelectorAll('a[target=\"_blank\"]')]"
    ".filter(a=>a.href && !a.href.includes('learn-anything.xyz'))"
    ".map(a=>{"
    "const box=a.parentElement?.parentElement;"
    "const lines=(box?.innerText||'').split('\\n').map(s=>s.trim()).filter(Boolean);"
    "return {title: lines[0]||'', domain: a.innerText.trim(), url: a.href};"
    "}).filter(x=>x.url && x.title);"
    "return JSON.stringify(out);"
    "})()"
)


def _cli() -> str:
    return shutil.which("agent-browser") or "agent-browser"


def _run(args, timeout=90):
    cmd = _cli()
    if cmd.lower().endswith((".cmd", ".bat")):
        full = ["cmd", "/c", cmd] + args
    else:
        full = [cmd] + args
    return subprocess.run(full, capture_output=True, text=True,
                          encoding="utf-8", errors="ignore", timeout=timeout)


def fetch_topic(topic: str, wait: float = 7.0) -> list:
    """打开主题页并把资源列表读出来。"""
    url = f"https://learn-anything.xyz/{topic}"
    _run(["open", url])
    time.sleep(wait)
    out = _run(["eval", EXTRACT_JS])
    raw = (out.stdout or "").strip()
    if not raw:
        raise RuntimeError(f"页面未返回数据：{out.stderr.strip()[:160]}")
    # eval 的输出是「JSON 字符串的 JSON 编码」，要解两层
    return json.loads(json.loads(raw))


def save(topic: str, items: list) -> Path:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    path = OUT_DIR / f"{topic}.json"
    payload = {
        "topic": topic,
        "source": f"https://learn-anything.xyz/{topic}",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "items": items,
    }
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def main() -> int:
    parser = argparse.ArgumentParser(description="导入 Learn Anything 主题资源")
    parser.add_argument("topics", nargs="+", help="主题名，如 web / math / programming")
    parser.add_argument("--no-translate", action="store_true", help="只抓取不翻译")
    args = parser.parse_args()

    from app.services.translate import translate_many

    for topic in args.topics:
        try:
            items = fetch_topic(topic)
        except Exception as exc:
            print(f"[{topic}] 抓取失败：{type(exc).__name__}: {exc}")
            continue

        if not args.no_translate and items:
            items = translate_many(items, "title")
            ok = sum(1 for x in items if x.get("title_zh") and x["title_zh"] != x["title"])
            print(f"[{topic}] {len(items)} 条，翻译 {ok} 条")
        else:
            print(f"[{topic}] {len(items)} 条（未翻译）")

        path = save(topic, items)
        print(f"[{topic}] 已写入 {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
