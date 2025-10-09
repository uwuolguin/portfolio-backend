# app/routers/products.py
from fastapi import APIRouter, Depends
from typing import List
import asyncpg
from app.database.connection import get_db

router = APIRouter(
    prefix="/products",
    tags=["products"]
)

# Add your product endpoints here
