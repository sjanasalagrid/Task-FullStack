"""add verifications table
Revision ID: c7f9b8a6d5e4
Revises: bef8b33f7cd7
Create Date: 2026-03-02 12:50:00.000000
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c7f9b8a6d5e4'
down_revision = 'bef8b33f7cd7'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'verifications',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('token', sa.String(length=128), nullable=False),
        sa.Column('username', sa.String(length=50), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('expires_at', sa.DateTime(), nullable=False),
    )
    op.create_index(op.f('ix_verifications_token'), 'verifications', ['token'], unique=True)
    op.create_index(op.f('ix_verifications_username'), 'verifications', ['username'], unique=False)
    op.create_index(op.f('ix_verifications_email'), 'verifications', ['email'], unique=False)


def downgrade():
    op.drop_index(op.f('ix_verifications_email'), table_name='verifications')
    op.drop_index(op.f('ix_verifications_username'), table_name='verifications')
    op.drop_index(op.f('ix_verifications_token'), table_name='verifications')
    op.drop_table('verifications')
