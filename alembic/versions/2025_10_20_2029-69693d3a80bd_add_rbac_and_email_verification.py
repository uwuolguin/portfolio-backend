"""add_rbac_and_email_verification

Revision ID: 69693d3a80bd
Revises: d9674160b661
Create Date: 2025-10-20 20:29:16.204383

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '69693d3a80bd'
down_revision: Union[str, Sequence[str], None] = 'd9674160b661'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('users', 
        sa.Column('role', sa.String(20), nullable=False, server_default='user'),
        schema='proveo'
    )
    
    op.add_column('users',
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'),
        schema='proveo'
    )
    op.add_column('users',
        sa.Column('verification_token', sa.Text(), nullable=True),
        schema='proveo'
    )
    op.add_column('users',
        sa.Column('verification_token_expires', sa.DateTime(timezone=True), nullable=True),
        schema='proveo'
    )
    
    op.create_index('idx_users_verification_token', 'users', ['verification_token'], schema='proveo')
    
    op.execute("""
        UPDATE proveo.users 
        SET role = 'admin', email_verified = true
        WHERE email = 'acos2014600836@gmail.com'
    """)
    
    op.add_column('users_deleted',
        sa.Column('role', sa.String(20), nullable=False, server_default='user'),
        schema='proveo'
    )
    op.add_column('users_deleted',
        sa.Column('email_verified', sa.Boolean(), nullable=False, server_default='false'),
        schema='proveo'
    )


def downgrade() -> None:
    op.drop_index('idx_users_verification_token', table_name='users', schema='proveo')
    
    op.drop_column('users', 'verification_token_expires', schema='proveo')
    op.drop_column('users', 'verification_token', schema='proveo')
    op.drop_column('users', 'email_verified', schema='proveo')
    op.drop_column('users', 'role', schema='proveo')
    
    op.drop_column('users_deleted', 'email_verified', schema='proveo')
    op.drop_column('users_deleted', 'role', schema='proveo')
