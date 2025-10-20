"""Initial migration 

Revision ID: 28de81bc6b20
Revises: 
Create Date: 2025-09-28 17:33:58.664718

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = '28de81bc6b20'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS proveo")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    op.create_table(
        'communes',
        sa.Column('uuid', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='proveo'
    )

    op.create_table(
        'communes_deleted',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='proveo'
    )

    op.create_table(
        'companies_deleted',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('user_uuid', sa.UUID(), nullable=False),
        sa.Column('product_uuid', sa.UUID(), nullable=False),
        sa.Column('commune_uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description_es', sa.String(length=100), nullable=False),
        sa.Column('description_en', sa.String(length=100), nullable=False),
        sa.Column('address', sa.String(length=100), nullable=False),
        sa.Column('phone', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('image_url', sa.String(length=10000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='proveo'
    )

    op.create_table(
        'products',
        sa.Column('uuid', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name_es', sa.String(length=100), nullable=False),
        sa.Column('name_en', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='proveo'
    )

    op.create_table(
        'products_deleted',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('name_es', sa.String(length=100), nullable=False),
        sa.Column('name_en', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='proveo'
    )

    op.create_table(
        'users',
        sa.Column('uuid', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('hashed_password', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        sa.UniqueConstraint('email'),
        schema='proveo'
    )

    op.create_table(
        'users_deleted',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('hashed_password', sa.Text(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='proveo'
    )

    op.create_table(
        'companies',
        sa.Column('uuid', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_uuid', sa.UUID(), nullable=False),
        sa.Column('product_uuid', sa.UUID(), nullable=False),
        sa.Column('commune_uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description_es', sa.String(length=100), nullable=False),
        sa.Column('description_en', sa.String(length=100), nullable=False),
        sa.Column('address', sa.String(length=100), nullable=False),
        sa.Column('phone', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=100), nullable=False),
        sa.Column('image_url', sa.String(length=10000), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['commune_uuid'], ['proveo.communes.uuid']),
        sa.ForeignKeyConstraint(['product_uuid'], ['proveo.products.uuid']),
        sa.ForeignKeyConstraint(['user_uuid'], ['proveo.users.uuid']),
        sa.PrimaryKeyConstraint('uuid'),
        schema='proveo'
    )
def downgrade() -> None:
    """Downgrade schema - drop all tables and schema"""
    op.drop_table('companies', schema='proveo')
    op.drop_table('users_deleted', schema='proveo')
    op.drop_table('users', schema='proveo')
    op.drop_table('products_deleted', schema='proveo')
    op.drop_table('products', schema='proveo')
    op.drop_table('companies_deleted', schema='proveo')
    op.drop_table('communes_deleted', schema='proveo')
    op.drop_table('communes', schema='proveo')
    
    op.execute("DROP SCHEMA IF EXISTS proveo CASCADE")
    