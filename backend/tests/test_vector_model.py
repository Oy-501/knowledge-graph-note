"""真语义模型路径（`transformers` 引擎）

其余向量用例固定走 tfidf 降级引擎 —— 真模型 470MB，每个测试进程都加载会拖慢测试。
代价是**真模型路径一度零覆盖**：降级编码的断言全绿，不代表装上模型之后也对。
本文件补上这一段。

三条设计约束：

1. **只断言「关系」，不断言数值。** 分数随模型版本变，钉死数值只会变成噪音。
   唯一例外是「区分度下限」—— 那是质量地板，跌破就说明模型没在干活。
2. **模型取不到就明确跳过，并打印原因**，不静默通过。跳过 = 这条覆盖本次没发生，
   必须在报告里说清楚，而不是伪装成绿色。
3. **对照集与 `scripts/vector_probe.py` 同源**（直接按路径导入那个模块），
   否则探针报 8/8、测试报别的，两边漂移。

代价：本模块约 15~20 秒（大头是 `import torch`）。
日常快速回路用 `py -m pytest -m "not slow_model"`。
"""
from __future__ import annotations

import importlib.util
import math
import statistics
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parent.parent

pytestmark = pytest.mark.slow_model


def _load_probe():
    """按路径导入探针模块，复用它的对照集，避免两处数据集各写一份后漂移。"""
    path = BACKEND / "scripts" / "vector_probe.py"
    spec = importlib.util.spec_from_file_location("_vector_probe", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


PROBE = _load_probe()
PARAPHRASE_PAIRS = PROBE.PARAPHRASE_PAIRS
UNRELATED_PAIRS = PROBE.UNRELATED_PAIRS


@pytest.fixture(scope="module")
def model_engine():
    """切到真模型。取不到就跳过（这是降级，不是通过）。"""
    from app.config import settings
    from app.services import vector_engine as ve

    saved = settings.VECTOR_BACKEND
    settings.VECTOR_BACKEND = "transformers"
    ok = ve.prepare(force=True)

    if not ok:
        settings.VECTOR_BACKEND = saved
        ve.prepare(force=True)          # 恢复原引擎，别把降级状态留给后续用例
        pytest.skip(f"真模型不可用，跳过真模型路径覆盖（原因：{ve.get_engine_info()['reason']}）")

    yield ve

    settings.VECTOR_BACKEND = saved
    ve.prepare(force=True)


def _sims(ve, pairs):
    return [ve.cosine_similarity(ve.encode(a), ve.encode(b)) for a, b in pairs]


# ---------------------------------------------------------------- 引擎身份

def test_engine_actually_is_the_model(model_engine):
    """必须先确认引擎真的切过去了，否则后面所有断言都在测降级路径。"""
    info = model_engine.get_engine_info()
    assert info["degraded"] is False, f"引擎没切到真模型：{info}"
    assert info["mode"] == "transformers"
    assert info["dim"] > 0


def test_dimension_comes_from_the_model_not_a_constant(model_engine):
    """维度必须从模型对象读，不能写死。

    踩过：`VECTOR_DIM` 被写死成 768，而实际模型是 384 维。
    写死的维度一旦与真实维度不符，向量落库后 cosine 恒为 0 ——
    表现是「换了模型反而全都不相似」，而代码里看不出任何问题。
    """
    info = model_engine.get_engine_info()
    vec = model_engine.encode("数据库索引可以加快查询速度")
    assert len(vec) == info["dim"], (
        f"编码出来的维度 {len(vec)} 与引擎声明的 {info['dim']} 不一致"
    )
    # 指纹里要带维度，否则维度变了但指纹没变 → 旧向量不会被判为陈旧
    assert str(info["dim"]) in info["signature"], (
        f"引擎指纹里没有维度，换维度后旧向量不会被识别为陈旧：{info['signature']}"
    )


def test_signature_carries_the_model_name(model_engine):
    from app.config import settings

    assert settings.VECTOR_MODEL in model_engine.engine_signature(), (
        "指纹里没有模型名 —— 换模型后旧向量不会被识别为陈旧"
    )


def test_vectors_are_unit_length_and_deterministic(model_engine):
    """归一化 + 确定性。缺了归一化，点积就不是余弦，分数随文本长度漂。"""
    text = "数据库索引可以加快查询速度"
    a, b = model_engine.encode(text), model_engine.encode(text)
    assert a == b, "同一段文本两次编码结果不一致（模型不在 eval 模式？）"
    norm = math.sqrt(sum(x * x for x in a))
    assert 0.9 < norm < 1.1, f"向量没有归一化：范数 {norm}"


# ---------------------------------------------------------------- 质量地板

def test_paraphrases_outrank_unrelated(model_engine):
    """核心断言：同一个意思的两种说法，必须比无关的两句更像。

    这是 β 维有没有信息量的判据。降级编码在旧实现下对中文恒为 0，
    在这里会立刻塌掉 —— 所以它同时也是「模型静默降级」的探针。
    """
    para = _sims(model_engine, PARAPHRASE_PAIRS)
    unrel = _sims(model_engine, UNRELATED_PAIRS)

    mean_para, mean_unrel = statistics.mean(para), statistics.mean(unrel)
    margin = mean_para - mean_unrel
    correct = sum(1 for p, u in zip(para, unrel) if p > u)

    # 地板刻意卡在「真模型」与「降级编码」之间：实测真模型 +0.591、降级 +0.161。
    # 取 0.30 是为了让这条断言能分辨「模型没在干活」——
    # 若取 0.15，模型静默退回降级编码时它照样绿灯，就白写了。
    assert margin > 0.30, (
        f"区分度只有 {margin:+.3f}（改写对均值 {mean_para:.3f}，无关对均值 {mean_unrel:.3f}）"
        f"—— 低于地板（真模型实测 +0.591、降级 +0.161），模型可能没在干活"
    )
    assert correct >= len(para) - 1, (
        f"排序正确率 {correct}/{len(para)} 过低；逐条："
        f"{[(round(p,3), round(u,3)) for p, u in zip(para, unrel)]}"
    )


def test_chinese_paraphrases_are_not_collapsed_to_zero(model_engine):
    """中文改写句不能整片塌到 0 —— 那是历史 bug 的指纹。

    旧降级实现按空白切词，中文整句变成 1 个词元，两个不同句子共享 0 个词元，
    相似度**恒为 0**。这条只要有一对塌到 0 就说明切词或模型出了问题。
    """
    scored = [(a, b, s) for (a, b), s in zip(PARAPHRASE_PAIRS, _sims(model_engine, PARAPHRASE_PAIRS))
              if not a.isascii()]
    assert scored, "对照集里没有中文改写对，这条用例失去意义"
    zero = [f"{a} || {b}" for a, b, s in scored if s <= 0.01]
    assert not zero, f"中文改写句相似度塌到 0（历史 bug 的指纹）：{zero}"


def test_english_pairs_also_work(model_engine):
    """模型是多语言的，英文改写对同样要分得开。

    加这条是因为「换成多语言模型」这个决定本身就是针对中文失效做的；
    若有人换成纯英文模型，中文会静默变随机向量，而英文反而更漂亮。
    """
    pairs = [(a, b) for a, b in PARAPHRASE_PAIRS if a.isascii()]
    if not pairs:
        pytest.skip("对照集里没有英文对")
    para = _sims(model_engine, pairs)
    assert statistics.mean(para) > 0.4, f"英文改写对整体偏低（实测 0.589）：{para}"


# ---------------------------------------------------------------- 跨引擎

def test_fallback_vectors_are_judged_stale_against_the_model(model_engine):
    """降级引擎产出的向量，在真模型引擎下必须被判为陈旧。

    维度不同 = 没法比 ≠ 不相似。这一条错了，就会出现「cosine 恒为 0
    被当成不相似」，而那正是换引擎后最容易被误读的现象。
    """
    from app.services.vector_engine import FALLBACK_DIM, embedding_is_stale

    fallback_sig = f"tfidf|ngram|{FALLBACK_DIM}|1"
    sig = model_engine.engine_signature()

    assert embedding_is_stale(fallback_sig, sig) is True, (
        "降级向量没有被判为陈旧 —— 换模型后旧向量会被拿去和新向量比"
    )
    assert embedding_is_stale(sig, sig) is False, "同引擎的向量不该被判为陈旧"
    assert embedding_is_stale(None, sig) is True, "没有指纹的向量必须先重建"
