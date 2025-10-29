"""adding second index to mat view

Revision ID: b999848032b2
Revises: 69693d3a80bd
Create Date: 2025-10-28 22:55:09.233454

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b999848032b2'
down_revision: Union[str, Sequence[str], None] = '69693d3a80bd'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("""
    CREATE UNIQUE INDEX IF NOT EXISTS idx_company_search_unique_id 
    ON proveo.company_search (company_id);
    """)

def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS proveo.idx_company_search_unique_id;")

