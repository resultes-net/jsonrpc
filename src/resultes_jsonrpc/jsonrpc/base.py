import abc as _abc
import asyncio as _asyncio
import logging as _log

import aiohttp as _ahttp
import resultes_jsonrpc.jsonrpc.types as _tps

_LOGGER = _log.getLogger(__file__)


class JsonRpcBase(_abc.ABC):
    def __init__(
        self, websocket: _tps.WebSocket, wakeup_period_seconds: float = 5.0
    ) -> None:
        self._websocket = websocket
        self._wakeup_period_seconds = wakeup_period_seconds
        self._started = False
        self._stop_event = _asyncio.Event()

    async def start(self) -> None:
        if self._started:
            raise RuntimeError("Already started.")
        self._started = True

        _LOGGER.info("Starting.")

        while not self._stop_event.is_set():
            message = await self._websocket.receive(
                timeout=self._wakeup_period_seconds
            )

            if message.type == _ahttp.WSMsgType.TEXT:
                await self._handle_message(message.data)
            elif message.type == _ahttp.WSMsgType.ERROR:
                _LOGGER.error(
                    "WebSocket connectionw as closed with exception %s.",
                    self._websocket.exception(),
                )

        _LOGGER.info("Websocket connection closed.")

    def stop(self) -> None:
        if not self._started:
            raise RuntimeError("Not started.")

        self._stop_event.set()

    @_abc.abstractmethod
    async def _handle_message(self, data: str) -> None:
        raise NotImplementedError()
