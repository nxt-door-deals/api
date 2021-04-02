import hashlib
import secrets
from typing import Optional

from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from pydantic import BaseModel
from sentry_sdk import capture_exception
from sqlalchemy import and_
from sqlalchemy.orm import Session

from . import get_db
from . import router
from database.models import Chat
from database.models import ChatHistory


class ChatBase(BaseModel):
    ad_id: int
    seller_id: int
    buyer_id: Optional[int]


class ChatMessage(BaseModel):
    data: str
    sender: int


def get_chat_record(
    ad_id: int, seller_id: int, buyer_id: int, db: Session = Depends(get_db)
):

    chat_id = (
        db.query(Chat.chat_id)
        .filter(
            and_(
                Chat.ad_id == ad_id,
                Chat.seller_id == seller_id,
                Chat.buyer_id == buyer_id,
            )
        )
        .first()
    )

    if not chat_id:
        return None

    return chat_id[0]


@router.get("/chat")
def get_chat_details(
    ad_id: int, seller_id: int, buyer_id: int, db: Session = Depends(get_db)
):
    chat_id = get_chat_record(ad_id, seller_id, buyer_id, db)

    if chat_id:
        return chat_id
    else:
        return None


@router.post("/chat/create", status_code=status.HTTP_201_CREATED)
def create_chat(chat: ChatBase, db: Session = Depends(get_db)):
    chat_id = hashlib.sha256(secrets.token_hex(64).encode()).hexdigest()

    new_chat = Chat(
        ad_id=chat.ad_id,
        seller_id=chat.seller_id,
        buyer_id=chat.buyer_id,
        chat_id=chat_id,
    )

    new_chat_history = ChatHistory(chat_id=chat_id, history=None)

    try:
        db.add(new_chat)
        db.add(new_chat_history)
        db.commit()

        return chat_id
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error creating new chat record",
        )


@router.get("/chat/history/{chat_id}", status_code=status.HTTP_200_OK)
def get_chat_history(chat_id: str, db: Session = Depends(get_db)):

    try:
        chat_history = (
            db.query(ChatHistory).filter(ChatHistory.chat_id == chat_id).first()
        )

        if chat_history:
            return chat_history.history or None
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No chat history"
        )


@router.put(
    "/chat/notifications/{chat_id}", status_code=status.HTTP_201_CREATED
)
def update_notifications(chat_id: str, db: Session = Depends(get_db)):
    try:
        db.query(ChatHistory).filter(ChatHistory.chat_id == chat_id).update(
            {ChatHistory.new_notifications: False}
        )

        db.commit()
    except Exception as e:
        capture_exception(e)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not clear notification status",
        )
