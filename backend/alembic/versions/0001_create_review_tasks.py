"""Create the initial review_tasks table."""

from alembic import op
import sqlalchemy as sa


revision = "0001_review_tasks"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "review_tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("repo_url", sa.String(), nullable=False),
        sa.Column("ref", sa.String(), nullable=False),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_review_tasks_id", "review_tasks", ["id"], unique=False)
    op.create_index("ix_review_tasks_repo_url", "review_tasks", ["repo_url"], unique=False)
    op.create_index("ix_review_tasks_status", "review_tasks", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_review_tasks_status", table_name="review_tasks")
    op.drop_index("ix_review_tasks_repo_url", table_name="review_tasks")
    op.drop_index("ix_review_tasks_id", table_name="review_tasks")
    op.drop_table("review_tasks")
