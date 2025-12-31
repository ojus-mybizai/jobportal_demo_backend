"""drop qualification/experience and add job_categories json to jobs

Revision ID: 8c7d6c3c
Revises: 4b123add
Create Date: 2025-12-20 17:57:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
import app.models.base as base

# revision identifiers, used by Alembic.
revision: str = "8c7d6c3c"
down_revision: Union[str, Sequence[str], None] = "4b123add"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # drop old single-category FK and text fields
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("qualification")
        batch_op.drop_column("experience")
        batch_op.drop_constraint("jobs_job_category_id_fkey", type_="foreignkey")
        batch_op.drop_index("ix_jobs_job_category_id")
        batch_op.drop_column("job_category_id")
        batch_op.add_column(sa.Column("job_categories", sa.JSON(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("jobs") as batch_op:
        batch_op.drop_column("job_categories")
        batch_op.add_column(sa.Column("job_category_id", base.GUID(), nullable=True))
        batch_op.create_index("ix_jobs_job_category_id", ["job_category_id"], unique=False)
        batch_op.create_foreign_key(None, "master_job_category", ["job_category_id"], ["id"], ondelete=None)
        batch_op.add_column(sa.Column("experience", sa.Text(), nullable=True))
        batch_op.add_column(sa.Column("qualification", sa.Text(), nullable=True))
