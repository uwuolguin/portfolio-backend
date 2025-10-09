# app/routers/communes.py
from fastapi import APIRouter, Depends
from typing import List
import asyncpg
from app.database.connection import get_db

router = APIRouter(
    prefix="/communes",
    tags=["communes"]
)

# Add your commune endpoints here