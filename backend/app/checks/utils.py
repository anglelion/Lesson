# app/utils.py
import os
import subprocess
import tempfile


def fetch_snapshot(repo_url, commit):
    # 1. 创建一个临时目录
    temp_dir = tempfile.mkdtemp(prefix="mcp_review_")

    # 2. 用 git clone 拉取代码
    try:
        print(f"正在下载仓库: {repo_url} 到 {temp_dir}")
        # --depth 1 加快下载速度，只拉最新代码
        subprocess.run(
            ["git", "clone", "--depth", "1", repo_url, temp_dir],
            check=True,
            capture_output=True,
            text=True
        )
        print("下载成功！")
        return temp_dir
    except subprocess.CalledProcessError as e:
        # 如果下载失败，抛出异常，Celery 会捕获并重试
        raise Exception(f"仓库下载失败: {e.stderr}")


def resolve_ref(repo_url, ref):
    # 暂时不用 git ls-remote，先直接返回传进来的分支名
    return ref