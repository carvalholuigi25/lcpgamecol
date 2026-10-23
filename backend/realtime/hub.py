"""Live library updates over the ASP.NET Core SignalR protocol.

FastAPI has no SignalR server, so this module speaks the protocol itself: the JSON
hub protocol over the WebSockets transport, which is all the browser's
@microsoft/signalr client and Python's signalrcore client need. The hub only pushes
server events; it exposes no callable hub methods.

Connections live in this process, so run a single worker (or add a shared backplane
such as Redis) before scaling out.
"""

import asyncio
import json
import logging
import secrets
import threading
import time
from dataclasses import dataclass, field

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, status

from backend.auth import auth

HUB_PATH = "/hubs/library"
RECORD_SEPARATOR = "\x1e"
HANDSHAKE_TIMEOUT_SECONDS = 15
KEEP_ALIVE_SECONDS = 15
NEGOTIATION_TTL_SECONDS = 60

MESSAGE_INVOCATION = 1
MESSAGE_COMPLETION = 3
MESSAGE_PING = 6
MESSAGE_CLOSE = 7

logger = logging.getLogger(__name__)
router = APIRouter(tags=["realtime"])


def encode_message(message: dict) -> str:
    return json.dumps(message, separators=(",", ":"), default=str) + RECORD_SEPARATOR


def decode_messages(payload: str) -> list[dict]:
    return [json.loads(record) for record in payload.split(RECORD_SEPARATOR) if record]


@dataclass
class _Connection:
    websocket: WebSocket
    principal: auth.Principal
    send_lock: asyncio.Lock = field(default_factory=asyncio.Lock)

    async def send(self, text: str) -> None:
        async with self.send_lock:
            await self.websocket.send_text(text)


class LibraryHub:
    def __init__(self) -> None:
        self._negotiations: dict[str, tuple[str, float]] = {}
        self._connections: dict[str, _Connection] = {}
        self._lock = threading.Lock()
        self._loop: asyncio.AbstractEventLoop | None = None

    @property
    def connection_count(self) -> int:
        return len(self._connections)

    def negotiate(self, principal: auth.Principal) -> dict:
        token = secrets.token_urlsafe(24)
        now = time.monotonic()
        with self._lock:
            self._negotiations = {
                key: value for key, value in self._negotiations.items() if value[1] > now
            }
            self._negotiations[token] = (principal.username, now + NEGOTIATION_TTL_SECONDS)
        # The browser client sends connectionToken back as ?id=, signalrcore sends
        # connectionId, so both carry the same one-time value.
        return {
            "negotiateVersion": 1,
            "connectionId": token,
            "connectionToken": token,
            "availableTransports": [
                {"transport": "WebSockets", "transferFormats": ["Text"]}
            ],
        }

    def _claim_negotiation(self, token: str, principal: auth.Principal) -> bool:
        with self._lock:
            username, expires = self._negotiations.pop(token, ("", 0.0))
        return expires > time.monotonic() and username == principal.username

    async def serve(self, websocket: WebSocket, principal: auth.Principal) -> None:
        connection_token = websocket.query_params.get("id")
        await websocket.accept()
        if connection_token and not self._claim_negotiation(connection_token, principal):
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return

        try:
            handshake = await asyncio.wait_for(
                websocket.receive_text(), HANDSHAKE_TIMEOUT_SECONDS
            )
            request = decode_messages(handshake)[0]
        except (asyncio.TimeoutError, json.JSONDecodeError, IndexError, WebSocketDisconnect):
            await _close_quietly(websocket, status.WS_1002_PROTOCOL_ERROR)
            return
        if request.get("protocol") != "json" or request.get("version") != 1:
            await websocket.send_text(
                encode_message({"error": "Only the JSON hub protocol version 1 is supported."})
            )
            await _close_quietly(websocket, status.WS_1002_PROTOCOL_ERROR)
            return

        connection = _Connection(websocket, principal)
        await connection.send(encode_message({}))
        connection_id = connection_token or secrets.token_urlsafe(24)
        self._loop = asyncio.get_running_loop()
        with self._lock:
            self._connections[connection_id] = connection
        keep_alive = asyncio.create_task(self._keep_alive(connection))
        try:
            while True:
                for message in decode_messages(await websocket.receive_text()):
                    if message.get("type") == MESSAGE_CLOSE:
                        return
                    if message.get("type") == MESSAGE_INVOCATION and message.get("invocationId"):
                        await connection.send(
                            encode_message(
                                {
                                    "type": MESSAGE_COMPLETION,
                                    "invocationId": message["invocationId"],
                                    "error": "This hub does not accept invocations.",
                                }
                            )
                        )
        except (WebSocketDisconnect, json.JSONDecodeError, RuntimeError):
            pass
        finally:
            keep_alive.cancel()
            with self._lock:
                self._connections.pop(connection_id, None)
            await _close_quietly(websocket, status.WS_1000_NORMAL_CLOSURE)

    async def _keep_alive(self, connection: _Connection) -> None:
        ping = encode_message({"type": MESSAGE_PING})
        try:
            while True:
                await asyncio.sleep(KEEP_ALIVE_SECONDS)
                await connection.send(ping)
        except (RuntimeError, WebSocketDisconnect):
            pass

    async def _deliver(self, text: str, username: str | None) -> None:
        with self._lock:
            targets = [
                connection
                for connection in self._connections.values()
                if username is None or connection.principal.username.lower() == username.lower()
            ]
        results = await asyncio.gather(
            *(connection.send(text) for connection in targets), return_exceptions=True
        )
        for result in results:
            if isinstance(result, Exception):
                logger.debug("Dropped a realtime message for a closing connection: %s", result)

    def publish(self, target: str, *arguments, username: str | None = None) -> None:
        """Send a hub event to every connection, or only to one user's connections.

        Safe to call from sync route handlers (worker threads) and from the event loop.
        It returns immediately and never raises, so a failed push cannot fail a write.
        """
        loop = self._loop
        if loop is None or loop.is_closed() or not self._connections:
            return
        text = encode_message(
            {"type": MESSAGE_INVOCATION, "target": target, "arguments": list(arguments)}
        )
        try:
            running = asyncio.get_running_loop()
        except RuntimeError:
            running = None
        try:
            if running is loop:
                loop.create_task(self._deliver(text, username))
            else:
                asyncio.run_coroutine_threadsafe(self._deliver(text, username), loop)
        except RuntimeError:
            logger.debug("Realtime event %s was not sent; the event loop is closing.", target)


async def _close_quietly(websocket: WebSocket, code: int) -> None:
    try:
        await websocket.close(code=code)
    except RuntimeError:
        pass


hub = LibraryHub()


def _websocket_principal(websocket: WebSocket) -> auth.Principal | None:
    authorization = websocket.headers.get("authorization", "")
    bearer = authorization[7:] if authorization.lower().startswith("bearer ") else None
    token = bearer or websocket.query_params.get("access_token")
    if token is None:
        token = websocket.cookies.get(auth.AUTH_COOKIE_NAME)
        # Browsers attach cookies to cross-site WebSocket handshakes too.
        if token is not None and not auth._is_trusted_origin(websocket):
            return None
    if token is None:
        return None
    try:
        return auth._decode_access_token(token)
    except HTTPException:
        return None


@router.post(f"{HUB_PATH}/negotiate")
def negotiate(principal: auth.Principal = Depends(auth.get_current_principal)) -> dict:
    return hub.negotiate(principal)


@router.websocket(HUB_PATH)
async def library_hub(websocket: WebSocket) -> None:
    principal = _websocket_principal(websocket)
    if principal is None:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await hub.serve(websocket, principal)
