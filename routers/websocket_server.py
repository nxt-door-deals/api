import json
from typing import List

from better_profanity import profanity
from fastapi import Depends
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from sqlalchemy.orm import Session

from . import get_db
from . import router
from database.models import Chat
from database.models import ChatHistory


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

    # Update the "marked delete" columns so that the chat is visible in the user account
    db.query(Chat).filter(Chat.chat_id == chat_id).update(
        {Chat.marked_del_buyer: False, Chat.marked_del_seller: False}
    )

    db.commit()


# End points
@router.websocket("/ws")
async def default_websocket(
    websocket: WebSocket, db: Session = Depends(get_db)
):
    await manager.connect(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            data_json = json.loads(data)
            data_json["data"] = profanity.censor(data_json["data"])

            chat_id = data_json["chat_id"]
            client_id = data_json["client_id"]

            clients = get_valid_client_list(chat_id, db)

            if client_id in clients:
                data = json.dumps(data_json)
                save_chat_message(data, chat_id, db)
                await manager.broadcast(data)
            else:
                await handle_rejected_connections(websocket)

    except WebSocketDisconnect:
        manager.disconnect(websocket)
