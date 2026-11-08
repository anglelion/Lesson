# app/main.py
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
import uuid
from celery_app import celery
from tasks import run_review
from models import SessionLocal, ReviewTask, init_db

app = FastAPI()


# 启动时自动建表（防止数据库空）
@app.on_event("startup")
def startup_event():
    init_db()


class SubmitRequest(BaseModel):
    repo_url: str
    ref: str
    description: str = ""
    deploy_type: str = "stdio"


@app.post("/api/submit")
async def submit(req: SubmitRequest):
    task_id = str(uuid.uuid4())

    # 1. 真正写入 PostgreSQL
    db = SessionLocal()
    new_task = ReviewTask(id=task_id, repo_url=req.repo_url, ref=req.ref, status="pending")
    db.add(new_task)
    db.commit()
    db.close()
    print(f" [FastAPI] 任务 {task_id} 已写入数据库")

    # 2. 投递 Celery 任务（直接用 .delay，更稳妥）
    run_review.delay(task_id, req.repo_url, req.ref, req.deploy_type)

    return {"task_id": task_id, "status": "pending"}


@app.get("/api/tasks/{task_id}")
async def get_task(task_id: str):
    # 直接从 PostgreSQL 查（这才是真正的持久化）
    db = SessionLocal()
    task = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
    db.close()

    if not task:
        return {"error": "Task not found"}

    return {
        "task_id": task.id,
        "status": task.status,
        "result": task.result,
        "created_at": task.created_at
    }