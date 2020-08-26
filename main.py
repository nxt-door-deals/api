import database.models
from fastapi import FastAPI
from routers import apartments
from database.db import SessionLocal, engine


database.models.Base.metadata.create_all(bind=engine)

app = FastAPI()


# Dependency
def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


app.include_router(apartments.router)
