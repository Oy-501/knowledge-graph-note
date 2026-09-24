"""种子知识库初始化脚本（CLI 入口）

用法（在 backend/ 目录下）：
    py -m scripts.seed_knowledge_base            # 幂等导入（已存在则跳过）
    py -m scripts.seed_knowledge_base --force    # 清空种子来源数据后重建

解析逻辑与格式说明见 app/seed.py。
"""
import os
import sys

# 保证可以 `python scripts/seed_knowledge_base.py` 直接运行
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.seed import bootstrap  # noqa: E402

if __name__ == "__main__":
    force = "--force" in sys.argv
    if force:
        # force 模式需要自定义入口，见 app/seed.seed_knowledge_base(force=True)
        from app.database import SessionLocal
        from app.seed import ensure_default_user, seed_knowledge_base
        db = SessionLocal()
        try:
            ensure_default_user(db)
            result = seed_knowledge_base(db, force=True)
        finally:
            db.close()
    else:
        result = bootstrap()

    import json
    print(json.dumps(result, ensure_ascii=False, indent=2))
    print("\n[OK] 初始化完成！")
