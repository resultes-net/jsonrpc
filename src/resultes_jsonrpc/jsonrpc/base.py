import abc as _abc
import asyncio as _asyncio
import logging as _log

import aiohttp as _ahttp
import resultes_jsonrpc.jsonrpc.types as _tps

_LOGGER = _log.getLogger(__file__)


class JsonRpcBase(_abc.ABC):
    def __init__(self, websocket: _tps.WebSocket) -> None:
        self._websocket = websocket
        self._started = False

    async def start(self) -> None:
        if self._started:
            raise RuntimeError("Already started.")
        self._started = True

        _LOGGER.info("Starting.")

        while True:
            message = await self._websocket.receive()

            if message.type == _ahttp.WSMsgType.TEXT:
                data = message.data
                _LOGGER.info("Received message: %s.", data)
                await self._handle_message(data)
            elif message.type == _ahttp.WSMsgType.ERROR:
                _LOGGER.error(
                    "WebSocket connectionw as closed with exception %s.",
                    self._websocket.exception(),
                )
            elif message.type == _ahttp.WSMsgType.CLOSED:
                _LOGGER.info("Websocket connection closed.")
                break

    async def stop(self) -> None:
        if not self._started:
            raise RuntimeError("Not started.")

        seconds = 5.0
        async with _asyncio.timeout(seconds):
            await self._websocket.close()

    @_abc.abstractmethod
    async def _handle_message(self, data: str) -> None:
        raise NotImplementedError()
