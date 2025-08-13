import abc as _abc
import asyncio as _asyncio
import collections.abc as _cabc
import functools as _ft
import logging as _log
import typing as _tp

import jsonrpcserver as _jrpcs
import jsonrpcserver.codes as _jrpcsc
import resultes_jsonrpc.websockets.types as _tps

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


type AsyncJsonRpcMethod[**P] = _tp.Callable[P, _cabc.Awaitable[_jrpcs.Result]]


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

    return nested


class DispatcherBase(_abc.ABC):
    @_abc.abstractmethod
    async def dispatch(
        self, data: str, context: _tp.Any, websocket: _tps.WriteWebsocket
    ) -> None:
        raise NotImplementedError()


class SyncDispatcher(DispatcherBase):
    async def dispatch(
        self, data: str, context: _tp.Any, websocket: _tps.WriteWebsocket
    ) -> None:
        if result := _jrpcs.dispatch(data, context=context):
            await websocket.send_str(result)


class AsyncTaskSpawningDispatcher(DispatcherBase):
    def __init__(self, task_group: _asyncio.TaskGroup) -> None:
        self._task_group = task_group

    async def dispatch(
        self, data: str, context: _tp.Any, websocket: _tps.WriteWebsocket
    ) -> None:
        coroutine = self._dispatch_impl(data, context, websocket)
        self._task_group.create_task(coroutine)

    async def _dispatch_impl(
        self, data: str, context: _tp.Any, websocket: _tps.WriteWebsocket
    ) -> None:
        if result := await _jrpcs.async_dispatch(data, context=context):
            await websocket.send_str(result)


class JsonRpcServer(_tps.MessageReceiver):
    def __init__(
        self,
        websocket: _tps.WriteWebsocket,
        dispatcher: DispatcherBase,
        context: _tp.Any,
    ) -> None:
        self._websocket = websocket
        self._context = context
        self._dispatcher = dispatcher

    async def on_message_received(self, data: str) -> None:
        await self._dispatcher.dispatch(data, self._context, self._websocket)
