import os

from dotenv import load_dotenv

# Load environment variables
load_dotenv()

from fastapi import FastAPI

from database import models
from database.db import engine
from routers import (
    ads,
    apartments,
    auth,
    email_messages,
    heartbeat,
    index,
    user,
    chat,
    websocket_server,
)

from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware

# Create all the database models
models.Base.metadata.create_all(bind=engine)

# Middleware definitions go here
origins = [os.getenv("CORS_ORIGIN_SERVER")]

middleware = [
    Middleware(
        CORSMiddleware,
        allow_origins=origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
]

app = FastAPI(middleware=middleware, docs_url=None, redoc_url=None)

# Routers go here
prefix = "/api/v1"

app.include_router(index.router)
app.include_router(apartments.router, prefix=prefix)
app.include_router(user.router, prefix=prefix)
app.include_router(auth.router, prefix=prefix)
app.include_router(heartbeat.router, prefix=prefix)
app.include_router(email_messages.router, prefix=prefix)
app.include_router(ads.router, prefix=prefix)
app.include_router(chat.router, prefix=prefix)
app.include_router(websocket_server.router)
