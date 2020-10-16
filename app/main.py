import database.models
from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import apartments, user, auth, heartbeat, email_messages
from database.db import engine

# Load environment variables
load_dotenv()

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
prefix = "/api/v1"

app.include_router(apartments.router, prefix=prefix)
app.include_router(user.router, prefix=prefix)
app.include_router(auth.router, prefix=prefix)
app.include_router(heartbeat.router, prefix=prefix)
app.include_router(email_messages.router, prefix=prefix)
