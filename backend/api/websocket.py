import asyncio
import json
import websockets
from typing import Set

# Global set of connected WebSocket clients
connected_clients: Set[websockets.WebSocketServerProtocol] = set()


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


class WebSocketHandler:
    @staticmethod
    async def handler(websocket: websockets.WebSocketServerProtocol, path: str):
        connected_clients.add(websocket)
        try:
            async for message in websocket:
                # Handle incoming messages from frontend (if needed)
                pass
        except Exception:
            pass
        finally:
            connected_clients.discard(websocket)
