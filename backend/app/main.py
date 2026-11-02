# app/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from celery import Celery
import uuid
from datetime import datetime

app = FastAPI()
celery_app = Celery("mcp_audit", broker="redis://localhost:6379/0",
                    backend="redis://localhost:6379/1")

class SubmitRequest(BaseModel):
    repo_url: str
    ref: str  # 分支/标签/提交标识
    description: str = ""
    deploy_type: str = "stdio"  # stdio | http

@app.post("/api/submit")
async def submit(req: SubmitRequest):
    task_id = str(uuid.uuid4())
    # 1. 写入 PostgreSQL（此处省略 ORM 细节）
    # 2. 投递 Celery 任务
    celery_app.send_task(
        "tasks.run_review",
        args=[task_id, req.repo_url, req.ref, req.deploy_type],
        task_id=task_id
    )
    return {"task_id": task_id, "status": "pending"}

@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    # 从 Redis 或 PostgreSQL 查询状态
    result = celery_app.AsyncResult(task_id)
    return {"task_id": task_id, "state": result.state,
            "result": result.result if result.ready() else None}