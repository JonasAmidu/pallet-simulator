import asyncio
import json
import websockets
from collections.abc import Awaitable, Callable
from typing import Set

# Global set of connected WebSocket clients
connected_clients: Set[websockets.WebSocketServerProtocol] = set()
message_handler: Callable[[websockets.WebSocketServerProtocol, dict], Awaitable[None]] | None = None
state_provider: Callable[[], dict | None] | None = None


def configure_websocket(
    *,
    on_message: Callable[[websockets.WebSocketServerProtocol, dict], Awaitable[None]] | None = None,
    get_state: Callable[[], dict | None] | None = None,
):
    global message_handler, state_provider
    message_handler = on_message
    state_provider = get_state


async def broadcast_state(state: dict):
    """Send current state to all connected WebSocket clients."""
    if not connected_clients:
        return
    message = json.dumps(state)
    dead = set()
    for client in connected_clients:
        try:
            await client.send(message)
        except Exception:
            dead.add(client)
    connected_clients.difference_update(dead)


async def send_message(client: websockets.WebSocketServerProtocol, payload: dict):
    await client.send(json.dumps(payload))


class WebSocketHandler:
    @staticmethod
    async def handler(websocket: websockets.WebSocketServerProtocol, path: str):
        connected_clients.add(websocket)
        try:
            if state_provider is not None:
                state = state_provider()
                if state is not None:
                    await send_message(websocket, state)
            async for message in websocket:
                if message_handler is None:
                    continue
                try:
                    payload = json.loads(message)
                except json.JSONDecodeError:
                    await send_message(
                        websocket,
                        {
                            "type": "command_error",
                            "code": "invalid_message",
                            "message": "Command payload must be valid JSON.",
                        },
                    )
                    continue
                await message_handler(websocket, payload)
        except Exception:
            pass
        finally:
            connected_clients.discard(websocket)
