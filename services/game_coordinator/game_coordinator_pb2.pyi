from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Iterable as _Iterable, Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

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
    def __init__(self, serial: _Optional[str] = ..., team: _Optional[int] = ..., alive: bool = ..., score: _Optional[int] = ...) -> None: ...

class StartGameRequest(_message.Message):
    __slots__ = ("game_name", "players", "settings")
    class SettingsEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    GAME_NAME_FIELD_NUMBER: _ClassVar[int]
    PLAYERS_FIELD_NUMBER: _ClassVar[int]
    SETTINGS_FIELD_NUMBER: _ClassVar[int]
    game_name: str
    players: _containers.RepeatedCompositeFieldContainer[Player]
    settings: _containers.ScalarMap[str, str]
    def __init__(self, game_name: _Optional[str] = ..., players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ..., settings: _Optional[_Mapping[str, str]] = ...) -> None: ...

class StartGameResponse(_message.Message):
    __slots__ = ("success", "error", "game_id")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    GAME_ID_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    game_id: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ..., game_id: _Optional[str] = ...) -> None: ...

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
    def __init__(self, state: _Optional[_Union[GameState, str]] = ..., game_name: _Optional[str] = ..., players: _Optional[_Iterable[_Union[Player, _Mapping]]] = ..., elapsed_seconds: _Optional[int] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

class ForceEndGameRequest(_message.Message):
    __slots__ = ("reason",)
    REASON_FIELD_NUMBER: _ClassVar[int]
    reason: str
    def __init__(self, reason: _Optional[str] = ...) -> None: ...

class ForceEndGameResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...

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
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    EVENT_TYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    TIMESTAMP_FIELD_NUMBER: _ClassVar[int]
    event_type: str
    data: _containers.ScalarMap[str, str]
    timestamp: int
    def __init__(self, event_type: _Optional[str] = ..., data: _Optional[_Mapping[str, str]] = ..., timestamp: _Optional[int] = ...) -> None: ...
