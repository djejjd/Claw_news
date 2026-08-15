"""create publication foundation

Revision ID: 20260815_01
Revises:
Create Date: 2026-08-15
"""

from alembic import op
from app.publication.models import Base

revision = "20260815_01"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.create_all(op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(op.get_bind())
