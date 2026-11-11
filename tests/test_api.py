from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from backend.app import main
from backend.app.database import Base
from backend.app.domain import ReviewStage, TaskStatus
from backend.app.models import ReviewTask


def _test_session_factory():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def test_review_api_lifecycle(monkeypatch):
    session_factory = _test_session_factory()
    dispatched: list[dict] = []

    monkeypatch.setattr(main, "SessionLocal", session_factory)
    monkeypatch.setattr(
        main.run_review,
        "apply_async",
        lambda **kwargs: dispatched.append(kwargs),
    )
    client = TestClient(main.app)

    live = client.get("/health/live")
    assert live.status_code == 200
    assert live.json()["status"] == "alive"

    submitted = client.post(
        "/api/submit",
        json={
            "repo_url": "https://github.com/example/mcp-server.git",
            "ref": "main",
            "description": "API integration test",
            "deploy_type": "stdio",
        },
    )
    assert submitted.status_code == 202
    task_id = submitted.json()["task_id"]
    assert submitted.json()["stage"] == "queued"
    assert dispatched[0]["args"] == [
        task_id,
        "https://github.com/example/mcp-server.git",
        "main",
        "stdio",
    ]

    detail = client.get(f"/api/tasks/{task_id}")
    assert detail.status_code == 200
    assert detail.json()["requested_ref"] == "main"

    listing = client.get("/api/tasks?limit=10&offset=0")
    assert listing.status_code == 200
    assert listing.json()["total"] == 1
    assert listing.json()["items"][0]["task_id"] == task_id

    markdown = client.get(f"/api/tasks/{task_id}/report")
    assert markdown.status_code == 200
    assert "MCP Audit security report" in markdown.text

    with session_factory.begin() as db:
        task = db.get(ReviewTask, task_id)
        task.status = TaskStatus.FAILED
        task.stage = ReviewStage.FAILED
        task.error = "temporary failure"

    retried = client.post(f"/api/tasks/{task_id}/retry")
    assert retried.status_code == 200
    assert retried.json()["status"] == "pending"
    assert len(dispatched) == 2

    missing = client.get("/api/tasks/does-not-exist")
    assert missing.status_code == 404
