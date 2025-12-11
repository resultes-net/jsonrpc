import abc as _abc
import asyncio as _asyncio
import collections.abc as _cabc
import functools as _ft
import logging as _log
import traceback as _tb
import typing as _tp

import pydantic as _pyd
import jsonrpcserver as _jrpcs
import jsonrpcserver.codes as _jrpcsc
import resultes_jsonrpc.websockets.types as _rjwt
import resultes_jsonrpc.jsonrpc.types as _rjjt

_LOGGER = _log.getLogger(__file__)


class ContextBase:
    def __init__(self) -> None:
        self._tasks = set[_asyncio.Task[_tp.Any]]()

    def tasks(self) -> _cabc.Sequence[_asyncio.Task[_tp.Any]]:
        return list(self._tasks)

    def register_task(self, task: _asyncio.Task[_tp.Any]) -> None:
        if task in self._tasks:
            raise ValueError("Already registered.")

        self._tasks.add(task)

        task.add_done_callback(self._unregister_task)

    def _unregister_task(self, task: _asyncio.Task[_tp.Any]) -> None:
        if task not in self._tasks:
            raise ValueError("Not registered.")

        self._tasks.remove(task)


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
    def create_validating_method(
        validated_method: AsyncJsonRpcMethod[[C, T]],
    ) -> AsyncJsonRpcMethod[[C, _rjjt.JsonObject]]:
        @_jrpcs.method()
        @_ft.wraps(validated_method)
        async def validating_method(
            data: _rjjt.JsonObject, context: C
        ) -> _jrpcs.Result:
            try:
                instance = clazz(**data)
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
        self, data: str, context: _tp.Any, websocket: _rjwt.WriteWebsocket
    ) -> None:
        raise NotImplementedError()


class SyncDispatcher(DispatcherBase):
    async def dispatch(
        self, data: str, context: _tp.Any, websocket: _rjwt.WriteWebsocket
    ) -> None:
        if result := _jrpcs.dispatch(data, context=context):
            await websocket.send_str(result)


class AsyncTaskSpawningDispatcher(DispatcherBase):
    def __init__(self, task_group: _asyncio.TaskGroup) -> None:
        self._task_group = task_group

    async def dispatch(
        self, data: str, context: _tp.Any, websocket: _rjwt.WriteWebsocket
    ) -> None:
        coroutine = self._dispatch_impl(data, context, websocket)
        self._task_group.create_task(coroutine)

    async def _dispatch_impl(
        self, data: str, context: _tp.Any, websocket: _rjwt.WriteWebsocket
    ) -> None:
        if result := await _jrpcs.async_dispatch(data, context=context):
            await websocket.send_str(result)


class JsonRpcServer(_rjwt.MessageReceiver):
    def __init__(
        self,
        websocket: _rjwt.WriteWebsocket,
        dispatcher: DispatcherBase,
        context: _tp.Any,
    ) -> None:
        self._websocket = websocket
        self._context = context
        self._dispatcher = dispatcher

    async def on_message_received(self, data: str) -> None:
        await self._dispatcher.dispatch(data, self._context, self._websocket)
