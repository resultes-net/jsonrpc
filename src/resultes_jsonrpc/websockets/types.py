import abc as _abc
import collections.abc as _cabc
import typing as _tp

import aiohttp as _ahttp


class WriteWebsocket(_tp.Protocol):
    async def send_str(self, data: str) -> None: ...


class ReadWebSocket(_tp.Protocol):
    def __aiter__(self) -> _cabc.AsyncIterator[_ahttp.WSMessage]: ...
    def exception(self) -> BaseException | None: ...


class MessageReceiver(_abc.ABC):
    @_abc.abstractmethod
    async def on_message_received(self, json: str) -> None:
        raise NotImplementedError()
