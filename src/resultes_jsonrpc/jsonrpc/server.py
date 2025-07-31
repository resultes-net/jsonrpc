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


class JsonRpcMethod[C: ContextBase, **P](_tp.Protocol):
    def __call__(
        self, context: C, *args: P.args, **kwargs: P.kwargs
    ) -> _cabc.Awaitable[_jrpcs.Result]: ...


def cancellable_jrpcs_method[C: ContextBase, **P](
    method: JsonRpcMethod[C, P],
) -> JsonRpcMethod[C, P]:
    @_jrpcs.method()
    @_ft.wraps(method)
    async def nested(context: C, *args: P.args, **kwargs: P.kwargs) -> _jrpcs.Result:
        try:
            current_task = _asyncio.current_task()
            assert current_task

            context.register_task(current_task)

            return await method(context, *args, **kwargs)
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


class Dispatcher(DispatcherBase):
    async def dispatch(
        self, data: str, context: _tp.Any, websocket: _tps.WriteWebsocket
    ) -> None:
        if result := await _jrpcs.async_dispatch(data, context=context):
            await websocket.send_str(result)


class _TerminateTaskGroupException(Exception):
    pass


class TaskSpawningDispatcher(DispatcherBase):
    def __init__(self, task_group: _asyncio.TaskGroup) -> None:
        self._dispatcher = Dispatcher()
        self._task_group = task_group

    @staticmethod
    async def create() -> "TaskSpawningDispatcher":
        task_group = await _asyncio.TaskGroup().__aenter__()
        return TaskSpawningDispatcher(task_group)

    async def dispatch(
        self, data: str, context: _tp.Any, websocket: _tps.WriteWebsocket
    ) -> None:
        if not self._task_group:
            raise RuntimeError("Not entered.")

        coroutine = self._dispatcher.dispatch(data, context, websocket)

        task = self._task_group.create_task(coroutine)

        _LOGGER.info("New task %s for dispatching request created.", task.get_name())

    async def cancel_and_join_tasks(self) -> None:
        if not self._task_group:
            raise RuntimeError("Not entered.")

        _LOGGER.info("Terminating task group.")

        async def raise_exception() -> _tp.NoReturn:
            raise _TerminateTaskGroupException()

        self._task_group.create_task(raise_exception())

        _LOGGER.info("Joining tasks...")

        try:
            await self._task_group.__aexit__(None, None, None)
        except* _TerminateTaskGroupException:
            pass

        _LOGGER.info("...Done")


class JsonRpcServer(_tps.MessageReceiver):
    def __init__(
        self,
        websocket: _tps.WriteWebsocket,
        dispatcher: DispatcherBase = Dispatcher(),
        context: ContextBase = ContextBase(),
    ) -> None:
        self._websocket = websocket
        self._context = context
        self._dispatcher = dispatcher

    async def on_message_received(self, data: str) -> None:
        await self._dispatcher.dispatch(data, self._context, self._websocket)

    async def cancel_and_join_requests(self) -> None:
        tasks = self._context.tasks()

        _LOGGER.info("Cancelling %i running task(s).", len(tasks))

        for task in tasks:
            task.cancel()

        _LOGGER.info("Joining cancelled tasks...")

        for task in tasks:
            try:
                await task
            except _asyncio.CancelledError:
                pass

        _LOGGER.info("...DONE.")
