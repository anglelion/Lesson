# app/models.py
from sqlalchemy import create_engine, Column, String, JSON, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker
from datetime import datetime

# 连接本地 PostgreSQL 容器 (账号密码都是 postgres，库名 mcp_audit)
DATABASE_URL = "postgresql://postgres:postgres@localhost:5432/mcp_audit"
engine = create_engine(DATABASE_URL)

# 创建数据库会话
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 定义基础类
Base = declarative_base()

# 定义审查任务表
class ReviewTask(Base):
    __tablename__ = "review_tasks"

    id = Column(String, primary_key=True, index=True) # task_id
    repo_url = Column(String, index=True)
    ref = Column(String)
    status = Column(String, default="pending")        # pending, running, success, failed
    result = Column(JSON, nullable=True)              # 存放 findings 和 decision 的 JSON
    created_at = Column(DateTime, default=datetime.utcnow)

# 自动建表函数
def init_db():
    Base.metadata.create_all(bind=engine)