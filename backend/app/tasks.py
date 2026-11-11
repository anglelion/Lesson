# app/tasks.py
import shutil
import os
import tempfile
import subprocess

from .celery_app import celery
from .database import SessionLocal
from .models import ReviewTask

# 1. 导入所有检查模块（按照你的真实文件名）
from .checks.static_audit import static_audit
from .checks.dependency import dependency_check
from .checks.transport import transport_check


# from checks.mcp_semantic import mcp_semantic_check # 如果还没写，先注释掉
# from checks.update_review import update_review # 如果还没写，先注释掉

def fetch_snapshot(repo_url):
    """下载 Github 仓库到临时目录"""
    temp_dir = tempfile.mkdtemp(prefix="mcp_")
    print(f"正在克隆代码: {repo_url} -> {temp_dir}")
    try:
        subprocess.run(["git", "clone", "--depth", "1", repo_url, temp_dir], check=True, capture_output=True)
        return temp_dir
    except subprocess.CalledProcessError as e:
        raise Exception(f"仓库拉取失败，请检查 URL 是否公开: {e.stderr.decode('utf-8', errors='ignore')}")


@celery.task(bind=True, max_retries=0)
def run_review(self, task_id, repo_url, ref, deploy_type):
    print(f"\n=========================================")
    print(f" [Celery] 接收到任务，Task ID: {task_id}")
    print(f" [Celery] 仓库地址: {repo_url}")
    print(f"=========================================\n")
    db = SessionLocal()
    task_record = None
    workdir = None
    try:
        task_record = db.query(ReviewTask).filter(ReviewTask.id == task_id).first()
        if task_record:
            task_record.status = "running"
            db.commit()

        # 1. 下载真实代码
        workdir = fetch_snapshot(repo_url)

        findings = []

        # 2. 静态审计 (Semgrep)
        try:
            print("执行静态审计...")
            findings += static_audit(workdir)
        except Exception as e:
            print(f"静态审计报错: {e}")
            findings.append({"type": "tool_error", "tool": "semgrep", "message": str(e)})

        # 3. 依赖检查 (OSV)
        try:
            print("执行依赖检查...")
            findings += dependency_check(workdir)
        except Exception as e:
            print(f"依赖检查报错: {e}")

        # 4. 传输与授权检查（目前返回空，但流程打通）
        try:
            print("执行传输检查...")
            findings += transport_check(workdir, deploy_type)
        except Exception as e:
            print(f"传输检查报错: {e}")

        # 5. 决策仲裁（简易版：有发现就转人工复核）
        decision = {"decision": "pass", "reason": "无风险"}
        if len(findings) > 0:
            decision = {"decision": "manual_review", "reason": f"发现 {len(findings)} 个问题"}

        # 6. 结果写入数据库
        if task_record:
            task_record.status = "success"
            task_record.result = {"findings": findings, "decision": decision}
            db.commit()

        print(f"审查完成，共发现 {len(findings)} 个问题。结论: {decision['decision']}")
        return {"findings": findings, "decision": decision}

    except Exception as exc:
        db.rollback()
        if task_record:
            task_record.status = "failed"
            task_record.result = {"error": str(exc)}
            db.commit()
        print(f"任务执行失败: {exc}")
        #raise self.retry(exc=exc, countdown=10)
    finally:
        db.close()
        if workdir and os.path.exists(workdir):
            shutil.rmtree(workdir, ignore_errors=True)
