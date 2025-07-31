import collections.abc as _cabc
import contextlib as _ctx
import logging as _log
import typing as _tp

import aiohttp as _ahttp
import aiohttp.web as _ahttpw
import resultes_jsonrpc.websockets.types as _rjwt

_LOGGER = _log.getLogger(__name__)


type MessageReceiverFactory = _tp.Callable[
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
    async def serve(self) -> _cabc.AsyncIterator[None]:
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

        async for message in websocket:
            if message.type == _ahttp.WSMsgType.TEXT:
                data = message.data
                _LOGGER.info("Received message: %s.", data)
                await message_receiver.on_message_received(data)
            elif message.type == _ahttp.WSMsgType.ERROR:
                _LOGGER.error(
                    "WebSocket connectionw as closed with exception %s.",
                    websocket.exception(),
                )
            elif message.type == _ahttp.WSMsgType.CLOSED:
                _LOGGER.info("Websocket connection closed.")
                break

        return websocket
