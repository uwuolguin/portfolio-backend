"""add_unique_constraint_one_company_per_user

Revision ID: d9674160b661
Revises: c70f6d3ab4ec
Create Date: 2025-10-14 21:53:53.453301

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd9674160b661'
down_revision: Union[str, Sequence[str], None] = 'c70f6d3ab4ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_unique_constraint(
        'uq_companies_user_uuid', 
        'companies',              
        ['user_uuid'],             
        schema='fastapi'
    )


def downgrade() -> None:
    op.drop_constraint(
        'uq_companies_user_uuid',
        'companies',
        schema='fastapi'
    )