from google.protobuf.internal import containers as _containers
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from collections.abc import Mapping as _Mapping
from typing import ClassVar as _ClassVar, Optional as _Optional, Union as _Union

DESCRIPTOR: _descriptor.FileDescriptor

class MenuState(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
    __slots__ = ()
    STOPPED: _ClassVar[MenuState]
    RUNNING: _ClassVar[MenuState]
    GAME_STARTING: _ClassVar[MenuState]
STOPPED: MenuState
RUNNING: MenuState
GAME_STARTING: MenuState

class StartMenuRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StartMenuResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...

class StopMenuRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class StopMenuResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...

class GetMenuStatusRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class GetMenuStatusResponse(_message.Message):
    __slots__ = ("state", "current_selection", "ready_controller_count", "success", "error")
    STATE_FIELD_NUMBER: _ClassVar[int]
    CURRENT_SELECTION_FIELD_NUMBER: _ClassVar[int]
    READY_CONTROLLER_COUNT_FIELD_NUMBER: _ClassVar[int]
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    state: MenuState
    current_selection: str
    ready_controller_count: int
    success: bool
    error: str
    def __init__(self, state: _Optional[_Union[MenuState, str]] = ..., current_selection: _Optional[str] = ..., ready_controller_count: _Optional[int] = ..., success: bool = ..., error: _Optional[str] = ...) -> None: ...

class StreamMenuEventsRequest(_message.Message):
    __slots__ = ()
    def __init__(self) -> None: ...

class MenuEvent(_message.Message):
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

class ProcessInputRequest(_message.Message):
    __slots__ = ("input_type", "data")
    class DataEntry(_message.Message):
        __slots__ = ("key", "value")
        KEY_FIELD_NUMBER: _ClassVar[int]
        VALUE_FIELD_NUMBER: _ClassVar[int]
        key: str
        value: str
        def __init__(self, key: _Optional[str] = ..., value: _Optional[str] = ...) -> None: ...
    INPUT_TYPE_FIELD_NUMBER: _ClassVar[int]
    DATA_FIELD_NUMBER: _ClassVar[int]
    input_type: str
    data: _containers.ScalarMap[str, str]
    def __init__(self, input_type: _Optional[str] = ..., data: _Optional[_Mapping[str, str]] = ...) -> None: ...

class ProcessInputResponse(_message.Message):
    __slots__ = ("success", "error")
    SUCCESS_FIELD_NUMBER: _ClassVar[int]
    ERROR_FIELD_NUMBER: _ClassVar[int]
    success: bool
    error: str
    def __init__(self, success: bool = ..., error: _Optional[str] = ...) -> None: ...
