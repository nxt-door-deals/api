from fastapi import APIRouter
from database.db import SessionLocal

router = APIRouter()


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
