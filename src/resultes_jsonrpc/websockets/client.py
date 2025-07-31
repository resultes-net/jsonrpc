import asyncio as _asyncio
import logging as _log

import aiohttp as _ahttp
import resultes_jsonrpc.websockets.common as _rjwcom
import resultes_jsonrpc.websockets.types as _rjwt

_LOGGER = _log.getLogger(__name__)


class WebsocketClient:
    def __init__(
        self,
        websocket: _ahttp.ClientWebSocketResponse,
        message_receiver: _rjwt.MessageReceiver,
    ) -> None:
        self._websocket = websocket
        self._message_receiver = message_receiver
        self._reader_task: _asyncio.Task[None] | None = None

    def start(self) -> None:
        if self._reader_task:
            raise RuntimeError("Already started.")
        
        _LOGGER.info("Starting.")

        coroutine = _rjwcom.start_receiving_messages(
            self._websocket, self._message_receiver
        )
        self._reader_task = _asyncio.create_task(coroutine)

    async def join(self) -> None:
        if not self._reader_task:
            raise RuntimeError("Not started.")

        await self._reader_task
