"""initial

Revision ID: 000_initial
Revises: 
Create Date: 2026-03-02 00:00:00.000000

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = '000_initial'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('username', sa.String(), nullable=False, unique=True),
        sa.Column('email', sa.String(), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
    )


def downgrade():
    op.drop_table('users')
