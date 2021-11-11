import asyncio
import json
from datetime import datetime
from typing import Dict
from typing import List

from better_profanity import profanity
from fastapi import Depends
from fastapi import Request
from fastapi import status
from fastapi import WebSocket
from fastapi import WebSocketDisconnect
from sentry_sdk import capture_exception
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from . import get_db
from . import router
from database.models import Chat
from database.models import ChatHistory


class ConnectionManager:
    def __init__(self):
        self.active_connections = []

    def create_connection_object(
        self,
        websocket: WebSocket,
        chat_id: str,
        private_chat_list: Dict,
        private_connections: List,
    ):
        private_connections.append(websocket)
        private_chat_list["chat_id"] = chat_id
        private_chat_list["private_connection_list"] = private_connections
        self.active_connections.append(private_chat_list.copy())

    async def connect(self, websocket: WebSocket, chat_id: str):
        """Creates the list of web socket connections. The list of dictionaries, will have
        the chat id and list of private connections as keys.

        private_chat_list = {
            "chat_id": "chat_id string",
            "private_connection_list":
                    [websocket_1, websocket_2] # always two connections per  chat id
        }
        """
        private_connections = []

        private_chat_list = {}
        await websocket.accept()

        if len(self.active_connections) != 0:
            for connection in self.active_connections:
                if connection["chat_id"] == chat_id:
                    private_connections = connection["private_connection_list"]
                    private_connections.append(websocket)
                    connection["private_connection_list"] = private_connections
                    break
            else:
                self.create_connection_object(
                    websocket, chat_id, private_chat_list, private_connections
                )
        else:
            self.create_connection_object(
                websocket, chat_id, private_chat_list, private_connections
            )

        # self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket, chat_id: str):
        if len(self.active_connections) != 0:
            for connection in self.active_connections:
                if connection["chat_id"] == chat_id:
                    connection["private_connection_list"].remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str, chat_id: str):
        if len(self.active_connections) != 0:
            for connection in self.active_connections:
                if connection["chat_id"] == chat_id:
                    for one_to_one_connection in connection[
                        "private_connection_list"
                    ]:
                        await one_to_one_connection.send_text(message)


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

    try:
        chat_history = (
            db.query(ChatHistory).filter(ChatHistory.chat_id == chat_id).first()
        )

        if chat_history.history:
            message_list = [history for history in chat_history.history]

        message_list.append(message_json)

        last_message = datetime.now()

        db.query(ChatHistory).filter(ChatHistory.chat_id == chat_id).update(
            {
                ChatHistory.history: message_list,
                ChatHistory.new_notifications: True,
                ChatHistory.last_chat_message: last_message,
            }
        )

        # Update the "marked delete" columns so that the chat is visible in the user account
        db.query(Chat).filter(Chat.chat_id == chat_id).update(
            {Chat.marked_del_buyer: False, Chat.marked_del_seller: False}
        )

        db.commit()
    except Exception as e:
        capture_exception(e)


async def check_for_new_notifications(
    user_id: str, request: Request, db: Session = Depends(get_db)
):
    chat_ids = (
        db.query(ChatHistory)
        .join(Chat)
        .filter(
            Chat.chat_id == ChatHistory.chat_id,
            or_(Chat.seller_id == user_id, Chat.buyer_id == user_id),
            ChatHistory.new_notifications == True,  # noqa,
        )
        .all()
    )

    if chat_ids:
        for chat in chat_ids:
            if await request.is_disconnected():
                break

            if (
                chat.history[-1]["sender"] != user_id
                and ((datetime.now() - chat.last_chat_message).total_seconds())
                < 120
            ):
                yield {"data": chat.chat_id}

    await asyncio.sleep(120)  # Run every 120 seconds


# End points
@router.websocket("/ws/")
async def default_websocket(
    websocket: WebSocket,
    chat_id: str,
    client_id: str,
    db: Session = Depends(get_db),
):

    clients = get_valid_client_list(chat_id, db)

    if client_id in clients:

        await manager.connect(websocket, chat_id)

        try:
            while True:
                data = await websocket.receive_text()
                data_json = json.loads(data)
                data_json["data"] = profanity.censor(data_json["data"])
                data = json.dumps(data_json)
                save_chat_message(data, chat_id, db)
                await manager.broadcast(data, chat_id)

        except WebSocketDisconnect:
            capture_exception()
            manager.disconnect(websocket, chat_id)
    else:
        await handle_rejected_connections(websocket)


@router.get("/new/chats", status_code=status.HTTP_200_OK)
async def new_chats(
    user_id: str, request: Request, db: Session = Depends(get_db)
):
    event_generator = check_for_new_notifications(user_id, request, db)
    return EventSourceResponse(event_generator)
