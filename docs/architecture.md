# Architecture

MCP Audit is a five-service system: the browser talks to FastAPI; FastAPI persists review
requests in PostgreSQL and publishes jobs through Redis; Celery workers acquire an exact Git
commit, run isolated static analyzers, normalize evidence, and persist a deterministic decision.
Alembic owns schema changes and runs before the API and worker start.

The API never executes repository code. A review snapshot is detached from Git metadata before
analysis. Each analyzer records its own success, failure, duration, and finding count. Scanner
failure is coverage loss and therefore cannot produce a passing decision.

Result JSON uses a versioned schema with `findings`, `tool_runs`, `summary`, and `decision`.
New analyzers must return dictionaries that can be normalized by `evidence.normalize_finding` and
must be registered in `tasks._run_checks`.

