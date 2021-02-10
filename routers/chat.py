import hashlib
import json
import secrets
from typing import List
from typing import Optional

from better_profanity import profanity
from fastapi import Depends
from fastapi import HTTPException
from fastapi import status
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from pydantic import BaseModel
from sqlalchemy import and_
from sqlalchemy.exc import SQLAlchemyError
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


class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)


manager = ConnectionManager()


async def handle_rejected_connections(websocket: WebSocket):
    rejected_connections: List[WebSocket] = []
    await websocket.accept()
    rejected_connections.append(websocket)
    rejected_connections.remove(websocket)


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


def get_valid_client_list(chat_id: str, db: Session = Depends(get_db)):
    return list(
        db.query(Chat.seller_id, Chat.buyer_id)
        .filter(Chat.chat_id == chat_id)
        .first()
    )


def save_chat_message(data: str, chat_id: str, db: Session):
    message_list = []
    message_json = json.loads(data)

    chat_history = (
        db.query(ChatHistory).filter(ChatHistory.chat_id == chat_id).first()
    )

    if chat_history.history:
        message_list = [history for history in chat_history.history]

    message_list.append(message_json)

    db.query(ChatHistory).filter(ChatHistory.chat_id == chat_id).update(
        {ChatHistory.history: message_list, ChatHistory.new_notifications: True}
    )

    db.commit()


# End points
@router.websocket("/ws/")
async def default_websocket(
    websocket: WebSocket,
    chat_id: str,
    client_id: int,
    db: Session = Depends(get_db),
):

    clients = get_valid_client_list(chat_id, db)

    if client_id in clients:
        await manager.connect(websocket)

        try:
            while True:
                data = await websocket.receive_text()
                data_json = json.loads(data)
                data_json["data"] = profanity.censor(data_json["data"])
                data = json.dumps(data_json)
                save_chat_message(data, chat_id, db)
                await manager.broadcast(data)

        except WebSocketDisconnect:
            manager.disconnect(websocket)
    else:
        await handle_rejected_connections(websocket)


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
    except SQLAlchemyError:
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
    except SQLAlchemyError:
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
    except SQLAlchemyError:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Could not clear notification status",
        )
