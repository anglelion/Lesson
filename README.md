# MCP 仓库安全审查系统（MCP Audit）

一个面向 **MCP（Model Context Protocol）服务仓库** 的自动化安全审查原型。用户提交 Git 仓库地址后，系统通过 FastAPI 接收请求、PostgreSQL 持久化任务、Celery + Redis 异步执行审查流水线，最终输出风险发现（`findings`）与仲裁结论（`decision`）。

> 当前仓库处于原型/脚手架阶段：`frontend/`、`backend/rules/` 为空目录，`requirement.txt` 未填写内容，部分检查模块为占位实现。详见「当前状态与待办」。

---

## 功能特性

- **异步任务化审查**：提交即返回 `task_id`，后台 Worker 执行，前端可轮询结果。
- **代码快照拉取**：`git clone --depth 1` 到临时目录，审查结束自动清理。
- **静态审计**：通过 Docker 运行 `semgrep/semgrep --config=auto --json`，归一化规则 ID、文件、行号、严重级别与证据片段。
- **依赖漏洞检查**：解析 `requirements.txt` / `requirements-dev.txt` / `pyproject.toml` 中 `==` 固定版本，调用 [OSV API](https://osv.dev/) 查询已知漏洞。
- **传输/授权检查**：预留 `transport_check(workdir, deploy_type)` 接口（`stdio` 默认部署类型）。
- **决策仲裁**：独立模块 [`arbitrate()`](backend/app/decisions.py:2) 支持 `reject` / `manual_review` / `pass`；主流水线内置简易版「有发现即转人工」。
- **状态持久化**：`review_tasks` 表记录 `pending → running → success/failed` 及 JSON 结果。

---

## 技术栈

| 组件 | 用途 | 配置位置 |
| --- | --- | --- |
| Python 3.10+ / FastAPI | HTTP API | [`main.py`](backend/app/main.py:9) |
| SQLAlchemy + PostgreSQL | 任务表 ORM | [`models.py`](backend/app/models.py:7) |
| Celery + Redis | Broker `db0` / Backend `db1` | [`celery_app.py`](backend/app/celery_app.py:5) |
| Semgrep（Docker 镜像） | 静态扫描 | [`static_audit.py`](backend/app/checks/static_audit.py:11) |
| OSV.dev API | 依赖漏洞情报 | [`dependency.py`](backend/app/checks/dependency.py:7) |
| Git CLI | 拉取仓库快照 | [`tasks.py`](backend/app/tasks.py:19) |

> 依据代码推断的最小依赖：`fastapi`、`pydantic`、`sqlalchemy`、`psycopg2-binary`、`celery`、`redis`、`uvicorn`。当前 [`requirement.txt`](backend/requirement.txt:1) 为空，安装前需补全。

---

## 目录结构

```text
PythonProject/
├── README.md
├── backend/
│   ├── requirement.txt              # 依赖清单（待补全）
│   ├── rules/                       # 自定义 Semgrep 规则（预留，当前为空）
│   └── app/
│       ├── main.py                  # FastAPI 入口：/api/submit、/api/tasks/{id}
│       ├── models.py                # ReviewTask 模型 + 建表
│       ├── init_db.py               # 手动建表脚本
│       ├── schemas.py               # 预留：Pydantic Schema
│       ├── evidence.py              # 预留：证据分级
│       ├── decisions.py             # arbitrate() 仲裁逻辑
│       ├── celery_app.py            # Celery 实例与序列化配置
│       ├── tasks.py                 # run_review 流水线编排
│       └── checks/
│           ├── static_audit.py      # Semgrep(Docker) 扫描
│           ├── dependency.py        # OSV 依赖查询
│           ├── transport.py         # 传输检查（占位）
│           ├── mcp_semantic.py      # MCP 语义检查（占位）
│           ├── update_reiew.py      # 备用占位（文件名含拼写）
│           └── utils.py             # fetch_snapshot / resolve_ref 工具
└── frontend/                        # 前端（预留，当前为空）
```

---

## 环境准备

### 1. 基础服务

```bash
# PostgreSQL：库名 mcp_audit，账号/密码 postgres/postgres，端口 5432
# 首次创建（容器名需与后续 docker exec 一致）：
docker run -d --name mcp-postgres -e POSTGRES_PASSWORD=postgres -e POSTGRES_DB=mcp_audit -p 5432:5432 postgres:16

# Redis：6379
docker run -d --name mcp-redis -p 6379:6379 redis:7

# 之后每次重启直接 start 即可
docker start mcp-redis
docker start mcp-postgres

# Semgrep 由代码自动 docker run，需本机 Docker 可用并可拉取 semgrep/semgrep
docker pull semgrep/semgrep

# 验证官方镜像可用（应输出 semgrep 版本号）
docker run --rm semgrep/semgrep semgrep --version
```

数据库连接串硬编码在 [`models.py`](backend/app/models.py:7)，Redis 地址硬编码在 [`celery_app.py`](backend/app/celery_app.py:7)；如需改环境请直接修改或后续抽为环境变量。

### 2. Python 依赖

```bash
cd backend
python -m pip install fastapi pydantic sqlalchemy psycopg2-binary celery redis uvicorn
```

> 仓库已有 `.venv/`，也可激活后安装；建议同步把上述依赖写入 [`requirement.txt`](backend/requirement.txt:1)。

### 3. 建表（可选）

[`main.py`](backend/app/main.py:13) 启动时会自动 `init_db()`；也可手动执行：

```bash
cd backend/app
python init_db.py
```

---

## 启动

所有命令均在 `backend/app` 目录下执行（源码使用 `from models import ...` 等顶层导入，需把该目录作为工作目录/PYTHONPATH）。

```bash
# 终端 1：API
cd backend/app
python -m uvicorn main:app --reload

# 终端 2：Celery Worker
cd backend/app
python -m celery -A celery_app.celery worker --loglevel=info --pool=solo --include=tasks
```

Windows 下建议使用 `--pool=solo` 避免 Celery 默认 prefork 的兼容问题；`--include=tasks` 确保 [`run_review()`](backend/app/tasks.py:31) 被 Worker 显式加载。

---

## 端到端快速验证（推荐流程）

按顺序执行，完成一次「启动 → 提交 → 落库校验」闭环：

```bash
# 1) 基础服务（已创建过容器时直接 start）
docker start mcp-redis
docker start mcp-postgres

# 2) 验证 semgrep 官方镜像可用
docker run --rm semgrep/semgrep semgrep --version

# 3) 终端 1：FastAPI（在 backend/app 下）
python -m uvicorn main:app --reload

# 4) 终端 2：Celery Worker（在 backend/app 下）
python -m celery -A celery_app.celery worker --loglevel=info --pool=solo --include=tasks
```

打开浏览器访问 **<http://127.0.0.1:8000/docs>**，找到 `POST /api/submit`，点击右侧 **"Try it out"**，将 Request body 改为：

```json
{
  "repo_url": "https://gitee.com/mirrors/requests.git",
  "ref": "main",
  "description": "测试 Gitee 镜像",
  "deploy_type": "stdio"
}
```

点击 **Execute**，记录返回的 `task_id`；Worker 日志应出现 `pending → running → success/failed`。

### 查询数据库校验任务落库

```bash
docker exec -it mcp-postgres psql -U postgres -d mcp_audit
```

进入 `psql` 后执行：

```sql
SELECT id, repo_url, status, created_at FROM review_tasks;
```

预期能看到刚提交的一行：`repo_url` 为 `https://gitee.com/mirrors/requests.git`，`status` 随流水线从 `pending` 变为 `running`、`success`（异常时为 `failed`），`created_at` 为提交时间。也可配合 `GET /api/tasks/{task_id}` 查看 `result` 中的 `findings` / `decision`。

> 提示：`\q` 退出 `psql`；若容器尚未初始化过库表，[`main.py`](backend/app/main.py:13) 启动时会自动建表，或手动执行 [`init_db.py`](backend/app/init_db.py:1)。

---

## API 使用

### 提交审查

`POST /api/submit`

```json
{
  "repo_url": "https://github.com/example/mcp-server.git",
  "ref": "main",
  "description": "可选说明",
  "deploy_type": "stdio"
}
```

响应：

```json
{ "task_id": "6f1c...", "status": "pending" }
```

### 查询结果

`GET /api/tasks/{task_id}`

```json
{
  "task_id": "6f1c...",
  "status": "success",
  "result": {
    "findings": [
      {
        "rule_id": "GHSA-xxxx",
        "type": "dependency_vuln",
        "package": "requests",
        "version": "2.28.1",
        "severity": "HIGH",
        "source": "osv"
      }
    ],
    "decision": { "decision": "manual_review", "reason": "发现 1 个问题" }
  },
  "created_at": "2026-11-08T09:00:00"
}
```

`curl` 示例（等价于在 Swagger 中提交 Gitee 镜像）：

```bash
curl -X POST http://127.0.0.1:8000/api/submit -H "Content-Type: application/json" -d "{\"repo_url\":\"https://gitee.com/mirrors/requests.git\",\"ref\":\"main\",\"description\":\"测试 Gitee 镜像\",\"deploy_type\":\"stdio\"}"
curl http://127.0.0.1:8000/api/tasks/<task_id>
```

FastAPI 自动生成交互式文档：`http://127.0.0.1:8000/docs`。

---

## 审查流水线

[`run_review()`](backend/app/tasks.py:31) 顺序如下：

1. 置状态 `running` → [`fetch_snapshot()`](backend/app/tasks.py:19) 克隆到临时目录；
2. [`static_audit()`](backend/app/checks/static_audit.py:6)：Semgrep 扫描，异常降级为 `tool_error` 发现项；
3. [`dependency_check()`](backend/app/checks/dependency.py:59)：解析固定版本 → OSV 查询；
4. [`transport_check()`](backend/app/checks/transport.py:1)：当前返回空；
5. 汇总 `findings`，生成 `decision`，写回 `review_tasks.result`，状态置 `success`；
6. `finally` 关闭会话并 `shutil.rmtree` 清理临时目录；异常则置 `failed` 并记录 `error`。

独立仲裁模块 [`decisions.py`](backend/app/decisions.py:2) 提供更严格策略（已确认 CRITICAL / 工具投毒 → `reject`，HIGH 未确认或工具报错 → `manual_review`），目前尚未接入主流水线。

---

## 当前状态与待办

- [ ] 补全 [`requirement.txt`](backend/requirement.txt:1)，固化版本并支持 `pip install -r`。
- [ ] 将 PostgreSQL / Redis 连接配置改为环境变量，去掉硬编码。
- [ ] 把 [`arbitrate()`](backend/app/decisions.py:2) 接入 [`tasks.py`](backend/app/tasks.py:73)，替换简易决策。
- [ ] 实现 [`transport_check()`](backend/app/checks/transport.py:1)（TLS、Host 校验）与 [`mcp_semantic_check()`](backend/app/checks/mcp_semantic.py:1)（工具投毒、描述一致性）。
- [ ] 填充 `backend/rules/` 自定义 MCP 规则，并在 Semgrep 命令中挂载（`--config=/rules`）。
- [ ] 填充 `schemas.py` / `evidence.py`，统一发现项字段（注意 `dependency.py` 中 `evidence_level` 现为「已确认」中文，与仲裁模块期望的 `confirmed` 不一致）。
- [ ] `ref` 参数目前未参与 clone（仅 `--depth 1` 拉默认分支），可结合 [`resolve_ref()`](backend/app/checks/utils.py:28) 实现指定分支/commit。
- [ ] 修正 [`update_reiew.py`](backend/app/checks/update_reiew.py:1) 文件名拼写，移除重复占位函数。
- [ ] 补充 `frontend/` 页面与单元测试；`GET /api/tasks` 未找到时建议返回 404 而非 `{"error": ...}`。
- [ ] 为 OSV 查询、Semgrep 超时、大仓库克隆补充重试/限流与更细粒度日志。

---

## 许可证

未指定，按需补充。
