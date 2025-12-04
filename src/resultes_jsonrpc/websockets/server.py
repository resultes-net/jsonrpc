import collections.abc as _cabc
import contextlib as _ctx
import logging as _log

import aiohttp.web as _ahttpw
import resultes_jsonrpc.websockets.common as _rjwcom
import resultes_jsonrpc.websockets.types as _rjwt

_LOGGER = _log.getLogger(__name__)


type MessageReceiverFactory = _cabc.Callable[
    [_rjwt.WriteWebsocket], _rjwt.MessageReceiver
]


class Server:
    def __init__(
        self,
        port: int,
        message_receiver_factories_by_path: _cabc.Mapping[str, MessageReceiverFactory],
    ) -> None:
        self._port = port
        self._message_receiver_factories = message_receiver_factories_by_path

    @_ctx.asynccontextmanager
    async def run(self) -> _cabc.AsyncIterator[None]:
        app = _ahttpw.Application()

        routes = [
            _ahttpw.get(p, self._on_websocket_connection)
            for p in self._message_receiver_factories.keys()
        ]

        app.add_routes(routes)

        runner = _ahttpw.AppRunner(app)
        await runner.setup()
        site = _ahttpw.TCPSite(runner, port=self._port)

        _log.info("About to start serving requets on port %d.", self._port)
        await site.start()

        yield

        await site.stop()
        await runner.shutdown()

    async def _on_websocket_connection(
        self, request: _ahttpw.Request
    ) -> _ahttpw.WebSocketResponse:
        _log.info("Creating websocket.")
        websocket = _ahttpw.WebSocketResponse()
        await websocket.prepare(request)

        factory = self._message_receiver_factories[request.path]

        message_receiver = factory(websocket)

        await _rjwcom.start_receiving_messages(websocket, message_receiver)

        return websocket
