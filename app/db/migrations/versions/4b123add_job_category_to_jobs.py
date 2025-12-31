"""add job_category to jobs

Revision ID: 4b123add
Revises: 0ac56b5ea41c
Create Date: 2025-12-20 15:08:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.models.base as base

# revision identifiers, used by Alembic.
revision: str = "4b123add"
down_revision: Union[str, Sequence[str], None] = "0ac56b5ea41c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "jobs",
        sa.Column("job_category_id", base.GUID(), nullable=True),
    )
    op.create_index("ix_jobs_job_category_id", "jobs", ["job_category_id"], unique=False)
    op.create_foreign_key(
        None,
        "jobs",
        "master_job_category",
        ["job_category_id"],
        ["id"],
        ondelete=None,
    )


def downgrade() -> None:
    op.drop_constraint("jobs_job_category_id_fkey", "jobs", type_="foreignkey")
    op.drop_index("ix_jobs_job_category_id", table_name="jobs")
    op.drop_column("jobs", "job_category_id")
