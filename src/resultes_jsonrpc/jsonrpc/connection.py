import abc as _abc
import asyncio as _asyncio
import collections.abc as _cabc
import contextlib as _ctx
import dataclasses as _dc
import functools as _ft
import json as _json
import logging as _log
import traceback as _tb
import typing as _tp

import jsonrpcclient as _jrpcc
import jsonrpcserver as _jrpcs
import jsonrpcserver.codes as _jrpcsc
import pydantic as _pyd
import resultes_jsonrpc.jsonrpc.types as _rjjt
import resultes_jsonrpc.jsonrpc.types as _tps
import resultes_jsonrpc.websockets.types as _rjwt

_LOGGER = _log.getLogger(__file__)


type AsyncJsonRpcMethod[**P] = _cabc.Callable[P, _cabc.Awaitable[_jrpcs.Result]]


def cancellable_async_jrpcs_method[**P](
    method: AsyncJsonRpcMethod[P],
) -> AsyncJsonRpcMethod[P]:
    @_jrpcs.method()
    @_ft.wraps(method)
    async def nested(*args: P.args, **kwargs: P.kwargs) -> _jrpcs.Result:
        try:
            return await method(*args, **kwargs)
        except _asyncio.CancelledError:
            _LOGGER.warning("The request was cancelled on the server.")
            return _jrpcs.Error(
                _jrpcsc.ERROR_SERVER_ERROR, "The request was cancelled on the server."
            )
        except Exception as exception:
            _LOGGER.error("Exception occurred: %s", exc_info=exception)
            traceback = "\n".join(_tb.format_exception(exception))
            return _jrpcs.Error(_jrpcsc.ERROR_SERVER_ERROR, str(exception), traceback)

    return nested


def cancellable_async_validated_jrpcs_method[T: _pyd.BaseModel, C](
    clazz: type[T],
) -> _cabc.Callable[
    [AsyncJsonRpcMethod[[C, T]]], AsyncJsonRpcMethod[[C, _rjjt.JsonObject]]
]:
    """
    Wrapped methods name must be `value`.
    """

    def create_validating_method(
        validated_method: AsyncJsonRpcMethod[[C, T]],
    ) -> AsyncJsonRpcMethod[[C, _rjjt.JsonObject]]:
        @_jrpcs.method()
        @_ft.wraps(validated_method)
        async def validating_method(
            context: C, value: _rjjt.JsonObject
        ) -> _jrpcs.Result:
            try:
                instance = clazz(**value)
            except _pyd.ValidationError as validation_error:
                errors = validation_error.errors()
                return _jrpcs.InvalidParams(errors)

            try:
                return await validated_method(context, instance)
            except _asyncio.CancelledError:
                _LOGGER.warning("The request was cancelled on the server.")
                return _jrpcs.Error(
                    _jrpcsc.ERROR_SERVER_ERROR,
                    "The request was cancelled on the server.",
                )
            except Exception as exception:
                _LOGGER.error("Exception occurred: %s", exc_info=exception)
                traceback = "\n".join(_tb.format_exception(exception))
                return _jrpcs.Error(
                    _jrpcsc.ERROR_SERVER_ERROR, str(exception), traceback
                )

        return validating_method

    return create_validating_method


class DispatcherBase(_abc.ABC):
    @_abc.abstractmethod
    async def dispatch(
        self,
        data: _rjjt.JsonStructured,
        context: _tp.Any,
        websocket: _rjwt.WriteWebsocket,
    ) -> None:
        raise NotImplementedError()


class SyncDispatcher(DispatcherBase):
    @_tp.override
    async def dispatch(
        self,
        data: _rjjt.JsonStructured,
        context: _tp.Any,
        websocket: _rjwt.WriteWebsocket,
    ) -> None:
        json = _json.dumps(data)
        if result := _jrpcs.dispatch(json, context=context):
            await websocket.send_str(result)


class AsyncTaskSpawningDispatcher(DispatcherBase):
    def __init__(self, task_group: _asyncio.TaskGroup) -> None:
        self._task_group = task_group

    @_tp.override
    async def dispatch(
        self,
        data: _rjjt.JsonStructured,
        context: _tp.Any,
        websocket: _rjwt.WriteWebsocket,
    ) -> None:
        coroutine = self._dispatch_impl(data, context, websocket)
        self._task_group.create_task(coroutine)

    async def _dispatch_impl(
        self, data: _rjjt.JsonStructured, context: _tp.Any, websocket: _rjwt.WriteWebsocket
    ) -> None:
        json = _json.dumps(data)
        if result := await _jrpcs.async_dispatch(json, context=context):
            await websocket.send_str(result)


@_dc.dataclass
class Argument:
    name: str
    value: _pyd.BaseModel


class Connection(_rjwt.MessageReceiver):
    def __init__(
        self,
        dispatcher: DispatcherBase,
        context: _tp.Any,
        websocket: _rjwt.WriteWebsocket,
    ) -> None:
        self._context = context
        self._dispatcher = dispatcher
        self._websocket = websocket

        self._new_message_received_event = _asyncio.Event()
        self._parsed_response_futures_by_request_id = dict[
            int, _asyncio.Future[_jrpcc.responses.Response]
        ]()

    @_tp.override
    async def on_message_received(self, json: str) -> None:
        data = _json.loads(json)
        is_response = "error" in json or "result" in data
        if is_response:
            await self._on_response_received(data)
        else:
            await self._on_request_received(data)

    async def _on_request_received(self, data: _rjjt.JsonStructured) -> None:
        await self._dispatcher.dispatch(data, self._context, self._websocket)

    async def _on_response_received(self, data: _rjjt.JsonStructured) -> None:
        parsed_response = _jrpcc.parse(data)

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
                _LOGGER.error("Got error %s: %s", error.message, error.data)
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

    async def send_notification_data(
        self, method: str, params: _tps.JsonStructured | None = None
    ) -> None:
        converted_params = self._convert_params(params)

        notification = _jrpcc.notification(method=method, params=converted_params)

        data = _json.dumps(notification)

        _LOGGER.debug("Sending notification %s.", data)
        await self._websocket.send_str(data)

    async def send_notification_base_model(
        self, method: str, argument: Argument | None = None
    ) -> None:
        if argument:
            value_data = argument.value.model_dump()
            data = {argument.name: value_data}
        else:
            data = None

        await self.send_notification_data(method, data)

    def _convert_params(
        self, params: _tps.JsonStructured | None
    ) -> tuple[_tps.Json, ...] | _cabc.Mapping[str, _tps.Json] | None:
        if not params:
            return None

        try:
            return dict(params)
        except ValueError:
            return tuple(params)
