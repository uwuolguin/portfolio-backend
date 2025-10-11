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
    op.execute("CREATE SCHEMA IF NOT EXISTS fastapi")
    op.execute("CREATE EXTENSION IF NOT EXISTS \"uuid-ossp\"")

    op.create_table(
        'communes',
        sa.Column('uuid', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='fastapi'
    )

    op.create_table(
        'communes_deleted',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='fastapi'
    )

    op.create_table(
        'companies_deleted',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('user_uuid', sa.UUID(), nullable=False),
        sa.Column('product_uuid', sa.UUID(), nullable=False),
        sa.Column('commune_uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description_es', sa.String(length=100), nullable=True),
        sa.Column('description_en', sa.String(length=100), nullable=True),
        sa.Column('address', sa.String(length=100), nullable=True),
        sa.Column('phone', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=100), nullable=True),
        sa.Column('image_url', sa.String(length=10000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='fastapi'
    )

    op.create_table(
        'products',
        sa.Column('uuid', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name_es', sa.String(length=100), nullable=False),
        sa.Column('name_en', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='fastapi'
    )

    op.create_table(
        'products_deleted',
        sa.Column('uuid', sa.UUID(), nullable=False),
        sa.Column('name_es', sa.String(length=100), nullable=False),
        sa.Column('name_en', sa.String(length=100), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('uuid'),
        schema='fastapi'
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
        schema='fastapi'
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
        schema='fastapi'
    )

    op.create_table(
        'companies',
        sa.Column('uuid', sa.UUID(), nullable=False, server_default=sa.text('gen_random_uuid()')),
        sa.Column('user_uuid', sa.UUID(), nullable=False),
        sa.Column('product_uuid', sa.UUID(), nullable=False),
        sa.Column('commune_uuid', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description_es', sa.String(length=100), nullable=True),
        sa.Column('description_en', sa.String(length=100), nullable=True),
        sa.Column('address', sa.String(length=100), nullable=True),
        sa.Column('phone', sa.String(length=100), nullable=True),
        sa.Column('email', sa.String(length=100), nullable=True),
        sa.Column('image_url', sa.String(length=10000), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['commune_uuid'], ['fastapi.communes.uuid']),
        sa.ForeignKeyConstraint(['product_uuid'], ['fastapi.products.uuid']),
        sa.ForeignKeyConstraint(['user_uuid'], ['fastapi.users.uuid']),
        sa.PrimaryKeyConstraint('uuid'),
        schema='fastapi'
    )