"""add recommendation llm metadata

Adds urgency, prompt version, token usage and the context snapshot sent to the LLM.
NOT NULL columns without defaults: the table must be empty (no recommendations existed
before this migration).

Revision ID: 032911adf8f2
Revises: d3d9bd16ab2f
Create Date: 2026-11-25 11:56:27.478552

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = '032911adf8f2'
down_revision: Union[str, None] = 'd3d9bd16ab2f'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('ai_recommendations', sa.Column('urgency', sa.String(length=20), nullable=False))
    op.add_column('ai_recommendations', sa.Column('prompt_version', sa.String(length=50), nullable=False))
    op.add_column('ai_recommendations', sa.Column('prompt_tokens', sa.Integer(), nullable=True))
    op.add_column('ai_recommendations', sa.Column('completion_tokens', sa.Integer(), nullable=True))
    op.add_column('ai_recommendations', sa.Column('context', postgresql.JSONB(astext_type=sa.Text()), nullable=False))
    op.create_check_constraint(
        op.f('ck_ai_recommendations_urgency_valid'), 'ai_recommendations',
        "urgency IN ('IMMEDIATE', 'SOON', 'ROUTINE', 'NONE')",
    )
    op.create_check_constraint(
        op.f('ck_ai_recommendations_token_counts_non_negative'), 'ai_recommendations',
        "(prompt_tokens IS NULL OR prompt_tokens >= 0) "
        "AND (completion_tokens IS NULL OR completion_tokens >= 0)",
    )


def downgrade() -> None:
    op.drop_constraint(op.f('ck_ai_recommendations_token_counts_non_negative'), 'ai_recommendations', type_='check')
    op.drop_constraint(op.f('ck_ai_recommendations_urgency_valid'), 'ai_recommendations', type_='check')
    op.drop_column('ai_recommendations', 'context')
    op.drop_column('ai_recommendations', 'completion_tokens')
    op.drop_column('ai_recommendations', 'prompt_tokens')
    op.drop_column('ai_recommendations', 'prompt_version')
    op.drop_column('ai_recommendations', 'urgency')
