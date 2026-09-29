"""语义向量探针：量化 β 维到底能不能认出「换个说法说同一件事」

用法（在 backend 目录下执行）：
  py scripts/vector_probe.py                  # 用当前引擎跑内置对照集
  py scripts/vector_probe.py --tfidf          # 强制降级编码，看降级后的水平
  py scripts/vector_probe.py --csv out.csv    # 导出逐条明细

判定标准很简单，也很关键：
  同一个意思的两种说法（改写对）的相似度，必须高于随便两句无关话的相似度。
这称为「排序正确率」。它掉了，说明 β 维在瞎打分 —— 分数看着有，实际没信息量。
"""
import argparse
import os
import statistics
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# (改写对：同一个意思，说法不同)
PARAPHRASE_PAIRS = [
    ("数据库索引可以加快查询速度", "为数据表建立索引能提升检索性能"),
    ("上传大文件会让服务卡死", "体积过大的文件拖垮了后端响应"),
    ("用户登录后拿到会话令牌", "认证成功后颁发 session token"),
    ("知识图谱由节点和边组成", "图谱里的实体与关系构成了网络结构"),
    ("索引失效是因为对列使用了函数", "在字段上套函数会导致索引无法命中"),
    ("换背景没反应是因为视图根容器不透明", "视图容器背景不透明导致背景层被挡住"),
    ("The index speeds up query execution", "Creating an index improves retrieval performance"),
    ("Large uploads freeze the server", "Huge files make the backend unresponsive"),
]

# (无关对：不同话题)
UNRELATED_PAIRS = [
    ("数据库索引可以加快查询速度", "今天中午食堂的红烧肉有点咸"),
    ("上传大文件会让服务卡死", "这段代码的缩进用了两个空格"),
    ("用户登录后拿到会话令牌", "周末打算去爬山顺便拍点照片"),
    ("知识图谱由节点和边组成", "天气预报说明天有雨记得带伞"),
    ("索引失效是因为对列使用了函数", "楼下的猫又跑到阳台上晒太阳"),
    ("换背景没反应是因为视图根容器不透明", "地铁早高峰挤得连扶手都抓不到"),
    ("The index speeds up query execution", "She bought a loaf of bread yesterday"),
    ("Large uploads freeze the server", "The concert tickets sold out in minutes"),
]


def _sim(engine, a: str, b: str) -> float:
    return engine.cosine_similarity(engine.encode(a), engine.encode(b))


def main() -> int:
    parser = argparse.ArgumentParser(description="语义向量质量探针")
    parser.add_argument("--tfidf", action="store_true", help="强制使用降级编码")
    parser.add_argument("--csv", default=None, help="把逐条明细写到这里")
    args = parser.parse_args()

    if args.tfidf:
        os.environ["VECTOR_BACKEND"] = "tfidf"

    from app.services import vector_engine as engine

    info = engine.get_engine_info()
    print("=" * 78)
    print(f"引擎: {info['signature']}")
    print(f"模式: {'降级（字面重合）' if info['degraded'] else '真语义模型'}"
          f"{' · 原因: ' + info['reason'] if info['reason'] else ''}")
    print("=" * 78)

    para = [(a, b, _sim(engine, a, b)) for a, b in PARAPHRASE_PAIRS]
    unrel = [(a, b, _sim(engine, a, b)) for a, b in UNRELATED_PAIRS]

    print("\n[改写对] 同一个意思、不同说法")
    for a, b, s in para:
        print(f"  {s:.3f}  {a}  ||  {b}")

    print("\n[无关对] 不同话题")
    for a, b, s in unrel:
        print(f"  {s:.3f}  {a}  ||  {b}")

    para_sims = [s for _, _, s in para]
    unrel_sims = [s for _, _, s in unrel]
    margin = statistics.mean(para_sims) - statistics.mean(unrel_sims)

    # 排序正确率：每一对改写句，都要比「同位置的那对无关句」更像
    correct = sum(1 for p, u in zip(para_sims, unrel_sims) if p > u)

    print("\n" + "=" * 78)
    print(f"改写对平均相似度 : {statistics.mean(para_sims):.3f}")
    print(f"无关对平均相似度 : {statistics.mean(unrel_sims):.3f}")
    print(f"区分度（差值）   : {margin:+.3f}")
    print(f"排序正确率       : {correct}/{len(para_sims)}")
    print("=" * 78)

    if args.csv:
        import csv as _csv
        with open(args.csv, "w", newline="", encoding="utf-8-sig") as fh:
            writer = _csv.writer(fh)
            writer.writerow(["kind", "text_a", "text_b", "similarity", "engine"])
            for a, b, s in para:
                writer.writerow(["paraphrase", a, b, round(s, 4), info["signature"]])
            for a, b, s in unrel:
                writer.writerow(["unrelated", a, b, round(s, 4), info["signature"]])
        print(f"明细已写入 {args.csv}")

    # 退出码：区分度必须为正，且排序正确率过半 —— 否则 β 维没有信息量
    return 0 if (margin > 0 and correct > len(para_sims) / 2) else 1


if __name__ == "__main__":
    sys.exit(main())
