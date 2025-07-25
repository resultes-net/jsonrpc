import collections.abc as _cabc
import contextlib as _ctx
import typing as _tp

import aiohttp.web as _ahttpw


class Client:
    def __init__(self, handle_connection: HandleConnection, port: int) -> None:
        self._handle_connection = handle_connection
        self._port = port

    @_ctx.asynccontextmanager
    async def serve(self) -> _cabc.AsyncIterator[None]:
        app = _ahttpw.Application()
        app.add_routes([_ahttpw.get("/", self._get)])
        runner = _ahttpw.AppRunner(app)
        await runner.setup()
        site = _ahttpw.TCPSite(runner, port=self._port)
        await site.start()

        yield

        await site.stop()
        await runner.shutdown()

    async def _get(self, request: _ahttpw.Request) -> _ahttpw.WebSocketResponse:
        websocket = _ahttpw.WebSocketResponse()
        await websocket.prepare(request)
        await self._handle_connection(websocket)
        return websocket
