"""Interval forecasts and coverage scoring.

Adds nullable interval columns so predictions published under the point method
`ols_linear_v1` are left untouched (immutability rule) while new `ols_interval_v1`
predictions carry an 80% prediction interval and are scored on coverage.

Revision ID: 0002_interval_forecasts
Revises: 0001_initial
Create Date: 2026-07-26
"""
import sqlalchemy as sa

from alembic import op

revision = '0002_interval_forecasts'
down_revision = '0001_initial'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('predictions', sa.Column('lower_bound', sa.Float(), nullable=True))
    op.add_column('predictions', sa.Column('upper_bound', sa.Float(), nullable=True))
    op.add_column('predictions', sa.Column('interval_confidence', sa.Float(), nullable=True))
    op.add_column('prediction_results', sa.Column('interval_covered', sa.Boolean(), nullable=True))
    op.add_column('learning_feedback', sa.Column('coverage_correct', sa.Boolean(), nullable=True))


def downgrade() -> None:
    op.drop_column('learning_feedback', 'coverage_correct')
    op.drop_column('prediction_results', 'interval_covered')
    op.drop_column('predictions', 'interval_confidence')
    op.drop_column('predictions', 'upper_bound')
    op.drop_column('predictions', 'lower_bound')
