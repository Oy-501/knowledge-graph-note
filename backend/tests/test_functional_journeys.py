"""功能测试：完整用户旅程

**与其余测试模块的分工**（这一层为什么必须单独存在）：

| 模块 | 守什么 |
|---|---|
| `test_*_engine` / `test_kb_index` / `test_inference` … | **单个模块的不变量**（改坏了会被抓到） |
| `test_api_contract` | **接口契约**（状态码、错误信封、响应头） |
| `test_paging` | **边界守卫**（负数分页、越界） |
| **本文件** | **功能到底能不能用** —— 从真实入口走完整旅程，断言每一步的**中间产物** |

模块全绿、契约全绿，功能仍可能整条断掉：上传返回 200 却没解析出节点、
总结能生成但导出是空文件、删除文件后连线残留成了悬空引用 ——
这些在单模块测试里一个都看不见，因为它们各自「都对」。

**所有旅程都从真实 HTTP 入口进**（走完整 ASGI 栈：CORS → request_id → 写守卫 →
路由 → 依赖注入 → 库），不直接调服务层函数。断言的是产物（节点数、连线、文件字节数），
不是「接口返回了 200」。
"""
import json

import pytest


# ---------------------------------------------------------------- 工具

DOC_A = """# 数据库索引笔记

## 基础

数据库索引可以加快查询速度。
B+ 树是索引最常用的数据结构。

## 优化

查询优化需要遵循最左前缀原则。
索引失效是因为对列使用了函数。
"""

DOC_B = """# 检索性能调优

## 记录

给常用的查询字段加上索引，检索会明显变快。
在字段上套函数会导致索引无法命中。
"""


def _upload(client, headers, name: str, content: str, mime="text/markdown"):
    """按真实前端的 multipart 表单上传一个文件。"""
    r = client.post(
        "/api/files/upload?user_id=1",
        files={"file": (name, content.encode("utf-8"), mime)},
        headers=headers,
    )
    return r


def _graph(client, headers):
    r = client.get("/api/graph?user_id=1", headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


def _summary(client, headers, **kw):
    r = client.post("/api/summary/build", json={"user_id": 1, **kw}, headers=headers)
    assert r.status_code == 200, r.text
    return r.json()


# ---------------------------------------------------------------- 旅程一：首次使用到导出

def test_journey_first_run_to_export(client, admin_headers):
    """主干链路：初始化/登录 → 上传 → 解析 → 图谱 → 总结 → 导出 → 删除。

    这是用户真正会走的那条路。每一步都断言**中间产物**：
    只断言状态码的话，「上传成功但一个节点都没抽出来」会一路绿灯到导出。
    """
    # ---- 1. 登录页的初始探测（匿名可访问）
    st = client.get("/api/auth/status")
    assert st.status_code == 200, st.text
    status = st.json()
    assert {"need_bootstrap", "authenticated", "registration_open"} <= set(status), status

    # ---- 2. 上传一份中文文档
    up = _upload(client, admin_headers, "索引笔记.md", DOC_A)
    assert up.status_code == 200, up.text
    body = up.json()
    file_id = body["file_id"]
    assert body["status"] == "parsing", f"上传后状态应是从解析中开始：{body}"

    # ---- 3. 文件列表：解析必须**真的完成**（后台任务跑在响应之后）
    # 终态是 done（模型注释：pending / parsing / done / error；前端也按 done|indexed 判完成）
    files = client.get("/api/files?user_id=1", headers=admin_headers).json()["files"]
    row = next((f for f in files if f["id"] == file_id), None)
    assert row is not None, f"上传的文件不在列表里：{[f['name'] for f in files]}"
    assert row["status"] in ("done", "indexed"), (
        f"解析没有完成：status={row['status']} note={row['parse_note']}"
    )

    # ---- 4. 知识点必须真的抽出来了（这是最容易被「200」掩盖的一步）
    nodes = client.get(f"/api/files/{file_id}/nodes?user_id=1",
                       headers=admin_headers).json()["nodes"]
    assert len(nodes) >= 3, f"只抽出 {len(nodes)} 个知识点，解析链路可疑：{[n['entity'] for n in nodes]}"
    assert row["node_count"] == len(nodes), (
        f"文件记录的 node_count({row['node_count']}) 与实际节点数({len(nodes)}) 不一致"
    )

    # ---- 5. 图谱接口能读到这些节点
    g = _graph(client, admin_headers)
    ids = {n["id"] for n in g["nodes"]}
    assert {n["id"] for n in nodes} <= ids, "文件节点没有出现在图谱里"
    assert "links" in g, f"图谱响应缺 links：{sorted(g)}"

    # ---- 6. 生成总结：口径必须与图谱一致
    s = _summary(client, admin_headers)
    assert s["ok"] is True and s["empty"] is False, s
    assert "ok" in s["ai_digest"] or s["ai_digest"].startswith("[KNOWLEDGE-GRAPH-SUMMARY"), \
        f"AI 摘要格式不对：{s['ai_digest'][:80]!r}"
    assert s["mermaid"].lstrip().startswith("flowchart"), f"Mermaid 不是流程图：{s['mermaid'][:60]!r}"
    assert s["summary"]["overview"]["node_count"] == len(ids), (
        f"总结的节点数 {s['summary']['overview']['node_count']} 与图谱 {len(ids)} 不一致"
    )

    # ---- 7. 六种导出：不是「有没有 200」，而是「产物有没有内容」
    for fmt, minimal in (("md", 200), ("docx", 2000), ("pptx", 2000),
                         ("mermaid", 20), ("digest", 50), ("json", 100)):
        r = client.get(f"/api/summary/download?fmt={fmt}", headers=admin_headers)
        assert r.status_code == 200, f"{fmt} 导出失败：{r.status_code}"
        assert len(r.content) >= minimal, (
            f"{fmt} 产物只有 {len(r.content)} 字节，像是空文件"
        )

    # json 导出要能解析，且节点数与总结一致
    rj = client.get("/api/summary/download?fmt=json", headers=admin_headers)
    exported = json.loads(rj.content.decode("utf-8"))
    assert exported["overview"]["node_count"] == len(ids), "导出的节点数与页面口径不一致"

    # ---- 8. 删除文件：回到干净状态（外键清理链路也要真的生效）
    d = client.delete(f"/api/files/{file_id}", headers=admin_headers)
    assert d.status_code == 200, d.text
    left = client.get(f"/api/files/{file_id}/nodes?user_id=1",
                      headers=admin_headers).json()["nodes"]
    assert left == [], f"删文件后节点残留 {len(left)} 个"
    assert _graph(client, admin_headers)["nodes"] == [], "删文件后图谱里还有节点"


def test_journey_session_channel_can_do_the_whole_flow(client, authed_headers):
    """生产主通道（`X-Session-Token`）必须能走完整条链路，不能是二等公民。

    上面的旅程用的是 `X-Admin-Token` —— 兼容保留的**脚本通道**。真实用户用的是
    登录会话。「会话能登录」不等于「会话能做事」：写守卫的判定顺序、`/api/admin/`
    前缀规则、`require_user` 只要有一处不对，登录照样 200，
    但上传 / 导出 / 后台全线 401-403，而只测登录的用例一条都发现不了。
    """
    h = authed_headers

    # 会话身份可读（走的是 require_user 那条路径）
    me = client.get("/api/auth/me", headers=h)
    assert me.status_code == 200, f"会话读不到自己：{me.status_code} {me.text[:200]}"

    # 主干：上传 → 解析 → 图谱 → 总结 → 导出，全程只用会话令牌
    up = _upload(client, h, "会话链路.md", DOC_A)
    assert up.status_code == 200, (
        f"管理员会话被写守卫挡住：{up.status_code} {up.text[:200]}"
    )
    fid = up.json()["file_id"]

    nodes = client.get(f"/api/files/{fid}/nodes?user_id=1", headers=h).json()["nodes"]
    assert len(nodes) >= 3, f"会话通道下没抽出知识点：{[n['entity'] for n in nodes]}"

    g = _graph(client, h)
    assert {n["id"] for n in nodes} <= {n["id"] for n in g["nodes"]}, \
        "会话通道下图谱读不到刚上传的节点"

    s = _summary(client, h)
    assert s["ok"] is True and s["empty"] is False, s
    assert s["summary"]["overview"]["node_count"] == len(g["nodes"]), \
        "会话通道下总结与图谱口径不一致"

    r = client.get("/api/summary/download?fmt=md", headers=h)
    assert r.status_code == 200 and len(r.content) >= 200, \
        f"会话通道导不出内容：{r.status_code} / {len(r.content)} 字节"

    # 同一个管理员身份，两条通道都得放行 ——
    # 写守卫认会话、后台守卫不认，就会出现「能上传却打不开后台」的割裂。
    adm = client.get("/api/admin/overview", headers=h)
    assert adm.status_code == 200, (
        f"管理员会话被后台守卫挡住：{adm.status_code} {adm.text[:160]}"
    )


def test_journey_two_files_link_together(client, admin_headers):
    """两份**说法不同、意思相同**的文档，应当被关联起来。

    这是产品最核心的价值主張（知识关联），也是「各模块都对但功能没用」的典型位置：
    解析对、向量对、连线对，但分数门槛或候选剪枝一改，两份文档就是连不上。
    """
    id_a = _upload(client, admin_headers, "索引笔记.md", DOC_A).json()["file_id"]
    id_b = _upload(client, admin_headers, "调优记录.md", DOC_B).json()["file_id"]
    assert id_a != id_b

    g = _graph(client, admin_headers)
    assert len(g["nodes"]) > 0, "两份文档都没抽到节点"

    cross = [l for l in g["links"] if l.get("source_file") == "知识库"
             or l.get("semantic_bridge")]
    assert cross, (
        "两份同主题文档之间一条关联都没建立。"
        f"（节点 {len(g['nodes'])} 个、连线 {len(g['links'])} 条）"
    )

    # 相关的内容才该连上：随便拉一份无关内容进来，不能连
    _upload(client, admin_headers, "食堂菜谱.md",
            "# 食堂菜谱\n\n今天中午的红烧肉有点咸。\n周末打算去爬山顺便拍点照片。\n")
    g2 = _graph(client, admin_headers)
    canteen = [n for n in g2["nodes"] if "红烧肉" in (n.get("entity") or "")]
    if canteen:
        bad = [l for l in g2["links"]
               if canteen[0]["id"] in (l.get("source"), l.get("target"))]
        assert not bad, f"无关内容被连上了：{bad}"


# ---------------------------------------------------------------- 旅程二：知识库驱动

def test_journey_kb_anchoring_drives_links(client, admin_headers):
    """知识库是知识权威源：先扩知识库，再上传文档，文档应被锚定并产生连线。

    走的是产品宣称的因果链（锚定 → 连线），而不是分开测「知识库能写入」
    与「连线接口能返回」。
    """
    # ---- 1. 往知识库加两个知识点（手工维护路径）
    # 注意：种子知识库里本来就有「索引」这类常见概念，接口对重复条目的处理是
    # 返回 200 + {"ok": false, "message": "…已存在"}（不是错误码）。
    # 所以这里两种结果都算走通，断言的是「拿到了条目 id」而不是「一定新建成功」——
    # 否则用例的结果会取决于种子语料里碰巧有没有这个词。
    ids = []
    for payload in (
        {"entity": "索引", "aliases": ["数据库索引"], "domain": "database", "level": 2,
         "definition": "加速数据检索的数据结构", "related_terms": ["B+ 树"]},
        {"entity": "B+ 树", "domain": "database", "level": 2,
         "definition": "索引最常用的树结构"},
    ):
        r = client.post("/api/kb/entries", json=payload, headers=admin_headers)
        assert r.status_code == 200, f"新增知识库条目失败：{r.status_code} {r.text[:200]}"
        assert r.json().get("id"), f"新增/已存在的条目都应返回 id：{r.json()}"
        ids.append(r.json()["id"])

    # ---- 2. 做一次真实用户动作：在知识库里搜刚才那个概念
    found = client.get("/api/kb/entries",
                       params={"keyword": "索引", "limit": 50},
                       headers=admin_headers)
    assert found.status_code == 200, found.text
    body = found.json()
    assert body["total"] >= 1, "知识库里搜「索引」一条都没有，新增的数据没进库"
    assert any("索引" in e["entity"] for e in body["entries"]), \
        f"搜到的条目里没有含「索引」的：{[e['entity'] for e in body['entries']][:10]}"

    # ---- 3. 上传提到这些概念的文档
    fid = _upload(client, admin_headers, "索引笔记.md", DOC_A).json()["file_id"]

    # ---- 4. 文件的知识画像应当记录「锚定到了哪些概念」
    prof = client.get(f"/api/kb/file/{fid}?user_id=1", headers=admin_headers)
    assert prof.status_code == 200, f"知识画像接口不可用：{prof.status_code} {prof.text[:200]}"

    # ---- 5. 图谱里应当出现由知识库建立的连线
    g = _graph(client, admin_headers)
    kb_links = [l for l in g["links"]
                if l.get("source_file") == "知识库" or l.get("semantic_bridge")]
    assert kb_links, (
        "上传的文档提到了知识库里的概念，却没有产生任何知识库连线。"
        f"（节点 {len(g['nodes'])}、连线 {len(g['links'])}）"
    )

    # ---- 6. 重建知识关联应当幂等：跑两次结果不能翻倍
    first = len(_graph(client, admin_headers)["links"])
    client.post("/api/kb/rebuild", json={"user_id": 1}, headers=admin_headers)
    second = len(_graph(client, admin_headers)["links"])
    assert second == first, f"重建关联不幂等：{first} → {second}"


# ---------------------------------------------------------------- 旅程三：笔记生命周期

def test_journey_note_lifecycle(client, admin_headers):
    """工作台的笔记：存 → 列 → 读 → 校验 → 删。"""
    save = client.post("/api/notes/save", json={
        "title": "功能测试笔记", "content": "这是一条用于验证笔记链路的笔记。",
        "user_id": 1,
    }, headers=admin_headers)
    assert save.status_code == 200, save.text
    note = (save.json().get("note") or {})      # 接口把结果包在 note 里
    note_id = note.get("id")
    assert note_id, f"保存笔记没有返回 id：{save.json()}"
    assert note.get("title") == "功能测试笔记", f"存进去的标题不对：{note}"

    listed = client.get("/api/notes?user_id=1", headers=admin_headers).json()
    ids = [n.get("id") for n in (listed.get("notes") or [])]
    assert note_id in ids, f"刚保存的笔记不在列表里：{ids}"

    one = client.get(f"/api/notes/{note_id}?user_id=1", headers=admin_headers)
    assert one.status_code == 200, one.text
    assert "功能测试笔记" in one.text, f"读回的笔记内容不对：{one.text[:200]}"

    val = client.post(f"/api/notes/{note_id}/validate", headers=admin_headers)
    assert val.status_code == 200, f"校验笔记失败：{val.status_code} {val.text[:200]}"

    dele = client.delete(f"/api/notes/{note_id}?user_id=1", headers=admin_headers)
    assert dele.status_code == 200, dele.text
    after = client.get("/api/notes?user_id=1", headers=admin_headers).json()
    assert note_id not in [n.get("id") for n in (after.get("notes") or [])], "删除后笔记还在列表里"


# ---------------------------------------------------------------- 旅程四：权限边界（功能视角）

def test_journey_regular_user_can_work_but_not_admin(client):
    """注册一个普通账号，从**功能视角**确认：业务能用，后台进不去。

    与 `test_auth_guard` 的分工：那里测的是状态码语义，
    这里测的是「普通用户这条使用路径走不走得通」。
    """
    from app.services.auth_service import SESSION_HEADER

    reg = client.post("/api/auth/register", json={
        "username": "journey_user", "password": "Journey#12345",
    })
    assert reg.status_code in (200, 201), f"注册失败：{reg.status_code} {reg.text[:200]}"
    token = reg.json().get("token")
    assert token, f"注册没有返回会话令牌：{reg.text[:200]}"
    h = {SESSION_HEADER: token}

    # 业务功能：能读
    assert client.get("/api/files?user_id=1", headers=h).status_code == 200
    assert client.get("/api/kb/stats?user_id=1", headers=h).status_code == 200

    # 后台管理：必须是 403（不是 401 —— 已登录但权限不够，回 401 会把用户踢回登录页）
    r = client.get("/api/admin/overview", headers=h)
    assert r.status_code == 403, f"普通用户访问后台返回 {r.status_code}，应为 403"

    # 登出：普通账号也要能退出（曾因豁免名单漏了它而做不到）
    out = client.post("/api/auth/logout", headers=h)
    assert out.status_code == 200, f"普通账号登出失败：{out.status_code} {out.text[:200]}"

    # 会话必须真的被吊销 —— 用**需要会话**的端点来验（/api/auth/me 走 require_user）。
    # 不能拿 /api/files 去验：那是「过渡期兼容」的读端点，收 user_id 查询参数、
    # 本来就不要求会话，传不传令牌都是 200，证明不了任何事。
    assert client.get("/api/auth/me", headers=h).status_code == 401, "登出后旧令牌仍然有效"
    assert client.get("/api/auth/status", headers=h).json()["authenticated"] is False, \
        "登出后 /auth/status 仍报告已登录"


# ---------------------------------------------------------------- 旅程五：检索

def test_journey_search_finds_uploaded_content(client, admin_headers):
    """上传 → 检索命中。搜不到自己刚上传的内容是「功能不通」的典型形态。"""
    _upload(client, admin_headers, "索引笔记.md", DOC_A)

    # 检索分两路返回：知识库命中在 knowledge_base，文档节点命中在 nodes
    r = client.get("/api/knowledge/search?keyword=索引&limit=20", headers=admin_headers)
    assert r.status_code == 200, r.text
    hits = r.json()
    assert {"knowledge_base", "nodes"} <= set(hits), f"检索返回结构变了：{sorted(hits)}"
    assert hits["knowledge_base"] or hits["nodes"], (
        "搜「索引」两路都没命中，但刚上传的文档里满是这个词"
    )
    # 文档里抽出的节点必须能被搜到（这是「检索能用」的判据，知识库命中不算）
    assert hits["nodes"], (
        f"文档节点一路没命中：{hits['knowledge_base'][:2]} —— 上传内容搜不到等于检索不可用"
    )
    assert any("索引" in (n.get("entity") or "") for n in hits["nodes"]), \
        f"命中的节点里没有含「索引」的：{[n.get('entity') for n in hits['nodes']][:8]}"

    # 不存在的词两路都该为空，而不是报错或返回全量
    empty = client.get("/api/knowledge/search?keyword=zzz不存在的词zzz&limit=20",
                       headers=admin_headers)
    assert empty.status_code == 200, empty.status_code
    e = empty.json()
    assert e["knowledge_base"] == [] and e["nodes"] == [], (
        f"搜不存在的词却返回了 {len(e['knowledge_base'])} + {len(e['nodes'])} 条"
    )


# ---------------------------------------------------------------- 旅程六：后台审阅

def test_journey_admin_pipeline_is_visible(client, admin_headers):
    """后台要能看见「上传 → 解析 → 候选 → 审计」这条流水线。

    管理员排查问题时全靠这一页，它空了等于可观测性为零。
    """
    _upload(client, admin_headers, "索引笔记.md", DOC_A)

    ov = client.get("/api/admin/overview", headers=admin_headers)
    assert ov.status_code == 200, ov.text

    audit = client.get("/api/admin/audit?limit=50", headers=admin_headers)
    assert audit.status_code == 200, audit.text
    logs = audit.json().get("logs") or audit.json().get("items") or []
    actions = {l.get("action") for l in logs}
    assert "upload" in actions, f"审计里没有上传记录，实际有：{sorted(a for a in actions if a)}"
    assert any(a in actions for a in ("parse", "split", "kb_link", "verdict", "candidate")), (
        f"审计里看不到解析/判定环节：{sorted(a for a in actions if a)}"
    )

    cands = client.get("/api/admin/candidates?limit=50", headers=admin_headers)
    assert cands.status_code == 200, cands.text

    stats = client.get("/api/admin/stats/verdicts", headers=admin_headers)
    assert stats.status_code == 200, stats.text


# ---------------------------------------------------------------- 旅程七：导出参数贯穿

def test_journey_export_reflects_the_chosen_params(client, admin_headers):
    """界面上选的参数必须一路贯穿到导出产物（功能视角，不是接口视角）。"""
    _upload(client, admin_headers, "索引笔记.md", DOC_A)

    two = _summary(client, admin_headers, max_paths=2)
    assert len(two["summary"]["paths"]) <= 2, "预览没按 main_paths 走"

    for fmt in ("json", "mermaid"):
        r = client.get(f"/api/summary/download?fmt={fmt}&max_paths=2", headers=admin_headers)
        assert r.status_code == 200, f"{fmt}: {r.status_code}"
    exported = json.loads(
        client.get("/api/summary/download?fmt=json&max_paths=2", headers=admin_headers)
        .content.decode("utf-8"))
    assert len(exported["paths"]) == len(two["summary"]["paths"]), (
        f"导出 {len(exported['paths'])} 条主线，预览 {len(two['summary']['paths'])} 条"
    )

    # 分组方式也要贯穿：两种分组产出的流程图结构不同
    by_level = client.get("/api/summary/download?fmt=mermaid&group_by=level",
                          headers=admin_headers).content.decode("utf-8")
    by_domain = client.get("/api/summary/download?fmt=mermaid&group_by=domain",
                           headers=admin_headers).content.decode("utf-8")
    assert by_level != by_domain, "两种分组方式产出了同一个流程图，参数没生效"
    assert "subgraph" in by_level and "subgraph" in by_domain
