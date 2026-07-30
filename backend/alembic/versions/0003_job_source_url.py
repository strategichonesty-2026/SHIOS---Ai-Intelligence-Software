"""add source_url to jobs

Revision ID: 0003_job_source_url
Revises: 0002_interval_forecasts
Create Date: 2026-07-30
"""
from alembic import op
import sqlalchemy as sa

revision = "0003_job_source_url"
down_revision = "0002_interval_forecasts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("source_url", sa.String(1024), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "source_url")
