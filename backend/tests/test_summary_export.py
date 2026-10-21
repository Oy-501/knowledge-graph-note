"""图谱总结与导出的交付质量

总结链路（结构总结 → Mermaid 流程图 → AI 摘要 → md/docx/pptx/json）是这套系统
对外的**最终交付物**：会进论文、进汇报、进别人的大模型上下文。
所以这里守的不是「代码能跑」，而是「产物能看」：

  · 六种导出都要能出，且非空 —— 少一种就是用户拿到半份东西
  · 空图谱要给出可读的说明，不能 500、也不能留一页白板
  · 同一概念不能在枢纽榜/样例里重复出现（同名不同 id 的节点是常态）
  · 导出的参数必须与页面上看到的一致（曾经导出写死 6 条主线，预览却按用户选的来）
  · 产物要落在配置指定的目录（不然测试会挤掉用户自己的导出）

已抓到过的真实缺陷都钉在这里：同名重复、导出参数不一致、PPT 空节留白。
"""
import json
import re

import pytest

from app.config import settings


# ---------------------------------------------------------------- 造图

def _node(db, fid, title, level=3, domain="database"):
    from app.models.models import Node

    n = Node(user_id=1, file_id=fid, entity=title, title=title, level=level,
             domain=domain, description=f"{title} 的说明", keywords=[title],
             entities=[], upload_time=1700000000)
    db.add(n)
    db.flush()
    return n


def _link(db, a, b, rel="related", score=0.5):
    from app.models.models import Link

    db.add(Link(source_id=a.id, target_id=b.id, relation_type=rel,
                relation_label={"prerequisite": "前置知识", "theory": "理论基础",
                                "implementation": "实现关系", "related": "相关"}.get(rel, rel),
                score=score, is_render=True))
    db.flush()


@pytest.fixture()
def rich_graph(db, make_file):
    """一个有枢纽、有连通簇、能走出学习主线的图谱。

    刻意让「索引」出现两次（同名不同 id、不同文件）—— 这正是过去枢纽榜
    出现「索引、索引」的原因。
    """
    f1 = make_file("g1.md", nodes=0)
    f2 = make_file("g2.md", nodes=0)

    n1 = _node(db, f1, "索引", 2, "database")
    n2 = _node(db, f1, "B+ 树", 2, "database")
    n3 = _node(db, f1, "查询优化", 3, "database")
    n4 = _node(db, f1, "最左前缀", 3, "database")
    n5 = _node(db, f1, "索引失效", 3, "database")
    n6 = _node(db, f2, "缓存", 2, "system")
    n7 = _node(db, f2, "淘汰策略", 3, "system")
    n8 = _node(db, f2, "索引", 2, "database")      # 同名，故意
    n10 = _node(db, f2, "缓存穿透", 3, "system")
    _node(db, f1, "孤点", 3, "misc")

    # 主线 1：索引 → B+ 树 → 查询优化 → 最左前缀
    _link(db, n1, n2, "prerequisite", 0.80)
    _link(db, n2, n3, "theory", 0.70)
    _link(db, n3, n4, "implementation", 0.70)
    # 主线 2：缓存 → 淘汰策略 → 缓存穿透
    _link(db, n6, n7, "implementation", 0.70)
    _link(db, n7, n10, "implementation", 0.70)
    # 让两处「索引」都有度数，才可能同时挤进枢纽榜
    _link(db, n1, n6, "theory", 0.75)
    _link(db, n1, n5, "related", 0.50)
    _link(db, n8, n6, "related", 0.50)
    _link(db, n8, n7, "related", 0.50)
    db.commit()
    return {"files": (f1, f2)}


@pytest.fixture()
def sparse_graph(db, make_file):
    """有点、没关联：枢纽/簇/主线三节都会是空的。"""
    fid = make_file("sparse.md", nodes=0)
    for name in ("甲", "乙", "丙"):
        _node(db, fid, name, 3, "misc")
    db.commit()
    return fid


NOISE_TITLE = "笔记要定期整理成知识结构"


@pytest.fixture()
def noisy_graph(db, make_file):
    """含一条句子残骸的图。

    残骸刻意做成**度数最高**的节点：它最容易挤进枢纽榜，
    也最容易被选成学习主线的起点 —— 这两个位置都是「正面呈现」。
    """
    f1 = make_file("noisy.md", nodes=0)
    a = _node(db, f1, "索引", 2, "database")
    b = _node(db, f1, "B+ 树", 2, "database")
    c = _node(db, f1, "查询优化", 3, "database")
    noise = _node(db, f1, NOISE_TITLE, 3, "misc")
    _node(db, f1, "写文章之前先想清楚读者", 3, "misc")   # 度数为 0，落在负面清单里

    _link(db, noise, a, "prerequisite", 0.80)
    _link(db, noise, b, "theory", 0.70)
    _link(db, a, b, "prerequisite", 0.80)
    _link(db, b, c, "theory", 0.70)
    db.commit()
    return f1


def _summary(client, headers, **kw):
    r = client.post("/api/summary/build", json={"user_id": 1, **kw}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- 六种导出

@pytest.mark.parametrize("fmt", ["md", "docx", "pptx", "mermaid", "digest", "json"])
def test_every_export_succeeds_with_data(client, admin_headers, rich_graph, fmt):
    r = client.get("/api/summary/download", params={"fmt": fmt}, headers=admin_headers)
    assert r.status_code == 200, f"{fmt} 导出失败：{r.status_code} {r.text[:200]}"
    assert len(r.content) > 200, f"{fmt} 产物太小（{len(r.content)} 字节），像是空文件"
    assert r.headers.get("content-disposition"), f"{fmt} 没带下载文件名"


@pytest.mark.parametrize("fmt", ["md", "docx", "pptx", "mermaid", "digest", "json"])
def test_every_export_survives_an_empty_graph(client, admin_headers, fmt):
    """空图谱必须友好降级。

    这是用户第一次打开总结页最可能遇到的状态，报 500 会让人以为系统坏了。
    """
    r = client.get("/api/summary/download", params={"fmt": fmt, "user_id": 999},
                   headers=admin_headers)
    assert r.status_code == 200, f"空图谱导出 {fmt} 报错：{r.status_code} {r.text[:200]}"
    assert r.content, f"空图谱导出 {fmt} 产出空文件"


def test_empty_graph_summary_says_what_to_do(client, admin_headers):
    r = client.get("/api/summary/download", params={"fmt": "md", "user_id": 999},
                   headers=admin_headers)
    text = r.content.decode("utf-8")
    assert "暂无知识点" in text, f"空图谱的文档没有给提示：{text[:200]}"


def test_mermaid_for_empty_graph_is_still_renderable(client, admin_headers):
    """空图谱也要给一段能渲染的 Mermaid，而不是空串。

    空串贴进编辑器只会报语法错，用户不知道是图空还是工具坏。
    """
    data = _summary(client, admin_headers, user_id=999)
    assert data["empty"] is True
    assert data["mermaid"].strip().startswith("flowchart"), f"不是合法 Mermaid：{data['mermaid']!r}"
    assert "暂无知识点" in data["mermaid"]


# ---------------------------------------------------------------- Mermaid

def test_mermaid_carries_real_relation_types(client, admin_headers, rich_graph):
    """边标签必须写真实关系类型，不能一律「相关」。

    AI 靠这个判断先学谁、谁支撑谁；全写成「相关」就等于没给信息。
    """
    data = _summary(client, admin_headers)
    mmd = data["mermaid"]
    assert mmd.strip().startswith("flowchart TD"), mmd[:120]
    assert "subgraph" in mmd, "没有按阶段/领域分组"
    labels = set(re.findall(r"\|\s*([^|]+?)\s*\|", mmd))
    assert labels - {""}, f"边上没有关系标签：{mmd[:300]}"
    assert any(lbl in {"前置知识", "理论基础", "实现关系"} for lbl in labels), (
        f"没有出现任何强关系标签，只有：{labels}"
    )


# ---------------------------------------------------------------- 去重

def test_same_title_nodes_do_not_repeat_in_hubs(client, admin_headers, rich_graph):
    """同名概念在枢纽榜里只能出现一次。

    图谱里同名不同 id 是常态（同一概念在多份文档里各被抽一次），
    不去重的话榜上会出现「索引、索引」—— 读者会以为统计算错了。
    """
    hubs = _summary(client, admin_headers)["summary"]["hubs"]
    titles = [h["title"] for h in hubs]
    assert titles, "造了带枢纽的图却一个枢纽都没有，用例失去意义"
    assert len(titles) == len(set(titles)), f"枢纽榜有重复标题：{titles}"


def test_same_title_nodes_do_not_repeat_in_level_samples(client, admin_headers, rich_graph):
    levels = _summary(client, admin_headers)["summary"]["levels"]
    for lv in levels:
        samples = lv["samples"]
        assert len(samples) == len(set(samples)), f"L{lv['level']} 样例有重复：{samples}"


def test_same_title_nodes_do_not_repeat_in_domain_and_cluster_lists(client, admin_headers, rich_graph):
    summary = _summary(client, admin_headers)["summary"]
    for d in summary["domains"]:
        assert len(d["top_nodes"]) == len(set(d["top_nodes"])), f"领域 {d['domain']} 代表点重复"
    for i, c in enumerate(summary["clusters"], 1):
        titles = [n["title"] for n in c["top_nodes"]]
        assert len(titles) == len(set(titles)), f"簇 {i} 代表点重复：{titles}"


def test_isolated_list_is_deduplicated_but_count_stays_honest(client, admin_headers, rich_graph):
    """孤立点列表去重，但计数仍是真实节点数。

    两件事不能混：列表是「待补全清单」（同一个概念列三遍没意义），
    计数是「有多少个知识点没有关联」（节点级事实）。
    """
    ov = _summary(client, admin_headers)["summary"]["overview"]
    isolated = _summary(client, admin_headers, user_id=1)["summary"]["isolated"]
    titles = [n["title"] for n in isolated]
    assert len(titles) == len(set(titles)), f"孤立点列表有重复：{titles}"
    assert ov["isolated_count"] >= len(titles), (
        f"孤立计数 {ov['isolated_count']} 小于去重后的列表长度 {len(titles)}"
    )


# ---------------------------------------------------------------- 噪音标题

def _presented_titles(summary: dict) -> list:
    """总结里所有「正面呈现」的位置上出现的标题。"""
    out = [h["title"] for h in summary["hubs"]]
    for lv in summary["levels"]:
        out += lv["samples"]
    for d in summary["domains"]:
        out += d["top_nodes"]
    for c in summary["clusters"]:
        out += [n["title"] for n in c["top_nodes"]]
    for p in summary["paths"]:
        out += [s["title"] for s in p["steps"]]
    return out


def test_sentence_fragment_is_never_presented_as_knowledge(client, admin_headers, noisy_graph):
    """句子残骸不能被摆成「核心枢纽 / 代表知识点 / 学习主线的一步」。

    抽取阶段已经不再产这种节点，但库里**已有的**节点还在 ——
    总结这一层必须也认得出，否则历史数据永远脏。
    """
    summary = _summary(client, admin_headers)["summary"]
    shown = _presented_titles(summary)
    assert shown, "总结里什么都没呈现，用例失去意义"
    assert NOISE_TITLE not in shown, f"句子残骸被当成知识点展示了：{shown}"


def test_noise_filter_does_not_change_the_counts(client, admin_headers, noisy_graph):
    """过滤只影响「选取」，不改「计数」。

    图谱里有多少个节点是事实。把残骸从展示里拿掉之后，
    总数如果也跟着变小，就变成「为了好看而修饰数据」了。
    """
    ov = _summary(client, admin_headers)["summary"]["overview"]
    assert ov["node_count"] == 5, f"节点计数被过滤影响了：{ov['node_count']}"


def test_negative_lists_still_show_everything(client, admin_headers, noisy_graph):
    """负面清单（孤立点/待补全）**不**过滤 —— 那里需要看全，用户才能顺手改掉标题。"""
    isolated = _summary(client, admin_headers)["summary"]["isolated"]
    titles = [n["title"] for n in isolated]
    assert "写文章之前先想清楚读者" in titles, f"孤立点清单被过滤了：{titles}"


# ---------------------------------------------------------------- 参数一致性

def test_export_uses_the_same_params_as_the_preview(client, admin_headers, rich_graph):
    """导出必须跟预览用同一套参数。

    真出过：页面把「主线数」调到 1，预览 1 条，导出的 PPT 却是 6 条 ——
    因为导出接口根本没接这个参数，写死了 6。
    """
    preview = _summary(client, admin_headers, max_paths=1)["summary"]
    assert len(preview["paths"]) == 1, f"预览没按 max_paths 走：{len(preview['paths'])} 条"

    r = client.get("/api/summary/download",
                   params={"fmt": "json", "max_paths": 1}, headers=admin_headers)
    exported = json.loads(r.content.decode("utf-8"))
    assert len(exported["paths"]) == len(preview["paths"]), (
        f"导出 {len(exported['paths'])} 条主线，预览却是 {len(preview['paths'])} 条"
    )

    r = client.get("/api/summary/download",
                   params={"fmt": "mermaid", "max_paths": 1}, headers=admin_headers)
    # 主线在流程图里表现为边标签；条数对不上时边也会明显变少
    assert r.content, "mermaid 导出为空"


def test_max_paths_out_of_range_is_rejected(client, admin_headers, rich_graph):
    """越界参数必须报错，而不是被静默夹到边界值。

    静默夹取会让「我设了 100 条」和「真的给了 100 条」看起来一样。
    """
    for bad in (0, -1, 999):
        r = client.get("/api/summary/download",
                       params={"fmt": "md", "max_paths": bad}, headers=admin_headers)
        assert r.status_code == 422, f"max_paths={bad} 竟然返回 {r.status_code}"


def test_unknown_group_by_is_rejected(client, admin_headers):
    """未知分组方式必须报错。

    以前传任何值都会静默回落成「按层级分组」，看着成功了其实没按用户要的来。
    """
    r = client.get("/api/summary/download",
                   params={"fmt": "mermaid", "group_by": "zzz"}, headers=admin_headers)
    assert r.status_code == 422, f"未知 group_by 竟然返回 {r.status_code}"


# ---------------------------------------------------------------- PPT 反查

def _slides(path):
    from pptx import Presentation

    return Presentation(path)


def _ppt_text(slide):
    parts = []
    for sh in slide.shapes:
        if sh.has_text_frame and sh.text_frame.text.strip():
            parts.append(sh.text_frame.text.strip())
        if getattr(sh, "has_table", False) and sh.has_table:
            for row in sh.table.rows:
                for cell in row.cells:
                    parts.append(cell.text)
    return "\n".join(parts)


def test_pptx_is_16_9_and_has_a_dense_flowchart_page(client, admin_headers, rich_graph, workdir):
    """PPT 尺寸与流程图页。

    流程图页是这份 PPT 的核心 —— 用形状和箭头原生画的，不是贴图。
    它一旦退化成只有标题的空页，整份演示就失去意义，所以专门断言形状数。
    """
    r = client.get("/api/summary/download", params={"fmt": "pptx"}, headers=admin_headers)
    path = workdir / "s.pptx"
    path.write_bytes(r.content)

    prs = _slides(str(path))
    assert abs(prs.slide_width / 914400 - 13.333) < 0.01, "不是 16:9"
    assert abs(prs.slide_height / 914400 - 7.5) < 0.01, "不是 16:9"
    assert len(prs.slides) >= 8, f"只有 {len(prs.slides)} 页，章节疑似被跳过"

    flow = [s for s in prs.slides if "总结流程图" in _ppt_text(s)]
    assert flow, "找不到流程图页"
    shapes = list(flow[0].shapes)
    # 流程图页 = 标题 + 每条主线的节点框与箭头。有 2 条主线时形状数应显著多于普通页。
    assert len(shapes) >= 10, f"流程图页只有 {len(shapes)} 个形状，图形没画出来"


def _slide_titled(prs, title: str):
    """按**整行等于标题**定位页，不用子串匹配。

    子串会误伤封面页：封面副标题里有「知识簇 0」这类字样，
    搜「知识簇」会先命中封面，于是断言测的是一张无关的页。
    """
    for slide in prs.slides:
        if title in [ln.strip() for ln in _ppt_text(slide).splitlines()]:
            return slide
    return None


def test_pptx_empty_sections_explain_themselves(client, admin_headers, sparse_graph, workdir):
    """没有数据的章节要说明原因，不能留一页只剩标题的白板。

    白板看起来像「导出坏了」，而不是「图谱里本来就没有这类结构」。
    """
    r = client.get("/api/summary/download", params={"fmt": "pptx"}, headers=admin_headers)
    path = workdir / "sparse.pptx"
    path.write_bytes(r.content)
    prs = _slides(str(path))

    for title in ("核心枢纽知识点", "知识簇", "总结流程图（学习主线）"):
        slide = _slide_titled(prs, title)
        assert slide is not None, f"找不到「{title}」页"
        text = _ppt_text(slide)
        lines = [ln for ln in text.splitlines() if ln.strip()]
        # 标题 + 副标题 + 至少一段说明
        assert len(lines) >= 3, f"「{title}」页只有 {len(lines)} 行，是空页：{lines}"
        assert any("还没有" in ln for ln in lines), (
            f"「{title}」页没说清楚为什么是空的：{lines}"
        )


# ---------------------------------------------------------------- 产物落盘

def test_exports_land_in_the_configured_directory(client, admin_headers, rich_graph):
    """产物必须落在配置指定的目录里。

    测试靠 `EXPORT_DIR` 环境变量隔离：没隔离的话，跑一次导出用例就会
    往用户自己的产物目录里塞文件，而那个目录是按 mtime 只留最近 N 个的 ——
    用户原有的导出会被挤掉。
    """
    from app.services.summary_export import export_dir

    target = export_dir()
    assert target == settings.resolved_export_dir
    assert "kg-pytest" in target, f"测试没有隔离导出目录，会写进正式产物目录：{target}"

    r = client.get("/api/summary/download", params={"fmt": "md"}, headers=admin_headers)
    assert r.status_code == 200
    import os

    files = [f for f in os.listdir(target) if f.endswith(".md")]
    assert files, f"导出后目录里没有 .md 产物：{os.listdir(target)}"
