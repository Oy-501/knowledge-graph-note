"""功能边界矩阵：输入极值、非法参数、退化路径。

跑法：py scripts/boundary_matrix.py
不联网、不写库，纯函数与轻量服务调用。
"""
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

PASS, FAIL = "PASS", "FAIL"
ROWS = []


def run(name, fn):
    """执行一个用例并输出 PASS/FAIL。"""
    try:
        detail = fn()
        ROWS.append((name, PASS))
        print(f"PASS  {name}" + (f" — {detail}" if detail else ""))
    except AssertionError as exc:
        ROWS.append((name, FAIL))
        print(f"FAIL  {name} — {exc}")
    except Exception as exc:  # noqa: BLE001 - 边界矩阵要记录而不是中断
        ROWS.append((name, FAIL))
        print(f"ERROR {name} — {type(exc).__name__}: {exc}")


def expect_error(fn, needle=""):
    """断言调用会抛出指定异常。"""
    try:
        fn()
    except Exception as exc:  # noqa: BLE001
        assert needle in str(exc), f"异常信息不含「{needle}」：{exc}"
        return type(exc).__name__
    raise AssertionError("应当拒绝但没有抛异常")


# ---------------------------------------------------------------- 分页


def _paging():
    """分页边界用例。"""
    from app.services.errors import clamp_paging

    run("分页 limit=0", lambda: _eq(clamp_paging(0), (30, 0)))
    run("分页 limit=-1", lambda: _eq(clamp_paging(-1), (30, 0)))
    run("分页 limit=201 截到 200", lambda: _eq(clamp_paging(201), (200, 0)))
    run("分页 limit=1 保留", lambda: _eq(clamp_paging(1), (1, 0)))
    run("分页 limit='abc' 回落默认", lambda: _eq(clamp_paging("abc"), (30, 0)))
    run("分页 limit=None", lambda: _eq(clamp_paging(None, None), (30, 0)))
    run("分页 offset=-5 归零", lambda: _eq(clamp_paging(10, -5), (10, 0)))


def _eq(actual, expected):
    """断言相等并返回可读值。"""
    assert actual == expected, f"{actual!r} != {expected!r}"
    return str(actual)


# ---------------------------------------------------------------- LIKE 转义


def _like():
    """LIKE 转义边界用例。"""
    from app.services.errors import escape_like

    def check(raw, must_contain):
        """断言转义结果包含目标片段。"""
        out = escape_like(raw)
        assert must_contain in out, f"{raw!r} → {out!r} 缺 {must_contain!r}"
        return out

    run("LIKE 转义 %", lambda: check("%", "\\%"))
    run("LIKE 转义 _", lambda: check("_", "\\_"))
    run("LIKE 转义 反斜杠", lambda: check("\\", "\\\\"))
    run("LIKE 混合字符", lambda: check("a%b_c", "\\%"))
    run("LIKE 空值", lambda: check("", ""))


# ---------------------------------------------------------------- 行角色


def _role():
    """行角色边界用例。"""
    from app.services.text_role import line_role

    def eq(line, nxt, expected):
        """断言行角色符合预期。"""
        got = line_role(line, nxt)
        assert got == expected, f"{line!r}/{nxt!r} → {got}，应为 {expected}"
        return got

    run("行角色 空串", lambda: eq("", "", "noise"))
    run("行角色 纯空格", lambda: eq("   ", "", "noise"))
    run("行角色 # 标题", lambda: eq("# 知识", "", "heading"))
    run("行角色 单个 #", lambda: eq("#", "", "heading"))
    run("行角色 编号标题", lambda: eq("一、概念", "", "heading"))
    run("行角色 数字标题", lambda: eq("3. 工具", "", "heading"))
    run("行角色 短行+更长下一行", lambda: eq("基础", "这是一段更长的正文说明。", "heading"))
    run("行角色 短行+等长下一行", lambda: eq("支持多种格式", "支持增量更新", "body"))
    run("行角色 完整句", lambda: eq("这是一句完整的话。", "", "body"))
    run("行角色 25 字无标点+更长下一行", lambda: eq("这是一个超过二十四字但内容仍然像标题的短句", "这是一段明显更长的正文内容用于对照。", "body"))


# ---------------------------------------------------------------- 摘要


def _summary():
    """摘要边界用例。"""
    from app.services.text_summary import summarize

    run("摘要 空文本", lambda: _summary_eq(summarize(""), 0))
    run("摘要 纯空白", lambda: _summary_eq(summarize("   \n\n  "), 0))
    run("摘要 单句", lambda: _summary_eq(summarize("光合作用是植物合成有机物的过程。", 5), 1))
    run("摘要 max_sentences=0", lambda: _summary_eq(summarize("第一句。第二句。第三句。", 0), 0))
    run("摘要 max_sentences=-1", lambda: _summary_eq(summarize("第一句。第二句。第三句。", -1), 0))
    run("摘要 max_sentences=100", lambda: _summary_upto(summarize("第一句。第二句。第三句。", 100), 3))
    run("摘要 max_chars=1", lambda: _summary_upto(summarize("第一句。第二句。第三句。", 5, 1), 1))
    run("摘要 纯标题", lambda: _summary_eq(summarize("# 标题\n\n## 子标题\n", 5), 0))


def _summary_eq(out, expect):
    """断言摘要句数。"""
    assert len(out["key_points"]) == expect, f"{len(out['key_points'])} != {expect}"
    return f"{len(out['key_points'])} 句"


def _summary_upto(out, limit):
    """断言摘要句数不超过上限。"""
    assert 0 <= len(out["key_points"]) <= limit, len(out["key_points"])
    return f"{len(out['key_points'])} 句（≤{limit}）"


# ---------------------------------------------------------------- 切割


def _split():
    """切割边界用例。"""
    from app.services.file_splitter import plan_split, validate_plan

    run("切割 空文本", lambda: _split_case(plan_split("", 100, 1000), 1))
    run("切割 单行短文本", lambda: _split_case(plan_split("一句话。", 100, 1000), 1))

    huge = "很长的句子" * 5000
    run("切割 单行超长", lambda: _split_not_crash(plan_split(huge, 10, 100, max_pieces=5, overlap_lines=1), huge))

    no_punct = "\n".join(f"第{i}行没有任何句末标点" for i in range(300))
    run("切割 无标点 300 行（允许撕裂，不许漏行）",
        lambda: _split_cover_ok(plan_split(no_punct, 50, 100000, max_pieces=20), no_punct))

    run("切割 target_lines=1（允许预算截断）",
        lambda: _split_truncated_ok(plan_split("\n".join(f"第{i}句。" for i in range(50)), 1, 100000, max_pieces=10)))

    run("切割 max_pieces=0", lambda: _max_pieces_positive(plan_split("\n".join(f"第{i}句。" for i in range(100)), 10, 100000, max_pieces=0)))
    run("切割 overlap 大于片长", lambda: _overlap_bounded(plan_split("\n".join(f"第{i}句。" for i in range(200)), 50, 100000, max_pieces=10, overlap_lines=1000)))
    run("切割 overlap=-1", lambda: _split_valid(plan_split("\n".join(f"第{i}句。" for i in range(100)), 20, 100000, max_pieces=10, overlap_lines=-1), "\n".join(f"第{i}句。" for i in range(100))))
    run("切割 跨行句不撕裂", lambda: _torn_zero("\n".join(["前半句", "后半句结束。"] * 100)))


def _split_case(plan, expect_pieces):
    """断言分片数。"""
    assert len(plan["pieces"]) == expect_pieces, plan
    return f"{len(plan['pieces'])} 片"


def _split_not_crash(plan, text):
    """断言超长单行不崩。"""
    assert plan["pieces"], "没有分片"
    return f"{len(plan['pieces'])} 片"


def _split_valid(plan, text):
    """断言切割方案校验通过。"""
    from app.services.file_splitter import validate_plan
    report = validate_plan(plan, text)
    assert report["ok"], report
    return f"{len(plan['pieces'])} 片"


def _split_cover_ok(plan, text):
    """无标点文本允许句中切点，但不能漏行或出现空片"""
    from app.services.file_splitter import validate_plan
    report = validate_plan(plan, text)
    assert not report["gaps"], report
    assert not report["empty_pieces"], report
    return f"{len(plan['pieces'])} 片，torn={len(report['torn_cuts'])}"


def _split_truncated_ok(plan):
    """预算截断时允许尾部未覆盖，但必须显式标记"""
    from app.services.file_splitter import validate_plan
    if plan.get("truncated_by_limit"):
        return f"截断，{len(plan['pieces'])} 片"
    report = validate_plan(plan, "\n".join(f"第{i}句。" for i in range(50)))
    assert report["ok"], report
    return f"{len(plan['pieces'])} 片"


def _max_pieces_positive(plan):
    """断言 max_pieces=0 仍产出一片。"""
    assert len(plan["pieces"]) >= 1, f"max_pieces=0 产出了 {len(plan['pieces'])} 片"
    return f"{len(plan['pieces'])} 片"


def _overlap_bounded(plan):
    """断言重叠过大时片数不膨胀。"""
    assert len(plan["pieces"]) <= 10, f"片数异常膨胀：{len(plan['pieces'])}"
    assert all(p["lines"] > 0 for p in plan["pieces"]), "出现空片"
    return f"{len(plan['pieces'])} 片"


def _torn_zero(text):
    """断言跨行句不被撕裂。"""
    from app.services.file_splitter import plan_split, validate_plan
    plan = plan_split(text, 50, 100000, max_pieces=20, overlap_lines=2)
    report = validate_plan(plan, text)
    assert not report["torn_cuts"], report
    return "torn=0"


# ---------------------------------------------------------------- 存在性


def _existence():
    """存在性边界用例。"""
    from app.services.web_existence import check_existence

    def eq(entity, desc, result, expected):
        """断言存在性状态。"""
        got = check_existence(entity, desc, result)["status"]
        assert got == expected, f"{entity!r} → {got}，应为 {expected}"
        return got

    offline = {"online": False, "results": []}
    empty = {"online": True, "provider": "t", "results": []}
    noise = {"online": True, "provider": "t", "results": [
        {"title": "无关", "url": "https://a.com", "snippet": "无关内容"}]}

    run("存在性 空实体", lambda: eq("", "", noise, "unverified"))
    run("存在性 单字", lambda: eq("A", "", noise, "unverified"))
    run("存在性 离线", lambda: eq("RAG", "描述", offline, "unavailable"))
    run("存在性 结果为空", lambda: eq("RAG", "描述", empty, "unverified"))
    run("存在性 英文子串误命中", lambda: eq("RAG", "", {"online": True, "provider": "t", "results": [
        {"title": "Storage", "url": "https://a.com", "snippet": "storage layout"}]}, "unverified"))
    run("存在性 同域名不确认", lambda: eq("检索增强生成", "检索增强生成是一种方法", {"online": True, "provider": "t", "results": [
        {"title": "检索增强生成A", "url": "https://a.com/1", "snippet": "检索增强生成是一种方法"},
        {"title": "检索增强生成B", "url": "https://a.com/2", "snippet": "检索增强生成是一种方法"}]}, "probable"))
    run("存在性 多域名+一致", lambda: eq("检索增强生成", "检索增强生成是一种方法", {"online": True, "provider": "t", "results": [
        {"title": "检索增强生成A", "url": "https://a.com/1", "snippet": "检索增强生成是一种方法"},
        {"title": "检索增强生成B", "url": "https://b.com/2", "snippet": "检索增强生成是一种方法"}]}, "confirmed"))
    run("存在性 强否定", lambda: eq("某伪概念", "描述", {"online": True, "provider": "t", "results": [
        {"title": "某伪概念", "url": "https://a.com", "snippet": "某伪概念并不存在，属于谣言"}]}, "contradicted"))


# ---------------------------------------------------------------- 认证


def _auth():
    """认证字段长度边界。"""
    from app.services.auth_service import _validate_credentials

    run("用户名 1 字", lambda: expect_error(lambda: _validate_credentials("a", "123456")))
    run("用户名 2 字", lambda: _validate_credentials("ab", "123456") and "ok")
    run("用户名 32 字", lambda: _validate_credentials("a" * 32, "123456") and "ok")
    run("用户名 33 字", lambda: expect_error(lambda: _validate_credentials("a" * 33, "123456")))
    run("密码 5 位", lambda: expect_error(lambda: _validate_credentials("abc", "12345")))
    run("密码 72 位", lambda: _validate_credentials("abc", "a" * 72) and "ok")
    run("密码 73 位", lambda: expect_error(lambda: _validate_credentials("abc", "a" * 73)))


# ---------------------------------------------------------------- 抽取


def _extract():
    """抽取退化输入边界。"""
    from app.services.parser import extract_entity, extract_nodes_from_text

    run("抽取 空文本", lambda: _nodes_empty(""))
    run("抽取 纯标题", lambda: _nodes_empty("# 标题\n\n## 子标题\n"))
    run("抽取 纯标点", lambda: _nodes_empty("。。！！？？\n\n，；、\n"))
    run("抽取 标题不兜底", lambda: _no_heading_fallback())
    run("抽取 超长句", lambda: _nodes_not_crash("这是一个很长的句子" * 300 + "。"))
    run("抽取 英文句子", lambda: _nodes_not_crash("Retrieval augmented generation combines retrieval and generation."))


def _nodes_empty(text):
    """断言退化输入不产节点。"""
    from app.services.parser import extract_nodes_from_text
    nodes, _ = extract_nodes_from_text(text, 1, 1)
    assert nodes == [], [n["entity"] for n in nodes]
    return "0 节点"


def _nodes_not_crash(text):
    """断言超长或英文句不崩。"""
    from app.services.parser import extract_nodes_from_text
    nodes, _ = extract_nodes_from_text(text, 1, 1)
    return f"{len(nodes)} 节点"


def _no_heading_fallback():
    """断言标题不回落成节点。"""
    from app.services.parser import extract_nodes_from_text
    nodes, _ = extract_nodes_from_text("# 知识整理\n\n笔记要定期整理成知识结构，否则只是资料堆积。\n", 1, 1)
    entities = [n["entity"] for n in nodes]
    assert "知识整理" not in entities, entities
    return "标题未混入"


# ---------------------------------------------------------------- 其他


def _misc():
    """其他边界：余弦、净化、导出。"""
    from app.services.security import sanitize_request_id
    from app.services.vector_engine import cosine_similarity
    from app.services.summary_export import to_markdown

    run("余弦 零向量", lambda: _eq(cosine_similarity([0, 0], [1, 0]), 0.0))
    run("余弦 维度不等", lambda: _eq(cosine_similarity([1, 0], [1, 0, 0]), 0.0))
    run("request_id 非法字符", lambda: _sanitize(sanitize_request_id("../../etc/passwd")))
    run("导出 空 summary", lambda: _export_empty(to_markdown))


def _sanitize(value):
    # request_id 只进日志，不参与路径拼接；要求：不含路径分隔符与换行
    """断言 request_id 不含路径分隔符。"""
    for ch in ("/", "\\", "\n", "\r"):
        assert ch not in value, value
    return value[:40]


def _export_empty(to_markdown):
    """断言空总结可导出。"""
    md = to_markdown({"overview": {"node_count": 0, "link_count": 0, "file_count": 0},
                      "empty": True, "message": "空图谱"})
    assert isinstance(md, str) and md, "导出为空"
    return f"{len(md)} 字符"


def main() -> int:
    """命令行入口：跑完矩阵并汇总。"""
    print("=" * 70)
    print("功能边界矩阵")
    print("=" * 70)
    _paging()
    _like()
    _role()
    _summary()
    _split()
    _existence()
    _auth()
    _extract()
    _misc()

    passed = sum(1 for _, s in ROWS if s == PASS)
    print("-" * 70)
    print(f"结果：{passed}/{len(ROWS)} 通过")
    fails = [n for n, s in ROWS if s == FAIL]
    if fails:
        print("失败用例：")
        for n in fails:
            print("  -", n)
    return 0 if passed == len(ROWS) else 1


if __name__ == "__main__":
    raise SystemExit(main())
