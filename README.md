# MCP 仓库安全审查系统（MCP Audit）

一个面向 **MCP（Model Context Protocol）服务仓库** 的自动化安全审查原型。用户提交 Git 仓库地址后，系统通过 FastAPI 接收请求、PostgreSQL 持久化任务、Celery + Redis 异步执行审查流水线，最终输出风险发现（`findings`）与仲裁结论（`decision`）。

> 当前处于 v0.1 工程基础建设阶段：依赖、环境配置、容器编排、健康检查和数据库迁移已经纳入工程结构；部分安全检查模块仍为后续版本的占位实现。

---

## 功能特性

- **异步任务化审查**：提交即返回 `task_id`，后台 Worker 执行，前端可轮询结果。
- **代码快照拉取**：`git clone --depth 1` 到临时目录，审查结束自动清理。
- **静态审计**：运行 Semgrep Community Edition 的自动规则和项目本地规则，归一化规则 ID、文件、行号、严重级别与证据片段。
- **依赖漏洞检查**：解析 Python/Node.js 依赖与锁文件，批量调用 [OSV API](https://osv.dev/) 并补充漏洞详情和修复版本。
- **敏感信息检查**：离线检测常见私钥和令牌模式，报告中始终隐藏实际凭据值。
- **MCP 语义检查**：分析工具描述、输入/输出 Schema、行为注解和实现副作用，识别工具投毒与描述不一致。
- **传输与隔离检查**：检查 HTTP/stdio 暴露、鉴权、Host、CORS 和明文通信，并限制不可信仓库的来源与资源占用。
- **传输/授权检查**：预留 `transport_check(workdir, deploy_type)` 接口（`stdio` 默认部署类型）。
- **决策仲裁**：独立模块 [`arbitrate()`](backend/app/decisions.py:2) 支持 `reject` / `manual_review` / `pass`；主流水线内置简易版「有发现即转人工」。
- **状态持久化**：`review_tasks` 表记录 `pending → running → success/failed` 及 JSON 结果。

---

## 技术栈

| 组件 | 用途 | 配置位置 |
| --- | --- | --- |
| Python 3.11+ / FastAPI | HTTP API | [`main.py`](backend/app/main.py) |
| SQLAlchemy + PostgreSQL | 任务表 ORM | [`models.py`](backend/app/models.py:7) |
| Celery + Redis | Broker `db0` / Backend `db1` | [`celery_app.py`](backend/app/celery_app.py:5) |
| Semgrep Community Edition | 静态扫描 | [`static_audit.py`](backend/app/checks/static_audit.py) |
| OSV.dev API | 依赖漏洞情报 | [`dependency.py`](backend/app/checks/dependency.py:7) |
| Git CLI | 拉取仓库快照 | [`tasks.py`](backend/app/tasks.py:19) |

Python 依赖和版本范围统一维护在 [`pyproject.toml`](pyproject.toml)，运行配置通过 `MCP_AUDIT_` 前缀的环境变量覆盖。

---

## 目录结构

```text
Lesson/
├── compose.yaml                    # PostgreSQL、Redis、迁移、API、Worker
├── pyproject.toml                  # Python 项目元数据与依赖
├── .env.example                    # 环境变量示例
├── README.md
├── backend/
│   ├── Dockerfile                   # API/Worker 共用镜像
│   ├── alembic.ini                  # 数据库迁移配置
│   ├── alembic/                     # 数据库迁移脚本
│   └── app/
│       ├── main.py                  # FastAPI 入口：/api/submit、/api/tasks/{id}
│       ├── config.py                # 类型化环境配置
│       ├── database.py              # 数据库连接与会话
│       ├── models.py                # ReviewTask 模型
│       ├── init_db.py               # 手动建表脚本
│       ├── schemas.py               # API 请求与响应模型
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
```

---

## 环境准备

### 推荐：Docker Compose

```bash
docker compose up --build
```

Compose 会启动 PostgreSQL、Redis、数据库迁移、API 和 Worker。默认值可直接用于本地开发；需要覆盖配置时，将 `.env.example` 复制为 `.env` 后修改。

### 本地 Python 开发

```bash
python -m pip install -e ".[dev]"
alembic -c backend/alembic.ini upgrade head
```

## 启动

在仓库根目录执行：

```bash
# 终端 1：API
python -m uvicorn backend.app.main:app --reload

# 终端 2：Celery Worker
python -m celery -A backend.app.celery_app:celery worker --loglevel=info --pool=solo
```

Windows 本地运行 Worker 时建议使用 `--pool=solo`；容器内使用 Compose 已配置的并发参数。

---

## 端到端快速验证（推荐流程）

按顺序执行，完成一次「启动 → 提交 → 落库校验」闭环：

```bash
docker compose up --build
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
docker compose exec postgres psql -U postgres -d mcp_audit
```

进入 `psql` 后执行：

```sql
SELECT id, repo_url, status, created_at FROM review_tasks;
```

预期能看到刚提交的一行：`repo_url` 为 `https://gitee.com/mirrors/requests.git`，`status` 随流水线从 `pending` 变为 `running`、`success`（异常时为 `failed`），`created_at` 为提交时间。也可配合 `GET /api/tasks/{task_id}` 查看 `result` 中的 `findings` / `decision`。

> 提示：`\q` 退出 `psql`；Compose 启动时会先运行 Alembic 数据库迁移。

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

[`run_review()`](backend/app/tasks.py) 顺序如下：

1. 置状态为 `running/fetching`，精确获取请求的 branch、tag 或 commit；
2. 保存解析后的不可变 commit SHA，切换状态为 `scanning`；
3. 执行 Semgrep、依赖和传输检查，单个检查失败记录为 `tool_error`；
4. 切换到 `arbitrating` 并生成当前阶段的简易结论；
5. 保存结果、提交哈希和完成时间，状态置为 `success/completed`；
6. 流水线异常进入有限重试，最终失败时保存错误和 `failed` 状态；
7. 无论成功或失败，临时代码快照都会清理。

[`evidence.py`](backend/app/evidence.py) 会把不同扫描器的输出归一化为稳定证据格式，并记录每个工具的状态与耗时；[`decisions.py`](backend/app/decisions.py) 已接入流水线，根据证据等级、风险等级和扫描覆盖情况生成确定性结论。

---

## 当前状态与待办

- [x] 使用 [`pyproject.toml`](pyproject.toml) 管理依赖和版本范围。
- [x] 将 PostgreSQL / Redis 连接配置改为环境变量。
- [x] 增加 Docker Compose、健康检查和 Alembic 数据库迁移基础。
- [x] 让 `ref` 真正控制 branch、tag 或 commit，并保存解析后的 commit SHA。
- [x] 增加任务阶段、时间戳、错误、有限重试和可靠失败状态。
- [x] 统一发现项、证据等级、工具运行记录和结果摘要格式。
- [x] 把 [`arbitrate()`](backend/app/decisions.py) 接入任务流水线。
- [x] 实现 MCP 工具投毒、描述一致性、注解矛盾和 Schema 检查。
- [x] 实现 HTTP/stdio、TLS、Host、Origin 与授权配置检查。
- [x] 限制仓库协议、主机、解析地址、大小、文件数和符号链接。
- [x] 为 API/Worker 容器增加只读文件系统、能力移除和资源限制。
- [x] 增加本地通用安全规则，并与 Semgrep 自动规则共同执行。
- [x] 增加敏感信息扫描，确保报告不回传实际凭据。
- [x] 扩展 Python/Node.js 锁文件解析并使用 OSV 批量查询。
- [x] 移除重复快照工具和拼写错误的占位模块。
- [ ] 补充 `frontend/` 页面与单元测试；`GET /api/tasks` 未找到时建议返回 404 而非 `{"error": ...}`。
- [ ] 为 OSV 查询、Semgrep 和大仓库补充更细粒度限流与覆盖记录。

---

## 许可证

未指定，按需补充。
