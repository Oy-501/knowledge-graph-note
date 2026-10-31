"""下载 en→zh 离线翻译模型（MarianMT / opus-mt）。

用法：py scripts/fetch_translate_model.py [--force]
"""
import argparse
import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")

from huggingface_hub import snapshot_download  # noqa: E402

REPO = "Helsinki-NLP/opus-mt-en-zh"
FILES = ["config.json", "pytorch_model.bin", "source.spm", "target.spm",
         "vocab.json", "tokenizer_config.json", "special_tokens_map.json"]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()

    from app.config import settings
    target = Path(settings.resolved_model_dir) / "opus-mt-en-zh"
    if (target / "config.json").exists() and not args.force:
        print(f"已存在：{target}")
        return 0

    target.mkdir(parents=True, exist_ok=True)
    print(f"下载 {REPO} → {target}")
    path = snapshot_download(repo_id=REPO, local_dir=str(target),
                             allow_patterns=FILES, resume_download=True)
    print(f"完成：{path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
