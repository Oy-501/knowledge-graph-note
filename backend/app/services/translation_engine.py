"""离线翻译引擎：MarianMT（Helsinki-NLP/opus-mt-en-zh）本地推理。

为什么用本地模型：公共翻译服务在这台机器上全部不可用 ——
Google translate 与微软 Edge 接口不通，LibreTranslate 公共实例返回 HTML 报错，
Lingva 被 Cloudflare 挑战拦住；MyMemory 能通但会把 web.dev 译成「测长仪顶杆」。
本地模型质量中等，但稳定、离线、结果可复现。

模型按需加载并加锁：加载要几秒，并发首次调用不能重复加载。
"""
import threading
from pathlib import Path
from typing import Optional

from loguru import logger

from app.config import settings

# 模型会把技术词直译（Web → 网络、Portals → 门户），译后校正回通行说法
POST_FIX = (
    ("网络开发", "Web 开发"),
    ("网络应用", "Web 应用"),
    ("网络平台", "Web 平台"),
    ("网络无障碍", "Web 无障碍"),
    ("网络浏览器", "浏览器"),
    ("手持门户", "实战 Portals"),
    ("门户", "Portals"),
)

_PUNCT = str.maketrans({",": "，", ":": "：", "?": "？", ";": "；", "!": "！"})


def _polish(text: str) -> str:
    """修掉模型的两个固定毛病：技术词直译、英文标点。"""
    text = (text or "").strip()
    for src, dst in POST_FIX:
        text = text.replace(src, dst)
    return text.translate(_PUNCT) if text else text

_LOCK = threading.Lock()
_MODEL = None
_TOKENIZER = None
_DISABLED = False
_WARNED = False


def model_path() -> Path:
    return Path(settings.resolved_model_dir) / "opus-mt-en-zh"


def available() -> bool:
    """模型文件是否就位（不看内存里有没有加载）。"""
    return (model_path() / "config.json").exists()


def _ensure_loaded() -> bool:
    """加载模型；失败一次后不再重试，避免每次请求都卡几秒。"""
    global _MODEL, _TOKENIZER, _DISABLED, _WARNED

    if _MODEL is not None:
        return True
    if _DISABLED:
        return False
    if not available():
        return False

    with _LOCK:
        if _MODEL is not None:
            return True
        try:
            import torch
            from transformers import MarianMTModel, MarianTokenizer

            path = str(model_path())
            _TOKENIZER = MarianTokenizer.from_pretrained(path, local_files_only=True)
            _MODEL = MarianMTModel.from_pretrained(path, local_files_only=True)
            _MODEL.eval()
            torch.set_num_threads(max(1, (torch.get_num_threads() or 4)))
            logger.info(f"翻译模型已加载：{path}")
            return True
        except Exception as exc:
            _DISABLED = True
            if not _WARNED:
                _WARNED = True
                logger.warning(f"翻译模型不可用，降级为在线通道：{type(exc).__name__}: {exc}")
            return False


def translate(text: str, max_length: int = 512) -> Optional[str]:
    """英译中；模型不可用或推理失败时返回 None，由调用方决定降级。"""
    text = (text or "").strip()
    if not text:
        return None
    if not _ensure_loaded():
        return None

    try:
        import torch

        with torch.inference_mode():
            batch = _TOKENIZER([text], return_tensors="pt", padding=True,
                               truncation=True, max_length=max_length)
            generated = _MODEL.generate(**batch, max_length=max_length,
                                        num_beams=4, no_repeat_ngram_size=3)
            out = _TOKENIZER.batch_decode(generated, skip_special_tokens=True)[0]
        return _polish(out) or None
    except Exception as exc:
        logger.debug(f"本地翻译失败：{type(exc).__name__}: {exc}")
        return None


def warmup() -> bool:
    """预热：供服务启动或脚本提前加载，避免首个请求等几秒。"""
    return _ensure_loaded()
