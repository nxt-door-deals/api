import database.models

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import apartments, user
from database.db import engine

# Create all the database models
database.models.Base.metadata.create_all(bind=engine)

app = FastAPI()

# Middleware definitions go here
origins = ["http://localhost:3000"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routers go here
app.include_router(apartments.router, prefix="/api/v1")
app.include_router(user.router, prefix="/api/v1")
