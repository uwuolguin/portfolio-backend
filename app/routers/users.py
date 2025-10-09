from fastapi import APIRouter, Depends
from typing import List
import asyncpg
from app.database.connection import get_db

router = APIRouter(
    prefix="/users",
    tags=["users"]
)

# Add your user endpoints here
