import logging as _log
import typing as _tp

import jsonrpcserver as _jrpcs
import resultes_jsonrpc.jsonrpc.base as _rjjb
import resultes_jsonrpc.jsonrpc.types as _tps

_LOGGER = _log.getLogger(__file__)


class JsonRpcServer(_rjjb.JsonRpcBase):
    def __init__(
        self,
        websocket: _tps.WebSocket,
        wakeup_period_seconds: float = 5.0,
        message_dispatch_context: _tp.Any = None,
    ) -> None:
        super().__init__(websocket, wakeup_period_seconds)
        self._message_dispatch_context = message_dispatch_context

    async def _handle_message(self, data: str) -> None:
        if result := await _jrpcs.async_dispatch(
            data, context=self._message_dispatch_context
        ):
            await self._websocket.send_str(result)
