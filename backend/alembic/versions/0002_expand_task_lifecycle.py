"""Expand task lifecycle and resolved snapshot metadata."""

import sqlalchemy as sa
from alembic import op

revision = "0002_task_lifecycle"
down_revision = "0001_review_tasks"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("review_tasks", sa.Column("resolved_commit", sa.String(40), nullable=True))
    op.add_column(
        "review_tasks",
        sa.Column("description", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "review_tasks",
        sa.Column("deploy_type", sa.String(16), nullable=False, server_default="stdio"),
    )
    op.add_column(
        "review_tasks",
        sa.Column("stage", sa.String(), nullable=False, server_default="queued"),
    )
    op.add_column("review_tasks", sa.Column("error", sa.Text(), nullable=True))
    op.add_column(
        "review_tasks",
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
    )
    op.add_column("review_tasks", sa.Column("started_at", sa.DateTime(), nullable=True))
    op.add_column("review_tasks", sa.Column("finished_at", sa.DateTime(), nullable=True))
    op.create_index("ix_review_tasks_stage", "review_tasks", ["stage"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_review_tasks_stage", table_name="review_tasks")
    op.drop_column("review_tasks", "finished_at")
    op.drop_column("review_tasks", "started_at")
    op.drop_column("review_tasks", "updated_at")
    op.drop_column("review_tasks", "error")
    op.drop_column("review_tasks", "stage")
    op.drop_column("review_tasks", "deploy_type")
    op.drop_column("review_tasks", "description")
    op.drop_column("review_tasks", "resolved_commit")
