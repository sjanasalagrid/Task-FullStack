"""add otp to verifications
Revision ID: 9d3a7f4e8b2c
Revises: c7f9b8a6d5e4
Create Date: 2026-03-03 12:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '9d3a7f4e8b2c'
down_revision = 'c7f9b8a6d5e4'
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('verifications', sa.Column('otp', sa.String(length=6), nullable=True))


def downgrade():
    op.drop_column('verifications', 'otp')
