import abc as _abc
import asyncio as _asyncio
import contextlib as _ctx
import logging as _log
import typing as _tp

import jsonrpcserver as _jrpcs
import resultes_jsonrpc.jsonrpc.base as _rjjb
import resultes_jsonrpc.jsonrpc.types as _tps

_LOGGER = _log.getLogger(__file__)


class DispatcherBase(_abc.ABC):
    @_abc.abstractmethod
    async def dispatch(
        self, data: str, context: _tp.Any, websocket: _tps.WebSocket
    ) -> None:
        raise NotImplementedError()


class Dispatcher(DispatcherBase):
    async def dispatch(
        self, data: str, context: _tp.Any, websocket: _tps.WebSocket
    ) -> None:
        if result := await _jrpcs.async_dispatch(data, context):
            await websocket.send_str(result)


class _TerminateTaskGroupException(Exception):
    pass


class TaskSpawningDispatcher(
    DispatcherBase, _ctx.AbstractAsyncContextManager["TaskSpawningDispatcher"]
):
    def __init__(self) -> None:
        self._dispatcher = Dispatcher()
        self._task_group: _asyncio.TaskGroup | None = None

    async def __aenter__(self) -> _tp.Self:
        if self._task_group:
            raise RuntimeError("Already started.")

        self._task_group = _asyncio.TaskGroup()

        await self._task_group.__aenter__()

        return self

    async def __aexit__(self, exc_type, exc_value, traceback) -> bool:
        if not self._task_group:
            raise RuntimeError("Not started.")

        try:
            await self._task_group.__aexit__(exc_type, exc_value, traceback)
        except* _TerminateTaskGroupException:
            pass

        return False

    async def dispatch(
        self, data: str, context: _tp.Any, websocket: _tps.WebSocket
    ) -> None:
        if not self._task_group:
            raise RuntimeError("Not entered.")

        coroutine = self._dispatcher.dispatch(data, context, websocket)

        task = self._task_group.create_task(coroutine)

        _LOGGER.info("New task %s for dispatching request created.", task.get_name())

    async def cancel_tasks(self) -> None:
        _LOGGER.info("Terminating task group.")

        if not self._task_group:
            raise RuntimeError("Not entered.")

        async def raise_exception() -> _tp.NoReturn:
            raise _TerminateTaskGroupException()

        self._task_group.create_task(raise_exception())


class JsonRpcServer(_rjjb.JsonRpcBase):
    def __init__(
        self,
        websocket: _tps.WebSocket,
        dispatcher: DispatcherBase = Dispatcher(),
        message_dispatch_context: _tp.Any = None,
    ) -> None:
        super().__init__(websocket)
        self._message_dispatch_context = message_dispatch_context
        self._dispatcher = dispatcher

    async def _handle_message(self, data: str) -> None:
        await self._dispatcher.dispatch(
            data, self._message_dispatch_context, self._websocket
        )
