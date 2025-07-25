import collections.abc as _cabc
import typing as _tp
import aiohttp as _aiohttp

type JsonScalar = bool | int | float | str
type JsonStructured = _cabc.Sequence["Json"] | _cabc.Mapping[str, "Json"]
type Json = JsonScalar | JsonStructured


class RequestBase(_tp.TypedDict):
    method: str
    params: _tp.NotRequired[JsonStructured]


class Request(RequestBase):
    id: int


class Notification(RequestBase):
    pass


class Response(_tp.TypedDict):
    id: int
    result: Json


class WebSocket(_tp.Protocol):
    async def receive_json(self, *, timeout: float) -> _aiohttp.WSMessage: ...
    async def send_str(self, data: str) -> None: ...
    def exception(self) -> BaseException | None: ...
