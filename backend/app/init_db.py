# init_db.py
from sqlalchemy import inspect

from .database import engine, init_db


def create_tables():
    print("正在连接数据库并建表...")
    init_db()

    # 检查表是否真的建出来了
    inspector = inspect(engine)
    if "review_tasks" in inspector.get_table_names():
        print("✅ 表 `review_tasks` 创建成功！")
    else:
        print("❌ 建表失败，请检查数据库连接配置。")


if __name__ == "__main__":
    create_tables()
