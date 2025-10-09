# app/routers/companies.py
from fastapi import APIRouter, Depends
from typing import List, Optional
from uuid import UUID
import asyncpg
from app.database.connection import get_db

router = APIRouter(
    prefix="/companies",
    tags=["companies"]
)

# Add your company endpoints here