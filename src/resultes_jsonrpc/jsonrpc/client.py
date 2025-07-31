import asyncio as _asyncio
import collections.abc as _cabc
import contextlib as _ctx
import json as _json
import logging as _log
import typing as _tp

import jsonrpcclient as _jrpcc
import resultes_jsonrpc.jsonrpc.types as _tps
import resultes_jsonrpc.websockets.types as _rjwt

_LOGGER = _log.getLogger(__file__)


class JsonRpcClient(_rjwt.MessageReceiver):
    def __init__(self, websocket: _rjwt.WriteWebsocket) -> None:
        self._websocket = websocket

        self._new_message_received_event = _asyncio.Event()
        self._parsed_response_futures_by_request_id = dict[
            int, _asyncio.Future[_jrpcc.responses.Response]
        ]()

    async def on_message_received(self, data: str) -> None:
        parsed_response = _jrpcc.parse_json(data)

        parsed_responses = (
            [parsed_response]
            if isinstance(parsed_response, (_jrpcc.Ok, _jrpcc.Error))
            else list(parsed_response)
        )

        for parsed_response in parsed_responses:
            future = self._parsed_response_futures_by_request_id[parsed_response.id]
            future.set_result(parsed_response)

    async def send_request_and_check_and_get_response(
        self, method: str, params: _tps.JsonStructured | None = None
    ) -> _tps.Json:
        converted_params = self._convert_params(params)

        request: _tps.Request = _jrpcc.request(method=method, params=converted_params)

        data = _json.dumps(request)

        _LOGGER.debug("Sending request %s.", data)
        await self._websocket.send_str(data)

        response = await self._get_response(request["id"])
        _LOGGER.debug("Got response %s.", response)

        match response:
            case _jrpcc.Ok(result):
                return result
            case _jrpcc.Error() as error:
                raise RuntimeError(error)
            case _:
                _tp.assert_never(_)

    async def _get_response(self, request_id: int) -> _jrpcc.responses.Response:
        async with self._registered_future(request_id) as future:
            response = await future
            return response

    @_ctx.asynccontextmanager
    async def _registered_future(
        self, request_id: int
    ) -> _cabc.AsyncIterator[_asyncio.Future[_jrpcc.responses.Response]]:
        future = _asyncio.Future[_jrpcc.responses.Response]()
        self._parsed_response_futures_by_request_id[request_id] = future

        yield future

        del self._parsed_response_futures_by_request_id[request_id]

    async def send_notification(
        self, method: str, params: _tps.JsonStructured | None = None
    ) -> None:
        converted_params = self._convert_params(params)

        notification = _jrpcc.notification(method=method, params=converted_params)

        data = _json.dumps(notification)

        _LOGGER.debug("Sending notification %s.", data)
        await self._websocket.send_str(data)

    def _convert_params(
        self, params: _tps.JsonStructured | None
    ) -> tuple[_tps.Json, ...] | _cabc.Mapping[str, _tps.Json] | None:
        if not params:
            return None

        try:
            return dict(params)
        except ValueError:
            return tuple(params)
