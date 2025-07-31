import abc as _abc
import typing as _tp


class WriteWebsocket(_tp.Protocol):
    async def send_str(self, data: str) -> None: ...


class MessageReceiver(_abc.ABC):
    @_abc.abstractmethod
    async def on_message_received(self, data: str) -> None:
        raise NotImplementedError()