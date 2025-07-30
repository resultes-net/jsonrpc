import asyncio as _asyncio
import collections.abc as _cabc
import contextlib as _ctx
import dataclasses as _dc
import logging as _log

import aiohttp.web as _ahttpw

_LOGGER = _log.getLogger(__name__)


@_dc.dataclass
class WebsocketWithPath:
    websocket: _ahttpw.WebSocketResponse
    path: str


class Server:
    def __init__(self) -> None:
        self._queue = _asyncio.Queue[WebsocketWithPath]()

    @_ctx.asynccontextmanager
    @staticmethod
    async def start(
        port: int, paths: _cabc.Sequence[str]
    ) -> _cabc.AsyncIterator["Server"]:
        server = Server()

        app = _ahttpw.Application()

        routes = [_ahttpw.get(p, server._create_websocket) for p in paths]

        app.add_routes(routes)

        runner = _ahttpw.AppRunner(app)
        await runner.setup()
        site = _ahttpw.TCPSite(runner, port=port)

        _log.info("About to start serving requets on port %d.", port)
        await site.start()

        yield server

        await site.stop()
        await runner.shutdown()

    async def _create_websocket(
        self, request: _ahttpw.Request
    ) -> _ahttpw.WebSocketResponse:
        websocket = _ahttpw.WebSocketResponse()
        await websocket.prepare(request)
        item = WebsocketWithPath(websocket, request.path)
        await self._queue.put(item)
        return websocket

    async def websockets(self) -> _cabc.AsyncIterable[WebsocketWithPath]:
        try:
            while True:
                yield await self._queue.get()
        except _asyncio.QueueShutDown:
            pass

    def stop(self) -> None:
        self._queue.shutdown(immediate=True)
