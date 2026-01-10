from collections.abc import Iterable as _Iterable
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

DESCRIPTOR: _descriptor.FileDescriptor

class GameState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    IDLE: _ClassVar[GameState]
    STARTING: _ClassVar[GameState]
    RUNNING: _ClassVar[GameState]
    ENDING: _ClassVar[GameState]
    ENDED: _ClassVar[GameState]

IDLE: GameState
STARTING: GameState
RUNNING: GameState
ENDING: GameState
ENDED: GameState

class Player(_message.Message):
    __slots__ = ("serial", "team", "alive", "score")
    SERIAL_FIELD_NUMBER: _ClassVar[int]
    TEAM_FIELD_NUMBER: _ClassVar[int]
    ALIVE_FIELD_NUMBER: _ClassVar[int]
    SCORE_FIELD_NUMBER: _ClassVar[int]
    serial: str
    team: int
    alive: bool
    score: int
    def __init__(
        self,
        serial: str | None = ...,
        team: int | None = ...,
        alive: bool = ...,
        score: int | None = ...,
    ) -> None: ...

class StartGameRequest(_message.Message):
    __slots__ = ("game_name", "players", "settings")
    class SettingsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: str | None = ..., value: str | None = ...) -> None: ...

    GAME_NAME_FIELD_NUMBER: _ClassVar[int]
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    SETTINGS_FIELD_NUMBER: _ClassVar[int]
    game_name: str
    players: _containers.RepeatedCompositeFieldContainer[Player]
    settings: _containers.ScalarMap[str, str]
    def __init__(
        self,
        game_name: str | None = ...,
        players: _Iterable[Player | _Mapping] | None = ...,
        settings: _Mapping[str, str] | None = ...,
    ) -> None: ...

class StartGameResponse(_message.Message):
    __slots__ = ("success", "error", "game_id")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    game_id: str
    def __init__(
        self, success: bool = ..., error: str | None = ..., game_id: str | None = ...
    ) -> None: ...

class GetGameStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetGameStatusResponse(_message.Message):
    __slots__ = ("state", "game_name", "players", "elapsed_seconds", "success", "error")
    STATE_FIELD_NUMBER: _ClassVar[int]
    GAME_NAME_FIELD_NUMBER: _ClassVar[int]
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    ELAPSED_SECONDS_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    state: GameState
    game_name: str
    players: _containers.RepeatedCompositeFieldContainer[Player]
    elapsed_seconds: int
    success: bool
    error: str
    def __init__(
        self,
        state: GameState | str | None = ...,
        game_name: str | None = ...,
        players: _Iterable[Player | _Mapping] | None = ...,
        elapsed_seconds: int | None = ...,
        success: bool = ...,
        error: str | None = ...,
    ) -> None: ...

class ForceEndGameRequest(_message.Message):
    __slots__ = ("reason",)
    REASON_FIELD_NUMBER: _ClassVar[int]
    reason: str
    def __init__(self, reason: str | None = ...) -> None: ...

class ForceEndGameResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: str | None = ...) -> None: ...

class StreamEventsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GameEvent(_message.Message):
    __slots__ = ("event_type", "data", "timestamp")
    class DataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: str | None = ..., value: str | None = ...) -> None: ...

    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    event_type: str
    data: _containers.ScalarMap[str, str]
    timestamp: int
    def __init__(
        self,
        event_type: str | None = ...,
        data: _Mapping[str, str] | None = ...,
        timestamp: int | None = ...,
    ) -> None: ...
