"""SHIOS v1 initial schema.

Enables the pgvector extension on PostgreSQL and types `normalized_documents.embedding`
as a real vector column there, while leaving it as JSON on other backends so the same
migration runs against SQLite in CI.

Revision ID: 0001_initial
Revises: 
Create Date: 2026-07-25 22:52:58.564753
"""
from alembic import op
import sqlalchemy as sa

from app.config import settings

EMBEDDING_DIM = settings.embedding_dim


revision = '0001_initial'
down_revision = None
branch_labels = None
depends_on = None


def _is_postgres() -> bool:
    return op.get_bind().dialect.name == "postgresql"


def upgrade() -> None:
    if _is_postgres():
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    op.create_table('agent_runs',
    sa.Column('agent', sa.String(length=64), nullable=False),
    sa.Column('agent_version', sa.String(length=16), nullable=False),
    sa.Column('status', sa.String(length=16), nullable=False),
    sa.Column('started_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('duration_ms', sa.Integer(), nullable=False),
    sa.Column('inputs', sa.JSON(), nullable=False),
    sa.Column('outputs', sa.JSON(), nullable=False),
    sa.Column('error', sa.Text(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_agent_runs_agent'), 'agent_runs', ['agent'], unique=False)
    op.create_index(op.f('ix_agent_runs_started_at'), 'agent_runs', ['started_at'], unique=False)
    op.create_index(op.f('ix_agent_runs_status'), 'agent_runs', ['status'], unique=False)
    op.create_table('companies',
    sa.Column('name', sa.String(length=255), nullable=False),
    sa.Column('domain', sa.String(length=255), nullable=True),
    sa.Column('company_metadata', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_companies_created_at'), 'companies', ['created_at'], unique=False)
    op.create_index(op.f('ix_companies_name'), 'companies', ['name'], unique=True)
    op.create_table('event_log',
    sa.Column('name', sa.String(length=64), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_event_log_created_at'), 'event_log', ['created_at'], unique=False)
    op.create_index(op.f('ix_event_log_name'), 'event_log', ['name'], unique=False)
    op.create_table('knowledge_records',
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('subject', sa.String(length=255), nullable=False),
    sa.Column('predicate', sa.String(length=64), nullable=False),
    sa.Column('object', sa.String(length=255), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('evidence_ids', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_knowledge_records_created_at'), 'knowledge_records', ['created_at'], unique=False)
    op.create_index('ix_knowledge_spo', 'knowledge_records', ['subject', 'predicate', 'object'], unique=False)
    op.create_table('predictions',
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('statement', sa.Text(), nullable=False),
    sa.Column('domain', sa.String(length=32), nullable=False),
    sa.Column('metric', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=32), nullable=False),
    sa.Column('entity_name', sa.String(length=128), nullable=False),
    sa.Column('horizon', sa.String(length=32), nullable=False),
    sa.Column('target_period', sa.String(length=16), nullable=False),
    sa.Column('predicted_value', sa.Float(), nullable=False),
    sa.Column('predicted_direction', sa.String(length=8), nullable=False),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('supporting_evidence_ids', sa.JSON(), nullable=False),
    sa.Column('trend_ids', sa.JSON(), nullable=False),
    sa.Column('assumptions', sa.JSON(), nullable=False),
    sa.Column('risks', sa.JSON(), nullable=False),
    sa.Column('method', sa.String(length=64), nullable=False),
    sa.Column('review_date', sa.Date(), nullable=False),
    sa.Column('expiration_date', sa.Date(), nullable=False),
    sa.Column('version', sa.Integer(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_predictions_created_at'), 'predictions', ['created_at'], unique=False)
    op.create_index(op.f('ix_predictions_domain'), 'predictions', ['domain'], unique=False)
    op.create_index(op.f('ix_predictions_entity_name'), 'predictions', ['entity_name'], unique=False)
    op.create_index(op.f('ix_predictions_entity_type'), 'predictions', ['entity_type'], unique=False)
    op.create_index(op.f('ix_predictions_expiration_date'), 'predictions', ['expiration_date'], unique=False)
    op.create_index(op.f('ix_predictions_status'), 'predictions', ['status'], unique=False)
    op.create_index('ix_predictions_status_exp', 'predictions', ['status', 'expiration_date'], unique=False)
    op.create_index(op.f('ix_predictions_target_period'), 'predictions', ['target_period'], unique=False)
    op.create_table('raw_documents',
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('source', sa.String(length=64), nullable=False),
    sa.Column('external_id', sa.String(length=255), nullable=False),
    sa.Column('collected_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('content', sa.Text(), nullable=False),
    sa.Column('content_hash', sa.String(length=64), nullable=False),
    sa.Column('doc_metadata', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('source', 'external_id', name='uq_raw_source_external')
    )
    op.create_index('ix_raw_documents_collected_at', 'raw_documents', ['collected_at'], unique=False)
    op.create_index(op.f('ix_raw_documents_content_hash'), 'raw_documents', ['content_hash'], unique=False)
    op.create_index(op.f('ix_raw_documents_source'), 'raw_documents', ['source'], unique=False)
    op.create_table('reports',
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('report_type', sa.String(length=48), nullable=False),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('subtitle', sa.String(length=255), nullable=False),
    sa.Column('body_markdown', sa.Text(), nullable=False),
    sa.Column('payload', sa.JSON(), nullable=False),
    sa.Column('evidence_ids', sa.JSON(), nullable=False),
    sa.Column('period_start', sa.String(length=16), nullable=False),
    sa.Column('period_end', sa.String(length=16), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_reports_created_at'), 'reports', ['created_at'], unique=False)
    op.create_index(op.f('ix_reports_report_type'), 'reports', ['report_type'], unique=False)
    op.create_table('skills',
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_skills_created_at'), 'skills', ['created_at'], unique=False)
    op.create_index(op.f('ix_skills_name'), 'skills', ['name'], unique=True)
    op.create_table('technologies',
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('category', sa.String(length=64), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_technologies_created_at'), 'technologies', ['created_at'], unique=False)
    op.create_index(op.f('ix_technologies_name'), 'technologies', ['name'], unique=True)
    op.create_table('trends',
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('metric', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=32), nullable=False),
    sa.Column('entity_name', sa.String(length=128), nullable=False),
    sa.Column('period', sa.String(length=16), nullable=False),
    sa.Column('value', sa.Float(), nullable=False),
    sa.Column('delta', sa.Float(), nullable=False),
    sa.Column('delta_pct', sa.Float(), nullable=False),
    sa.Column('direction', sa.String(length=8), nullable=False),
    sa.Column('sample_size', sa.Integer(), nullable=False),
    sa.Column('evidence_ids', sa.JSON(), nullable=False),
    sa.Column('computed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('metric', 'entity_type', 'entity_name', 'period', name='uq_trend_slice')
    )
    op.create_index(op.f('ix_trends_computed_at'), 'trends', ['computed_at'], unique=False)
    op.create_index(op.f('ix_trends_entity_name'), 'trends', ['entity_name'], unique=False)
    op.create_index(op.f('ix_trends_entity_type'), 'trends', ['entity_type'], unique=False)
    op.create_index('ix_trends_lookup', 'trends', ['metric', 'entity_type', 'entity_name', 'period'], unique=False)
    op.create_index(op.f('ix_trends_metric'), 'trends', ['metric'], unique=False)
    op.create_index(op.f('ix_trends_period'), 'trends', ['period'], unique=False)
    op.create_table('users',
    sa.Column('email', sa.String(length=255), nullable=False),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('role', sa.String(length=32), nullable=False),
    sa.Column('api_key_hash', sa.String(length=128), nullable=True),
    sa.Column('is_active', sa.Boolean(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_users_created_at'), 'users', ['created_at'], unique=False)
    op.create_index(op.f('ix_users_email'), 'users', ['email'], unique=True)
    op.create_table('validation_results',
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('target_type', sa.String(length=32), nullable=False),
    sa.Column('target_id', sa.String(length=36), nullable=False),
    sa.Column('is_valid', sa.Boolean(), nullable=False),
    sa.Column('issues', sa.JSON(), nullable=False),
    sa.Column('missing_evidence', sa.JSON(), nullable=False),
    sa.Column('contradictory_evidence', sa.JSON(), nullable=False),
    sa.Column('unknowns_noted', sa.JSON(), nullable=False),
    sa.Column('validated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_validation_results_validated_at'), 'validation_results', ['validated_at'], unique=False)
    op.create_index('ix_validation_target', 'validation_results', ['target_type', 'target_id'], unique=False)
    op.create_table('dashboards',
    sa.Column('user_id', sa.String(length=36), nullable=True),
    sa.Column('name', sa.String(length=128), nullable=False),
    sa.Column('config', sa.JSON(), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['user_id'], ['users.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_dashboards_created_at'), 'dashboards', ['created_at'], unique=False)
    op.create_table('learning_feedback',
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('prediction_id', sa.String(length=36), nullable=False),
    sa.Column('prediction_result_id', sa.String(length=36), nullable=False),
    sa.Column('metric', sa.String(length=64), nullable=False),
    sa.Column('entity_type', sa.String(length=32), nullable=False),
    sa.Column('accuracy_score', sa.Float(), nullable=False),
    sa.Column('false_positive', sa.Boolean(), nullable=False),
    sa.Column('false_negative', sa.Boolean(), nullable=False),
    sa.Column('confidence_calibration_delta', sa.Float(), nullable=False),
    sa.Column('signal_quality_notes', sa.Text(), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_learning_feedback_created_at'), 'learning_feedback', ['created_at'], unique=False)
    op.create_index(op.f('ix_learning_feedback_entity_type'), 'learning_feedback', ['entity_type'], unique=False)
    op.create_index(op.f('ix_learning_feedback_metric'), 'learning_feedback', ['metric'], unique=False)
    op.create_index(op.f('ix_learning_feedback_prediction_id'), 'learning_feedback', ['prediction_id'], unique=False)
    op.create_index(op.f('ix_learning_feedback_prediction_result_id'), 'learning_feedback', ['prediction_result_id'], unique=False)
    op.create_table('normalized_documents',
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('raw_document_id', sa.String(length=36), nullable=False),
    sa.Column('doc_type', sa.String(length=32), nullable=False),
    sa.Column('title', sa.String(length=512), nullable=False),
    sa.Column('body_text', sa.Text(), nullable=False),
    sa.Column('entities', sa.JSON(), nullable=False),
    sa.Column('source', sa.String(length=64), nullable=False),
    sa.Column('observed_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('embedding', sa.JSON(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['raw_document_id'], ['raw_documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_norm_doctype_created', 'normalized_documents', ['doc_type', 'created_at'], unique=False)
    op.create_index(op.f('ix_normalized_documents_created_at'), 'normalized_documents', ['created_at'], unique=False)
    op.create_index(op.f('ix_normalized_documents_doc_type'), 'normalized_documents', ['doc_type'], unique=False)
    op.create_index(op.f('ix_normalized_documents_observed_at'), 'normalized_documents', ['observed_at'], unique=False)
    op.create_index(op.f('ix_normalized_documents_raw_document_id'), 'normalized_documents', ['raw_document_id'], unique=False)
    op.create_index(op.f('ix_normalized_documents_source'), 'normalized_documents', ['source'], unique=False)
    op.create_table('prediction_results',
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('prediction_id', sa.String(length=36), nullable=False),
    sa.Column('reality_period', sa.String(length=16), nullable=False),
    sa.Column('actual_value', sa.Float(), nullable=False),
    sa.Column('predicted_value', sa.Float(), nullable=False),
    sa.Column('accuracy_score', sa.Float(), nullable=False),
    sa.Column('deviation', sa.Float(), nullable=False),
    sa.Column('direction_correct', sa.Boolean(), nullable=False),
    sa.Column('notes', sa.Text(), nullable=False),
    sa.Column('evaluated_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_prediction_results_evaluated_at'), 'prediction_results', ['evaluated_at'], unique=False)
    op.create_index(op.f('ix_prediction_results_prediction_id'), 'prediction_results', ['prediction_id'], unique=True)
    op.create_table('recommendations',
    sa.Column('schema_version', sa.String(length=16), nullable=False),
    sa.Column('audience_type', sa.String(length=32), nullable=False),
    sa.Column('domain', sa.String(length=32), nullable=False),
    sa.Column('recommendation_text', sa.Text(), nullable=False),
    sa.Column('rationale', sa.Text(), nullable=False),
    sa.Column('evidence_ids', sa.JSON(), nullable=False),
    sa.Column('trend_ids', sa.JSON(), nullable=False),
    sa.Column('prediction_id', sa.String(length=36), nullable=True),
    sa.Column('confidence', sa.Float(), nullable=False),
    sa.Column('alternative_scenarios', sa.JSON(), nullable=False),
    sa.Column('risks', sa.JSON(), nullable=False),
    sa.Column('expected_outcomes', sa.JSON(), nullable=False),
    sa.Column('status', sa.String(length=24), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.ForeignKeyConstraint(['prediction_id'], ['predictions.id'], ondelete='SET NULL'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_recommendations_audience_type'), 'recommendations', ['audience_type'], unique=False)
    op.create_index(op.f('ix_recommendations_created_at'), 'recommendations', ['created_at'], unique=False)
    op.create_index(op.f('ix_recommendations_domain'), 'recommendations', ['domain'], unique=False)
    op.create_index(op.f('ix_recommendations_prediction_id'), 'recommendations', ['prediction_id'], unique=False)
    op.create_index(op.f('ix_recommendations_status'), 'recommendations', ['status'], unique=False)
    op.create_index('ix_recs_audience_created', 'recommendations', ['audience_type', 'created_at'], unique=False)
    op.create_table('evidence',
    sa.Column('normalized_document_id', sa.String(length=36), nullable=False),
    sa.Column('entity_type', sa.String(length=32), nullable=False),
    sa.Column('entity_name', sa.String(length=128), nullable=False),
    sa.Column('period', sa.String(length=16), nullable=False),
    sa.Column('snippet', sa.Text(), nullable=False),
    sa.Column('weight', sa.Float(), nullable=False),
    sa.Column('source', sa.String(length=64), nullable=False),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['normalized_document_id'], ['normalized_documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_evidence_created_at'), 'evidence', ['created_at'], unique=False)
    op.create_index('ix_evidence_entity', 'evidence', ['entity_type', 'entity_name', 'period'], unique=False)
    op.create_index(op.f('ix_evidence_entity_name'), 'evidence', ['entity_name'], unique=False)
    op.create_index(op.f('ix_evidence_entity_type'), 'evidence', ['entity_type'], unique=False)
    op.create_index(op.f('ix_evidence_normalized_document_id'), 'evidence', ['normalized_document_id'], unique=False)
    op.create_index(op.f('ix_evidence_period'), 'evidence', ['period'], unique=False)
    op.create_table('jobs',
    sa.Column('normalized_document_id', sa.String(length=36), nullable=False),
    sa.Column('company_id', sa.String(length=36), nullable=True),
    sa.Column('title', sa.String(length=255), nullable=False),
    sa.Column('normalized_role', sa.String(length=128), nullable=False),
    sa.Column('seniority', sa.String(length=32), nullable=False),
    sa.Column('location', sa.String(length=255), nullable=False),
    sa.Column('remote_type', sa.String(length=32), nullable=False),
    sa.Column('posted_at', sa.DateTime(timezone=True), nullable=False),
    sa.Column('skills', sa.JSON(), nullable=False),
    sa.Column('technologies', sa.JSON(), nullable=False),
    sa.Column('salary_min', sa.Float(), nullable=True),
    sa.Column('salary_max', sa.Float(), nullable=True),
    sa.Column('id', sa.String(length=36), nullable=False),
    sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['company_id'], ['companies.id'], ),
    sa.ForeignKeyConstraint(['normalized_document_id'], ['normalized_documents.id'], ondelete='CASCADE'),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_jobs_company_id'), 'jobs', ['company_id'], unique=False)
    op.create_index(op.f('ix_jobs_created_at'), 'jobs', ['created_at'], unique=False)
    op.create_index(op.f('ix_jobs_normalized_document_id'), 'jobs', ['normalized_document_id'], unique=False)
    op.create_index(op.f('ix_jobs_normalized_role'), 'jobs', ['normalized_role'], unique=False)
    op.create_index(op.f('ix_jobs_posted_at'), 'jobs', ['posted_at'], unique=False)
    if _is_postgres():
        op.execute("ALTER TABLE normalized_documents DROP COLUMN embedding")
        op.execute(f"ALTER TABLE normalized_documents ADD COLUMN embedding vector({EMBEDDING_DIM})")
        # Approximate-nearest-neighbour index. Build it after the first backfill so the
        # list count is chosen against real data; it is safe to create on an empty table.
        op.execute(
            "CREATE INDEX IF NOT EXISTS ix_normalized_documents_embedding "
            "ON normalized_documents USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100)"
        )


def downgrade() -> None:
    op.drop_index(op.f('ix_jobs_posted_at'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_normalized_role'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_normalized_document_id'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_created_at'), table_name='jobs')
    op.drop_index(op.f('ix_jobs_company_id'), table_name='jobs')
    op.drop_table('jobs')
    op.drop_index(op.f('ix_evidence_period'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_normalized_document_id'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_entity_type'), table_name='evidence')
    op.drop_index(op.f('ix_evidence_entity_name'), table_name='evidence')
    op.drop_index('ix_evidence_entity', table_name='evidence')
    op.drop_index(op.f('ix_evidence_created_at'), table_name='evidence')
    op.drop_table('evidence')
    op.drop_index('ix_recs_audience_created', table_name='recommendations')
    op.drop_index(op.f('ix_recommendations_status'), table_name='recommendations')
    op.drop_index(op.f('ix_recommendations_prediction_id'), table_name='recommendations')
    op.drop_index(op.f('ix_recommendations_domain'), table_name='recommendations')
    op.drop_index(op.f('ix_recommendations_created_at'), table_name='recommendations')
    op.drop_index(op.f('ix_recommendations_audience_type'), table_name='recommendations')
    op.drop_table('recommendations')
    op.drop_index(op.f('ix_prediction_results_prediction_id'), table_name='prediction_results')
    op.drop_index(op.f('ix_prediction_results_evaluated_at'), table_name='prediction_results')
    op.drop_table('prediction_results')
    op.drop_index(op.f('ix_normalized_documents_source'), table_name='normalized_documents')
    op.drop_index(op.f('ix_normalized_documents_raw_document_id'), table_name='normalized_documents')
    op.drop_index(op.f('ix_normalized_documents_observed_at'), table_name='normalized_documents')
    op.drop_index(op.f('ix_normalized_documents_doc_type'), table_name='normalized_documents')
    op.drop_index(op.f('ix_normalized_documents_created_at'), table_name='normalized_documents')
    op.drop_index('ix_norm_doctype_created', table_name='normalized_documents')
    op.drop_table('normalized_documents')
    op.drop_index(op.f('ix_learning_feedback_prediction_result_id'), table_name='learning_feedback')
    op.drop_index(op.f('ix_learning_feedback_prediction_id'), table_name='learning_feedback')
    op.drop_index(op.f('ix_learning_feedback_metric'), table_name='learning_feedback')
    op.drop_index(op.f('ix_learning_feedback_entity_type'), table_name='learning_feedback')
    op.drop_index(op.f('ix_learning_feedback_created_at'), table_name='learning_feedback')
    op.drop_table('learning_feedback')
    op.drop_index(op.f('ix_dashboards_created_at'), table_name='dashboards')
    op.drop_table('dashboards')
    op.drop_index('ix_validation_target', table_name='validation_results')
    op.drop_index(op.f('ix_validation_results_validated_at'), table_name='validation_results')
    op.drop_table('validation_results')
    op.drop_index(op.f('ix_users_email'), table_name='users')
    op.drop_index(op.f('ix_users_created_at'), table_name='users')
    op.drop_table('users')
    op.drop_index(op.f('ix_trends_period'), table_name='trends')
    op.drop_index(op.f('ix_trends_metric'), table_name='trends')
    op.drop_index('ix_trends_lookup', table_name='trends')
    op.drop_index(op.f('ix_trends_entity_type'), table_name='trends')
    op.drop_index(op.f('ix_trends_entity_name'), table_name='trends')
    op.drop_index(op.f('ix_trends_computed_at'), table_name='trends')
    op.drop_table('trends')
    op.drop_index(op.f('ix_technologies_name'), table_name='technologies')
    op.drop_index(op.f('ix_technologies_created_at'), table_name='technologies')
    op.drop_table('technologies')
    op.drop_index(op.f('ix_skills_name'), table_name='skills')
    op.drop_index(op.f('ix_skills_created_at'), table_name='skills')
    op.drop_table('skills')
    op.drop_index(op.f('ix_reports_report_type'), table_name='reports')
    op.drop_index(op.f('ix_reports_created_at'), table_name='reports')
    op.drop_table('reports')
    op.drop_index(op.f('ix_raw_documents_source'), table_name='raw_documents')
    op.drop_index(op.f('ix_raw_documents_content_hash'), table_name='raw_documents')
    op.drop_index('ix_raw_documents_collected_at', table_name='raw_documents')
    op.drop_table('raw_documents')
    op.drop_index(op.f('ix_predictions_target_period'), table_name='predictions')
    op.drop_index('ix_predictions_status_exp', table_name='predictions')
    op.drop_index(op.f('ix_predictions_status'), table_name='predictions')
    op.drop_index(op.f('ix_predictions_expiration_date'), table_name='predictions')
    op.drop_index(op.f('ix_predictions_entity_type'), table_name='predictions')
    op.drop_index(op.f('ix_predictions_entity_name'), table_name='predictions')
    op.drop_index(op.f('ix_predictions_domain'), table_name='predictions')
    op.drop_index(op.f('ix_predictions_created_at'), table_name='predictions')
    op.drop_table('predictions')
    op.drop_index('ix_knowledge_spo', table_name='knowledge_records')
    op.drop_index(op.f('ix_knowledge_records_created_at'), table_name='knowledge_records')
    op.drop_table('knowledge_records')
    op.drop_index(op.f('ix_event_log_name'), table_name='event_log')
    op.drop_index(op.f('ix_event_log_created_at'), table_name='event_log')
    op.drop_table('event_log')
    op.drop_index(op.f('ix_companies_name'), table_name='companies')
    op.drop_index(op.f('ix_companies_created_at'), table_name='companies')
    op.drop_table('companies')
    op.drop_index(op.f('ix_agent_runs_status'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_started_at'), table_name='agent_runs')
    op.drop_index(op.f('ix_agent_runs_agent'), table_name='agent_runs')
    op.drop_table('agent_runs')
    # ### end Alembic commands ###
