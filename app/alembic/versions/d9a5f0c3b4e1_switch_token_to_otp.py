"""switch token field to otp
Revision ID: d9a5f0c3b4e1
Revises: c7f9b8a6d5e4
Create Date: 2026-03-03 10:00:00.000000
"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = 'd9a5f0c3b4e1'
down_revision = 'c7f9b8a6d5e4'
branch_labels = None
depends_on = None


def upgrade():
    # add otp column
    op.add_column('verifications', sa.Column('otp', sa.String(length=6), nullable=False, server_default='000000'))
    # populate otp with placeholder if needed (should be replaced by application)
    # drop token column and its indexes
    with op.batch_alter_table('verifications') as batch_op:
        batch_op.drop_index('ix_verifications_token')
        batch_op.drop_column('token')
    # remove server default
    op.alter_column('verifications', 'otp', server_default=None)


def downgrade():
    # re-create token column
    op.add_column('verifications', sa.Column('token', sa.String(length=128), nullable=False, server_default=''))
    with op.batch_alter_table('verifications') as batch_op:
        batch_op.create_index('ix_verifications_token', ['token'], unique=True)
        batch_op.drop_column('otp')

    op.alter_column('verifications', 'token', server_default=None)
