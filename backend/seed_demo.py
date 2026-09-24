"""
演示数据注入脚本：向 backend/kg.db 写入高质量的概念级知识图谱，
用于验证前端功能（图谱渲染、筛选器、体检报告、学习路径、知识问答、时间线、每日回顾）。
可重复运行（幂等：先清空旧 nodes/links/files）。
"""
import sqlite3
import json
import time

DB = "c:/Users/yr200/Documents/trae_projects/YR/backend/kg.db"

NOW_MS = int(time.time() * 1000)
DAY = 24 * 3600 * 1000

def days_ago(n):
    return NOW_MS - n * DAY

# ---------- 节点定义：name -> (file_id, entity, title, type, level, domain, keywords, description, upload_days_ago, validate_status) ----------
NODE_DEFS = [
    # L1 元概念
    ("人工智能",       1, "人工智能", "人工智能", "knowledge", 1, "AI",   ["人工智能", "AI", "智能"], "研究使计算机表现出人类智能行为的学科", 30, "passed"),
    ("计算机科学",     1, "计算机科学", "计算机科学", "knowledge", 1, "计算机", ["计算机科学", "CS"], "研究计算与信息处理的学科", 30, "passed"),
    ("数据科学",       5, "数据科学", "数据科学", "knowledge", 1, "数据", ["数据科学", "数据"], "从数据中提取知识的交叉学科", 25, "passed"),
    # L2 核心理论
    ("机器学习",       1, "机器学习", "机器学习", "knowledge", 2, "AI", ["机器学习", "ML", "监督学习"], "让计算机从数据中学习模式的算法", 28, "passed"),
    ("自然语言处理",   1, "自然语言处理", "自然语言处理", "knowledge", 2, "AI", ["NLP", "自然语言", "文本"], "让计算机理解和生成人类语言的技术", 27, "passed"),
    ("计算机视觉",     2, "计算机视觉", "计算机视觉", "knowledge", 2, "AI", ["CV", "图像", "视觉"], "让计算机理解图像和视频的技术", 26, "passed"),
    ("Python",         5, "Python", "Python", "knowledge", 2, "编程", ["Python", "编程语言"], "简洁易学的高级编程语言", 24, "passed"),
    # L3 具体技术
    ("深度学习",       2, "深度学习", "深度学习", "knowledge", 3, "AI", ["深度学习", "神经网络"], "基于深层神经网络的机器学习方法", 25, "passed"),
    ("神经网络",       2, "神经网络", "神经网络", "knowledge", 3, "AI", ["神经网络", "神经元"], "由多层神经元组成的计算模型", 24, "passed"),
    ("监督学习",       1, "监督学习", "监督学习", "knowledge", 3, "AI", ["监督学习", "分类", "回归"], "使用标注数据训练模型", 26, "passed"),
    ("无监督学习",     1, "无监督学习", "无监督学习", "knowledge", 3, "AI", ["无监督学习", "聚类"], "从未标注数据发现隐藏结构", 26, "pending"),
    ("Transformer",    1, "Transformer", "Transformer", "knowledge", 3, "AI", ["Transformer", "自注意力", "注意力"], "基于自注意力机制的现代架构", 22, "passed"),
    ("知识图谱",       1, "知识图谱", "知识图谱", "knowledge", 3, "AI", ["知识图谱", "实体", "关系"], "用实体和关系结构化描述知识", 20, "passed"),
    ("NumPy",          5, "NumPy", "NumPy", "knowledge", 3, "编程", ["NumPy", "数组", "线性代数"], "高效的数组运算库", 20, "passed"),
    ("Pandas",         5, "Pandas", "Pandas", "knowledge", 3, "编程", ["Pandas", "DataFrame", "数据清洗"], "数据处理与分析的库", 19, "passed"),
    # L4 实现/工具
    ("CNN",            2, "卷积神经网络", "卷积神经网络", "knowledge", 4, "AI", ["CNN", "卷积"], "擅长图像识别的神经网络", 23, "passed"),
    ("RNN",            2, "循环神经网络", "循环神经网络", "knowledge", 4, "AI", ["RNN", "循环"], "处理序列数据的神经网络", 23, "passed"),
    ("BERT",           2, "BERT", "BERT", "knowledge", 4, "AI", ["BERT", "预训练", "双向"], "基于 Transformer 的预训练语言模型", 21, "passed"),
    ("GPT",            2, "GPT", "GPT", "knowledge", 4, "AI", ["GPT", "生成式", "自回归"], "自回归生成文本的预训练模型", 21, "passed"),
    ("ResNet",         2, "ResNet", "ResNet", "knowledge", 4, "AI", ["ResNet", "残差连接"], "引入残差连接的深层网络", 20, "passed"),
    ("PyTorch",        2, "PyTorch", "PyTorch", "knowledge", 4, "AI", ["PyTorch", "深度学习框架"], "流行的深度学习框架", 18, "passed"),
    ("Scikit-learn",   5, "Scikit-learn", "Scikit-learn", "knowledge", 4, "编程", ["Scikit-learn", "机器学习库"], "提供机器学习算法统一接口", 17, "pending"),
    ("Django",         5, "Django", "Django", "knowledge", 4, "编程", ["Django", "Web框架", "ORM"], "全栈 Web 开发框架", 16, "passed"),
    ("Flask",          5, "Flask", "Flask", "knowledge", 4, "编程", ["Flask", "轻量框架"], "轻量灵活的 Web 框架", 16, "passed"),
    # 笔记类型节点
    ("AI学习心得",     1, "AI学习心得", "AI学习心得", "note", 2, "AI", ["心得", "AI"], "个人 AI 学习心得笔记", 15, "passed"),
    ("Python实战记录", 5, "Python实战记录", "Python实战记录", "note", 3, "编程", ["实战", "Python"], "Python 项目实战记录", 10, "passed"),
    # 孤立/干扰节点（烹饪 + 园艺）
    ("韩式辣炒年糕",   3, "韩式辣炒年糕", "韩式辣炒年糕", "knowledge", 4, "美食", ["辣炒年糕", "韩国料理"], "韩国街头小吃", 8, "passed"),
    ("番茄种植",       4, "番茄种植", "番茄种植", "knowledge", 3, "园艺", ["番茄", "种植"], "番茄的种植方法", 7, "passed"),
    ("月季花养护",     4, "月季花养护", "月季花养护", "knowledge", 3, "园艺", ["月季", "养护"], "月季花的养护要点", 6, "passed"),
    ("多肉植物繁殖",   4, "多肉植物繁殖", "多肉植物繁殖", "knowledge", 4, "园艺", ["多肉", "繁殖"], "多肉植物的叶插与砍头繁殖", 5, "passed"),
]

# ---------- 连线定义：name_a -> name_b (relation_type, label, score, evidence) ----------
LINK_DEFS = [
    # prerequisite：source 高层 → target 前置基础（diff = 1）
    ("机器学习",     "人工智能",       "prerequisite", "前置知识", 0.82, "机器学习是人工智能的核心子领域"),
    ("自然语言处理", "人工智能",       "prerequisite", "前置知识", 0.80, "自然语言处理是 AI 的重要应用领域"),
    ("计算机视觉",   "人工智能",       "prerequisite", "前置知识", 0.78, "计算机视觉是 AI 的重要分支"),
    ("Python",       "计算机科学",     "prerequisite", "前置知识", 0.70, "Python 是计算机科学常用的编程语言"),
    ("深度学习",     "机器学习",       "prerequisite", "前置知识", 0.85, "深度学习是机器学习的子领域"),
    ("神经网络",     "深度学习",       "prerequisite", "前置知识", 0.88, "神经网络是深度学习的基础模型"),
    ("监督学习",     "机器学习",       "prerequisite", "前置知识", 0.84, "监督学习是机器学习的核心范式"),
    ("无监督学习",   "机器学习",       "prerequisite", "前置知识", 0.75, "无监督学习是机器学习的重要范式"),
    ("Transformer",  "自然语言处理",   "prerequisite", "前置知识", 0.86, "Transformer 是现代 NLP 的基础"),
    ("知识图谱",     "自然语言处理",   "prerequisite", "前置知识", 0.72, "知识图谱与 NLP 密切相关"),
    ("NumPy",        "Python",         "prerequisite", "前置知识", 0.80, "NumPy 基于 Python 提供数组运算"),
    ("Pandas",       "Python",         "prerequisite", "前置知识", 0.80, "Pandas 基于 Python 做数据分析"),
    ("CNN",          "神经网络",       "prerequisite", "前置知识", 0.82, "CNN 是一种特殊的前馈神经网络"),
    ("RNN",          "神经网络",       "prerequisite", "前置知识", 0.80, "RNN 是处理序列的神经网络"),
    ("BERT",         "Transformer",    "prerequisite", "前置知识", 0.88, "BERT 基于 Transformer 架构"),
    ("GPT",          "Transformer",    "prerequisite", "前置知识", 0.87, "GPT 基于 Transformer 的自回归"),
    ("ResNet",       "CNN",            "prerequisite", "前置知识", 0.78, "ResNet 是一种深层 CNN"),
    ("PyTorch",      "神经网络",       "prerequisite", "前置知识", 0.79, "PyTorch 用于构建和训练神经网络"),
    ("Scikit-learn", "机器学习",       "prerequisite", "前置知识", 0.82, "Scikit-learn 提供机器学习算法"),
    ("Django",       "Python",         "prerequisite", "前置知识", 0.78, "Django 是基于 Python 的框架"),
    ("Flask",        "Python",         "prerequisite", "前置知识", 0.76, "Flask 是基于 Python 的框架"),
    # related：同层级相关
    ("深度学习",     "计算机视觉",     "related", "相关", 0.70, "深度学习驱动计算机视觉"),
    ("神经网络",     "计算机视觉",     "related", "相关", 0.68, "神经网络用于计算机视觉任务"),
    ("Transformer",  "神经网络",       "related", "相关", 0.72, "Transformer 基于神经网络"),
    ("BERT",         "自然语言处理",   "related", "相关", 0.75, "BERT 用于 NLP 任务"),
    ("GPT",          "自然语言处理",   "related", "相关", 0.74, "GPT 用于 NLP 文本生成"),
    ("CNN",          "计算机视觉",     "related", "相关", 0.80, "CNN 主要用于图像识别"),
    ("RNN",          "自然语言处理",   "related", "相关", 0.76, "RNN 适合处理自然语言序列"),
    ("监督学习",     "深度学习",       "related", "相关", 0.66, "深度学习大量使用监督学习"),
    ("Scikit-learn", "Pandas",         "related", "相关", 0.60, "Scikit-learn 常与 Pandas 配合"),
    ("NumPy",        "Pandas",         "related", "相关", 0.72, "Pandas 底层依赖 NumPy"),
    ("数据科学",     "机器学习",       "related", "相关", 0.68, "机器学习是数据科学的核心方法"),
    ("数据科学",     "Python",         "related", "相关", 0.70, "Python 是数据科学主流语言"),
    # contains：包含
    ("计算机科学",   "人工智能",       "contains", "包含", 0.75, "人工智能是计算机科学的分支"),
    ("人工智能",     "知识图谱",       "contains", "包含", 0.62, "知识图谱是 AI 的应用方向"),
    # 笔记关联
    ("AI学习心得",   "人工智能",       "related", "相关", 0.65, "笔记中提到了人工智能"),
    ("Python实战记录","Pandas",        "related", "相关", 0.64, "实战中使用了 Pandas"),
    # 园艺孤立簇（size=3 断层区域）
    ("番茄种植",     "月季花养护",     "related", "相关", 0.55, "都是园艺主题"),
    ("月季花养护",   "多肉植物繁殖",   "related", "相关", 0.50, "都是园艺主题"),
]

REL_COLORS = {
    "prerequisite": "#D4A574",
    "related": "#8A9AA8",
    "contains": "#7CB8A0",
    "extension": "#8A9AA8",
    "theory": "#4F6F8F",
}

LEVEL_LABELS = {1: "L1: 元概念", 2: "L2: 核心理论", 3: "L3: 具体技术", 4: "L4: 实现/工具"}


def main():
    conn = sqlite3.connect(DB)
    cur = conn.cursor()

    # 清空旧数据（顺序：先删依赖表）
    for t in ["links", "node_sources", "note_nodes", "isolate_blacklist", "nodes", "files"]:
        cur.execute(f"DELETE FROM {t}")
    conn.commit()
    print("已清空旧 nodes/links/files")

    # 插入 files
    file_names = {1: "AI基础.md", 2: "深度学习.md", 3: "韩式辣炒年糕.md", 4: "园艺种植.md", 5: "Python编程.md"}
    file_ids = {}
    for fid, name in file_names.items():
        cur.execute(
            "INSERT INTO files (user_id, name, content, status, node_count) VALUES (1, ?, '', 'done', 0)",
            (name,),
        )
        file_ids[fid] = cur.lastrowid

    # 插入 nodes
    node_ids = {}
    for name, fid, entity, title, ntype, level, domain, keywords, desc, days, vstatus in NODE_DEFS:
        cur.execute(
            """INSERT INTO nodes
               (user_id, file_id, entity, title, type, description, keywords, entities,
                group_id, group_name, level, level_label, domain, validated, validate_status,
                confidence, status, visible, isolate_blacklist, upload_time, created_at, updated_at)
               VALUES (1, ?, ?, ?, ?, ?, ?, ?, 'default', '默认分组', ?, ?, ?, ?, ?, 0.8, 'active', 1, '[]', ?, datetime('now'), datetime('now'))""",
            (
                file_ids[fid], entity, title, ntype, desc,
                json.dumps(keywords, ensure_ascii=False), json.dumps(keywords, ensure_ascii=False),
                level, LEVEL_LABELS[level], domain,
                1 if vstatus == "passed" else 0, vstatus,
                days_ago(days),
            ),
        )
        node_ids[name] = cur.lastrowid

    # 插入 links
    link_count = 0
    for a, b, rtype, rlabel, score, evidence in LINK_DEFS:
        if a not in node_ids or b not in node_ids:
            print(f"  跳过连线（节点缺失）: {a} -> {b}")
            continue
        cur.execute(
            """INSERT INTO links
               (source_id, target_id, relation_type, relation_label, relation_color,
                relation_line_style, score, final_weight, is_render, evidence,
                auto_generated, user_confirmed, semantic_bridge, time_bridge, created_at)
               VALUES (?, ?, ?, ?, ?, 'solid', ?, ?, 1, ?, 1, 0, 0, 0, datetime('now'))""",
            (
                node_ids[a], node_ids[b], rtype, rlabel, REL_COLORS.get(rtype, "#8A9AA8"),
                score, score, evidence,
            ),
        )
        link_count += 1

    conn.commit()
    print(f"注入完成：{len(node_ids)} 个节点，{link_count} 条连线")
    conn.close()


if __name__ == "__main__":
    main()
