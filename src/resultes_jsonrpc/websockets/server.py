import asyncio as _asyncio
import collections.abc as _cabc
import contextlib as _ctx
import dataclasses as _dc

import aiohttp.web as _ahttpw


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

        for path in paths:
            app.add_routes([_ahttpw.get(path, server._create_websocket)])

        runner = _ahttpw.AppRunner(app)
        await runner.setup()
        site = _ahttpw.TCPSite(runner, port=port)
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
