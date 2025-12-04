import collections.abc as _cabc
import typing as _tp

type JsonScalar = bool | int | float | str
type JsonObject = _cabc.Mapping[str, "Json"]
type JsonStructured = _cabc.Sequence["Json"] | JsonObject
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
